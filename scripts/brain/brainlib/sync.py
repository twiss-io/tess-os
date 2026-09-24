"""`tessbrain.py sync`: journal new transcript records, run the cue pass on
the new principal lines, verify + promote candidates, re-check pending
records and onboarding answers, then regenerate the indexes.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from . import cues, entities, guards, inbox, index, journal, lookup, promote, records
from .config import Config, iso, log_error, read_json, write_json
from .parsers import claude, codex, gemini

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows: locking degrades to a no-op
    fcntl = None

KIND_MAP = {"decision": "decision", "preference": "preference", "correction": "correction", "open_loop": "open_loop"}


def sessions_state(cfg: Config) -> Dict[str, Dict]:
    return read_json(cfg.state / "sessions.json", {})


def remember_session(cfg: Config, runtime: str, session_id: str, transcript: str, cwd: str) -> None:
    if not transcript:
        return
    cfg.ensure_state()
    data = sessions_state(cfg)
    data[session_id or transcript] = {"runtime": runtime, "transcript_path": transcript, "cwd": cwd or ""}
    write_json(cfg.state / "sessions.json", data)


def _known(cfg: Config, runtime: str) -> List[str]:
    return [v.get("transcript_path", "") for v in sessions_state(cfg).values() if v.get("runtime") == runtime]


def sources(cfg: Config, runtime: str, claude_dir: Optional[str], codex_home: Optional[str],
            also_cwd: List[str], days: Optional[int], deadline: Optional[float] = None,
            gemini_home: Optional[str] = None):
    out = []
    also_cwd = list(also_cwd) + cfg.also_cwd
    cutoff = time.time() - days * 86400 if days else None
    if runtime in ("all", "claude"):
        for p in claude.discover(cfg.root, Path(claude_dir) if claude_dir else None, _known(cfg, "claude")):
            if cutoff is None or p.stat().st_mtime >= cutoff:
                out.append((p, claude.parse))
    if runtime in ("all", "codex"):
        paths = codex.discover(cfg.root, codex_home, also_cwd, days, deadline)
        for k in _known(cfg, "codex"):
            if k and Path(k).is_file() and Path(k) not in paths:
                paths.append(Path(k))
        out.extend((p, codex.parse) for p in paths)
    if runtime in ("all", "gemini"):
        for p in gemini.discover(cfg.root, gemini_home, also_cwd):
            if cutoff is None or p.stat().st_mtime >= cutoff:
                out.append((p, gemini.parse))
    return out


def _register(entry, ents: Dict[str, str]) -> str:
    """The one entity named in THIS message, else '' (brain/decisions). Session-level
    mentions are not used: one mention of a client must not file every decision there."""
    named = [eid for eid, name in ents.items() if cues.mentions(entry.text, name)]
    return named[0] if len(named) == 1 else ""


def cue_candidates(cfg: Config, sess, new_entries, ents: Dict[str, str]) -> List[Dict]:
    out = []
    for e in new_entries:
        if e.kind != "msg" or not e.principal:
            continue
        for hit in cues.scan_text(e.text):
            entity = _register(e, ents) if hit.kind in ("decision", "open_loop") else ""
            at = iso(cfg.local(e.at)) if e.at else ""
            cand = inbox.new_candidate(
                cfg, KIND_MAP[hit.kind], hit.sentence, hit.quote, detected_by="cue", source_ref=e.ref,
                source_at=at, speaker=e.speaker, entity=entity, tier="material" if hit.material else "routine",
                external_context=bool(sess.external_context), title=hit.quote if hit.kind == "decision" else "")
            out.append(cand)
    return out


def verify_onboarding(cfg: Config) -> List[str]:
    """answers.<key>.quote must be the operator's real words (journal, principal line)."""
    data = read_json(cfg.path, None)
    if not isinstance(data, dict):
        return []
    answers = ((data.get("onboarding") or {}).get("answers") or {})
    changed, unverified = False, []
    for key, ans in answers.items():
        if not isinstance(ans, dict) or not ans.get("quote") or ans.get("verified"):
            continue
        hits = [h for h in lookup.search(cfg, str(ans["quote"])) if h.principal and h.kind != "turn"]
        if hits:
            ans["verified"] = True
            changed = True
        else:
            unverified.append(key)
    if changed:
        _write_brain_json(cfg, data)
    return unverified


def _write_brain_json(cfg: Config, data: Dict) -> None:
    import json
    tmp = cfg.path.with_name("brain.json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(cfg.path))


def _onboarding_records(cfg: Config) -> List[Dict]:
    out = []
    for rec in records.all_records(cfg):
        if rec.meta.get("detected_by") != "onboarding" or rec.status != "pending-verification":
            continue
        q = str(rec.meta.get("source_quote") or "")
        hits = [h for h in lookup.search(cfg, q) if h.principal and h.kind != "turn"] if q.strip() else []
        if hits:
            records.update_fields(rec, {"status": "accepted", "verified": True, "verified_at": iso(cfg.now()),
                                        "source_ref": hits[0].ref, "source_speaker": hits[0].speaker,
                                        "decided_by": rec.meta.get("decided_by") or hits[0].speaker})
            out.append({"record": rec.id, "status": "accepted"})
    return out


class Lock:
    """Non-blocking exclusive lock under .tess/state/brain/locks/."""

    def __init__(self, cfg: Config, name: str):
        cfg.ensure_state()
        (cfg.state / "locks").mkdir(exist_ok=True)
        self.fh = open(cfg.state / "locks" / ("%s.lock" % name), "w")
        self.ok = False

    def __enter__(self):
        if fcntl is None:
            self.ok = True
            return self
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.ok = True
        except OSError:
            self.ok = False
        return self

    def __exit__(self, *exc):
        if self.ok and fcntl is not None:
            fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


def run(cfg: Config, runtime: str = "all", claude_dir: Optional[str] = None, codex_home: Optional[str] = None,
        also_cwd: Optional[List[str]] = None, transcript: Optional[str] = None, days: Optional[int] = None,
        wait: bool = True, gemini_home: Optional[str] = None) -> Dict:
    if not cfg.active():
        return {"skipped": "source repo" if cfg.is_source_repo() else "no brain/brain.json"}
    with Lock(cfg, "sync") as lock:
        if not lock.ok and not wait:
            return {"skipped": "another sync is running"}
        if not lock.ok:
            for _ in range(100):
                time.sleep(0.2)
                try:
                    fcntl.flock(lock.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    lock.ok = True
                    break
                except OSError:
                    continue
        return _run_locked(cfg, runtime, claude_dir, codex_home, also_cwd or [], transcript, days, gemini_home)


def _run_locked(cfg, runtime, claude_dir, codex_home, also_cwd, transcript, days, gemini_home=None) -> Dict:
    ents = entities.names(cfg)
    if transcript:
        parser = {"codex": codex.parse, "gemini": gemini.parse}.get(runtime, claude.parse)
        srcs = [(Path(transcript), parser)]
    else:
        srcs = sources(cfg, runtime, claude_dir, codex_home, also_cwd, days, gemini_home=gemini_home)
    summary = {"journaled": 0, "candidates": 0, "outcomes": [], "rechecked": [], "onboarding_unverified": []}
    cands: List[Dict] = []
    taken_back: List[str] = []
    for path, parser in srcs:
        try:
            sess, new, commit = journal.update(cfg, path, parser, ents)
            found = cue_candidates(cfg, sess, new, ents) if sess is not None else []
            for cand in found:
                inbox.save(cfg, cand)  # persisted before the cursor moves
            commit()
        except Exception as exc:  # noqa: BLE001 - one bad transcript never blocks the rest
            log_error(cfg, "sync: journaling %s failed" % path, exc)
            continue
        if sess is not None:
            summary["journaled"] += 1
            cands += found
            taken_back += [e.ref for e in new if e.kind == "msg" and e.principal]
    summary["candidates"] = len(cands)
    summary["outcomes"] = inbox.process_all(cfg)
    summary["held"] = held_by_takeback(cfg, taken_back)
    summary["rechecked"] = _onboarding_records(cfg) + promote.recheck_pending(cfg)
    summary["onboarding_unverified"] = verify_onboarding(cfg)
    rc, msgs = index.regenerate(cfg)
    summary["index"] = {"rc": rc, "messages": msgs}
    return summary


JUDGED_BACK = ("decision", "preference", "correction")


def held_by_takeback(cfg: Config, refs: List[str]) -> List[Dict]:
    """A take-back at the start of a later principal message ("Wait, no.", "not Heroku after all"):
    the previous message's auto-promoted, unconfirmed records it targets go back to review (proposed)."""
    out: List[Dict] = []
    for ref in refs:
        path, _, label = ref.partition("#")
        msgs = sorted((l for l in lookup.lines_for(cfg, path) if l.kind == "msg" and l.principal),
                      key=lambda l: l.order)
        prev = [l for i, l in enumerate(msgs) if i + 1 < len(msgs) and msgs[i + 1].label == label]
        if not prev:
            continue
        nxt = [l.text for l in msgs if l.label == label][0]
        for rec in records.all_records(cfg):
            if (str(rec.meta.get("source_ref") or "") == prev[0].ref and rec.kind in JUDGED_BACK
                    and rec.status in ("accepted", "active") and rec.meta.get("confirmed") is False
                    and guards.takes_back(str(rec.meta.get("source_quote") or rec.meta.get("statement") or ""),
                                          nxt)):
                records.update_fields(rec, {"status": "proposed"})
                out.append({"record": rec.id, "status": "proposed", "reason": "V11: taken back at %s" % ref})
    return out
