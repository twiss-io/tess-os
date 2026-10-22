"""`tessbrain.py sync`: journal new transcript records, run the cue pass on
the new principal lines, verify + promote candidates, re-check pending
records and onboarding answers, then regenerate the indexes.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from . import claims, cues, entities, guards, inbox, index, journal, lookup, promote, provenance, records, roots, switch
from .config import Config, iso, log_error, os_user_home, read_json, write_json
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
    return [str(v.get("transcript_path") or "") for v in sessions_state(cfg).values()
            if isinstance(v, dict) and v.get("runtime") == runtime]


def _cwd_of(runtime: str, path: Path) -> str:
    if runtime == "codex":
        return codex.session_cwd(path) or ""
    if runtime == "gemini":
        return ""
    return claude._first_cwd(path)


def vetted(cfg: Config, runtime: str, paths: List[str], also_cwd: List[str], store: Optional[List[Path]]) -> List[Path]:
    """Hook-reported (sessions.json) or --transcript paths that pass the same ownership checks as discovered
    ones: a uid-owned regular file outside the instance, in the runtime's store (cached paths), whose own
    session cwd is inside this instance. sessions.json is a repo file: an entry pointing at another project's
    rollout was journaled here merely because the file existed (Codex review finding 4)."""
    out: List[Path] = []
    for k in paths:
        if not k:
            continue
        p = Path(k)
        if not p.exists():
            continue  # a session whose transcript is gone (or was never written): nothing to journal
        why = provenance.transcript_ok(cfg, p, _cwd_of(runtime, p) if p.is_file() else "", also_cwd, store)
        if why:
            log_error(cfg, "sync: refusing %s transcript %s: %s" % (runtime, k, why))
            continue
        out.append(Path(os.path.realpath(str(p))))
    return out


# 1.0.x (Cyra B-1): where each runtime keeps its transcripts. The store was
# taken from CLAUDE_CONFIG_DIR / CODEX_HOME / GEMINI_CLI_HOME (or $HOME) of
# whatever process ran the sync, and the --claude-dir / --codex-home /
# --gemini-home checks compared against that same folder, so a command that
# moved one of them chose which files were attested as the operator's words.
# Now the trusted homes are the one under the OS user record's home, plus a
# moved home only once a real runtime hook saw it in the runtime's own
# environment (hooks.witness_store) or the operator confirmed it at a terminal
# (Codex / Gemini homes). Both are kept outside the repo, in stores.json.
STORES_FILE = "stores.json"
STORE_ENV = {"claude": "CLAUDE_CONFIG_DIR", "codex": "CODEX_HOME", "gemini": "GEMINI_CLI_HOME"}
_STORE_SUB = {"claude": ("projects",), "codex": ("sessions",), "gemini": (".gemini", "tmp")}


def default_home(runtime: str) -> Path:
    """The runtime's home under the OS user record (no environment variable consulted)."""
    h = os_user_home()
    return h / ".claude" if runtime == "claude" else h / ".codex" if runtime == "codex" else h


def env_home(runtime: str) -> Path:
    """The home this process's environment names for the runtime (what the runtime itself would use)."""
    v = os.environ.get(STORE_ENV[runtime])
    if v:
        return Path(v)
    return Path.home() / ".claude" if runtime == "claude" else Path.home() / ".codex" \
        if runtime == "codex" else Path.home()


def store_of(runtime: str, home) -> Path:
    return Path(str(home)).joinpath(*_STORE_SUB[runtime])


def _stores_path(cfg: Config) -> Optional[Path]:
    from . import extstate
    d = extstate.project_dir(cfg)
    return (d / STORES_FILE) if d is not None else None


def witnessed_homes(cfg: Config, runtime: str) -> List[str]:
    """Moved homes a hook saw (or the operator confirmed) for `runtime`; [] when none or unsafe."""
    p = _stores_path(cfg)
    if p is None or not p.is_file():
        return []
    why = provenance._owned_private(p, 0o077)
    if why:
        log_error(cfg, "sync: ignoring %s: %s" % (p, why))
        return []
    data = read_json(p, {})
    out: List[str] = []
    for h in ((data.get(runtime) if isinstance(data, dict) else None) or []):
        h = str(h)
        if not os.path.isabs(h) or provenance._inside(h, str(cfg.root)) or os.path.realpath(h) == os.sep:
            continue
        out.append(os.path.realpath(h))
    return out


def trusted_homes(cfg: Config, runtime: str) -> List[str]:
    out = [os.path.realpath(str(default_home(runtime)))]
    for h in witnessed_homes(cfg, runtime):
        if h not in out:
            out.append(h)
    return out


def record_home(cfg: Config, runtime: str, home: str) -> bool:
    """Add `home` to the trusted homes of `runtime` (stores.json, 0600, outside the repo)."""
    p = _stores_path(cfg)
    real = os.path.realpath(str(home))
    if p is None or runtime not in STORE_ENV or provenance._inside(real, str(cfg.root)) or real == os.sep:
        return False
    data = read_json(p, {}) if p.is_file() else {}
    data = data if isinstance(data, dict) else {}
    homes = [str(h) for h in (data.get(runtime) or []) if isinstance(h, str)]
    if real in homes:
        return True
    data[runtime] = homes + [real]
    tmp = p.with_name(STORES_FILE + ".tmp")
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            import json
            json.dump(data, fh, indent=2)
        os.replace(str(tmp), str(p))
    except OSError as exc:
        log_error(cfg, "sync: could not record the %s home %s" % (runtime, real), exc)
        return False
    return True


def _home_trusted(cfg: Config, runtime: str, home) -> bool:
    return os.path.realpath(str(home)) in trusted_homes(cfg, runtime)


def claude_dir_problem(cfg: Config, claude_dir: Optional[str]) -> str:
    """'' when `--claude-dir` is Claude's own transcript folder for THIS instance, else the reason.

    v1.0.0 item e: every *.jsonl in a --claude-dir was journaled, and attested as the operator's own
    words, with no check of where it came from, so an agent could write a folder of made-up
    conversations (with "confirm D-...") and sync it. Now only the runtime's own store for this project
    counts; any other folder needs the operator at a terminal (tessbrain sync asks, like `roots add`).
    1.0.x (B-1): "own" is a trusted Claude home, never one named only in this process's environment."""
    if not claude_dir:
        return ""
    real = os.path.realpath(claude_dir)
    own: List[str] = []
    for h in trusted_homes(cfg, "claude"):
        own += [os.path.realpath(str(d)) for d in claude.default_dirs(cfg.root, store_of("claude", h))]
    if real in own:
        return ""
    return ("%s is not Claude's own transcript folder for this project (%s)"
            % (claude_dir, own[0] if own else "~/.claude/projects/<project>"))


def own_store(cfg: Config, runtime: str, claude_dir: Optional[str] = None, codex_home: Optional[str] = None,
              gemini_home: Optional[str] = None) -> List[Path]:
    """The runtime's own transcript store: the only place whose files are attested as this instance's
    conversations. Overrides are passed here only once they are trusted or the operator allowed them at
    a terminal."""
    if runtime == "codex" and codex_home:
        return [store_of("codex", codex_home)]
    if runtime == "gemini" and gemini_home:
        return [store_of("gemini", gemini_home)]
    out = [store_of(runtime, h) for h in trusted_homes(cfg, runtime)]
    return out + ([Path(claude_dir)] if runtime == "claude" and claude_dir else [])


def home_problem(cfg: Config, codex_home: Optional[str], gemini_home: Optional[str]) -> str:
    """'' when --codex-home / --gemini-home are absent or name a trusted home of that runtime, else why.

    v1.0.0 audit (unbound transcript source): like --claude-dir before item e, these chose the folder whose
    files were journaled and attested as the operator's own words, so an agent could sync a folder of
    made-up rollouts. Any other folder now needs the operator at a terminal (tessbrain sync asks).
    1.0.x (B-1): a home named only in this process's environment is not trusted."""
    out = []
    if codex_home and not _home_trusted(cfg, "codex", codex_home):
        out.append("%s is not this machine's Codex home (%s)" % (codex_home, default_home("codex")))
    if gemini_home and not _home_trusted(cfg, "gemini", gemini_home):
        out.append("%s is not this machine's Gemini home (%s)" % (gemini_home, default_home("gemini")))
    return "; ".join(out)


def _untrusted_env(cfg: Config, runtime: str) -> None:
    home = env_home(runtime)
    if not _home_trusted(cfg, runtime, home):
        log_error(cfg, "sync: not journaling %s transcripts from %s: no %s hook has run with it and you have "
                       "not confirmed it, so its conversations do not count as yours"
                  % (runtime, store_of(runtime, home), runtime))


def sources(cfg: Config, runtime: str, claude_dir: Optional[str], codex_home: Optional[str],
            days: Optional[int], deadline: Optional[float] = None, gemini_home: Optional[str] = None):
    """[(transcript, parser, the runtime store it was found in)]. Discovery looks only in trusted
    homes (1.0.x, B-1), or in a folder passed on the command line once it was allowed."""
    out = []
    also_cwd = roots.extra(cfg)  # operator-added, outside the repo; never brain.json (GPT-6 round 2, R6)
    cutoff = time.time() - days * 86400 if days else None
    if runtime in ("all", "claude"):
        store = own_store(cfg, "claude", claude_dir=claude_dir)
        known = [str(p) for p in vetted(cfg, "claude", _known(cfg, "claude"), also_cwd, store)]
        if not claude_dir:
            _untrusted_env(cfg, "claude")
        bases = None if claude_dir else [store_of("claude", h) for h in trusted_homes(cfg, "claude")]
        for p in claude.discover(cfg.root, Path(claude_dir) if claude_dir else None, known, bases=bases):
            if cutoff is None or p.stat().st_mtime >= cutoff:
                out.append((p, claude.parse, store))
    if runtime in ("all", "codex"):
        if not codex_home:
            _untrusted_env(cfg, "codex")
        homes = [codex_home] if codex_home else trusted_homes(cfg, "codex")
        paths: List[Path] = []
        for h in homes:
            paths += [p for p in codex.discover(cfg.root, h, also_cwd, days, deadline) if p not in paths]
        seen = {os.path.realpath(str(p)) for p in paths}
        store = own_store(cfg, "codex", codex_home=codex_home)
        for p in vetted(cfg, "codex", _known(cfg, "codex"), also_cwd, store):
            if str(p) not in seen:
                paths.append(p)
        out.extend((p, codex.parse, store) for p in paths)
    if runtime in ("all", "gemini"):
        if not gemini_home:
            _untrusted_env(cfg, "gemini")
        store = own_store(cfg, "gemini", gemini_home=gemini_home)
        homes = [gemini_home] if gemini_home else trusted_homes(cfg, "gemini")
        found: List[Path] = []
        for h in homes:
            found += [p for p in gemini.discover(cfg.root, h, also_cwd) if p not in found]
        for p in found:
            if cutoff is None or p.stat().st_mtime >= cutoff:
                out.append((p, gemini.parse, store))
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
        hits = [h for h in lookup.search(cfg, str(ans["quote"])) if h.principal and lookup.trusted(cfg, h)]
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
    from . import extstate
    out = []
    can_seal = extstate.writable(cfg)
    for rec in records.all_records(cfg):
        if rec.meta.get("detected_by") != "onboarding" or rec.status != "pending-verification":
            continue
        q = str(rec.meta.get("source_quote") or "")
        hits = [h for h in lookup.search(cfg, q) if h.principal and lookup.trusted(cfg, h)] if q.strip() else []
        if hits:
            if rec.seal_trusted and not can_seal:
                continue  # accepted (and sealed) by the next hook, outside the sandbox
            # a file no seal vouches for (not written by onboarding, or edited since), or one only the sandbox
            # sealed (GPT-6 round 6, item 10), waits for review
            status = "accepted" if rec.seal_trusted else "proposed"
            records.update_fields(rec, {"status": status, "verified": True, "verified_at": iso(cfg.now()),
                                        "source_ref": hits[0].ref, "source_speaker": hits[0].speaker,
                                        "decided_by": rec.meta.get("decided_by") or hits[0].speaker})
            out.append({"record": rec.id, "status": status})
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
        transcript: Optional[str] = None, days: Optional[int] = None,
        wait: bool = True, gemini_home: Optional[str] = None, claude_dir_confirmed: bool = False,
        homes_confirmed: bool = False) -> Dict:
    if not cfg.active():
        return {"skipped": "source repo" if cfg.is_source_repo() else "no brain/brain.json"}
    why = "" if claude_dir_confirmed else claude_dir_problem(cfg, claude_dir)
    if why:
        log_error(cfg, "sync: refusing --claude-dir: %s" % why)
        return {"error": "refused --claude-dir: " + why}
    why = "" if homes_confirmed else home_problem(cfg, codex_home, gemini_home)
    if why:
        log_error(cfg, "sync: refusing a transcript home: %s" % why)
        return {"error": "refused: " + why}
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
        return _run_locked(cfg, runtime, claude_dir, codex_home, transcript, days, gemini_home)


def _run_locked(cfg, runtime, claude_dir, codex_home, transcript, days, gemini_home=None) -> Dict:
    provenance.prepare(cfg)
    settled = claims.settle(cfg)  # confirmations a sandboxed shell queued are durable now: apply them
    ents = entities.names(cfg)
    if transcript:
        # v1.0.0 audit: a --transcript is journaled (and attested) only from the runtime's OWN store, never an
        # agent-written file elsewhere whose recorded cwd happens to name this instance.
        parser = {"codex": codex.parse, "gemini": gemini.parse}.get(runtime, claude.parse)
        rt = runtime if runtime in ("codex", "gemini") else "claude"
        store = own_store(cfg, rt)
        srcs = [(p, parser, store) for p in vetted(cfg, rt, [transcript], roots.extra(cfg), store)]
    else:
        srcs = sources(cfg, runtime, claude_dir, codex_home, days, gemini_home=gemini_home)
    summary = {"journaled": 0, "candidates": 0, "outcomes": [], "rechecked": [], "onboarding_unverified": []}
    summary.update({"settled": settled} if settled else {})
    cands: List[Dict] = []
    taken_back: List[str] = []
    from . import extstate
    can_attest = extstate.writable(cfg)
    deferred = 0
    for path, parser, store in srcs:
        trusted = _trusted(cfg, path, store)
        if trusted and not can_attest:
            # v1.0.0 audit: a shell that cannot write the external ledger (the Codex sandbox) never attests
            # a line: the next hook, outside the sandbox, journals this transcript with its attestations.
            deferred += 1
            continue
        try:
            sess, new, commit = journal.update(cfg, path, parser, ents, trusted=trusted)
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
    if deferred:
        summary["deferred"] = deferred
    summary["candidates"] = len(cands)
    summary["outcomes"] = inbox.process_all(cfg)
    touched = {r.partition("#")[0] for r in taken_back}
    summary["held"] = held_by_takeback(cfg, taken_back) + switch.held(cfg, touched)
    summary["rechecked"] = _onboarding_records(cfg) + promote.recheck_pending(cfg)
    summary["onboarding_unverified"] = verify_onboarding(cfg)
    rc, msgs = index.regenerate(cfg)
    summary["index"] = {"rc": rc, "messages": msgs}
    return summary


def _trusted(cfg: Config, path: Path, store: Optional[List[Path]]) -> bool:
    """Its lines are attested only when the file is a uid-owned, non-shared file outside the instance AND
    inside the runtime's own transcript store (v1.0.0 audit: store=None attested any such file)."""
    if not store:
        return False
    return not provenance.transcript_ok(cfg, path, str(cfg.root), [], store)


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
