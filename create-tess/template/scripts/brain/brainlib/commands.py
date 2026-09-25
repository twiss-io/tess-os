"""Command handlers for tessbrain.py. Each returns (exit code, payload)."""
from __future__ import annotations

import json
from typing import Dict, List, Tuple

from . import (githooks, hooks, inbox, index, lint, lookup, promote, recall, records, save, status, sync)
from .config import Config, iso
from .parsers import count_lines

Out = Tuple[int, object]


def _need(cfg: Config) -> str:
    if cfg.is_source_repo():
        return "this is the Tess OS source repo (no brain/brain.json); nothing to do"
    if not cfg.exists:
        return cfg.load_error or "brain/brain.json is missing: run onboarding first (skill brain-onboard)"
    return ""


def cmd_sync(cfg: Config, a) -> Out:
    why = _need(cfg)
    if why:
        return (0 if cfg.is_source_repo() else 1), {"skipped": why}
    res = sync.run(cfg, a.runtime, a.claude_dir, a.codex_home, a.also_cwd, a.transcript, a.days, wait=not a.no_wait,
                   gemini_home=a.gemini_home)
    over = any(o.get("status") == inbox.OVER_CAP for o in res.get("outcomes", [])) if isinstance(res, dict) else False
    return (3 if over else (res.get("index", {}).get("rc", 0) if isinstance(res, dict) else 0)), res


def cmd_journal_note(cfg: Config, a) -> Out:
    why = _need(cfg)
    if why:
        return 1, {"error": why}
    now = cfg.now()
    cfg.ensure_state()
    path = cfg.state / "notes" / ("%s.jsonl" % now.strftime("%Y%m%d"))
    path.parent.mkdir(parents=True, exist_ok=True)
    speaker = a.speaker or "operator"
    slug = cfg.resolve_speaker(speaker)
    from . import redact
    text = redact.redact(a.text)[0] if slug and cfg.consents(slug) else "[omitted: no consent]"
    rec = {"type": "user", "sessionId": "note%s" % now.strftime("%Y%m%d"), "timestamp": iso(now),
           "message": {"role": "user", "content": text}, "cwd": str(cfg.root)}
    if a.speaker:
        rec["tessSpeaker"] = a.speaker
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    from . import journal, entities
    from .parsers import claude

    def parse_note(p, upto=None):
        s = claude.parse(p, upto)
        s.runtime = "note"
        return s
    sess, new, commit = journal.update(cfg, path, parse_note, entities.names(cfg))
    for cand in (sync.cue_candidates(cfg, sess, new, entities.names(cfg)) if sess else []):
        inbox.save(cfg, cand)
    commit()
    outcomes = inbox.process_all(cfg)
    index.regenerate(cfg)
    return 0, {"journaled": bool(sess), "outcomes": outcomes}


def _candidate(cfg: Config, a, kind: str, detected: str) -> Dict:
    return inbox.new_candidate(
        cfg, kind, a.statement or a.quote, a.quote, detected_by=detected, source_ref=getattr(a, "source_ref", ""),
        speaker=getattr(a, "speaker", ""), entity=getattr(a, "entity", "") or "", supersedes=a.supersedes or "",
        tier=getattr(a, "tier", "") or "routine", target=getattr(a, "register", "") or "",
        title=getattr(a, "title", "") or "", approves_quote=getattr(a, "approves_quote", "") or "",
        also_quoted=getattr(a, "also_quoted", None) or [], decision_kind=getattr(a, "decision_kind", "") or "",
        due=getattr(a, "due", "") or "", owner=getattr(a, "owner", "") or "",
        verify_via=getattr(a, "verify_via", "") or "")


def _run_candidate(cfg: Config, cand: Dict, dry: bool) -> Out:
    outcome = inbox.process(cfg, cand, dry_run=dry)
    rc = 0
    if not dry:
        rc, msgs = index.regenerate(cfg)
        if msgs:
            outcome["index"] = msgs
    if outcome["status"] == inbox.OVER_CAP:
        return 3, outcome
    return (1 if outcome["status"] == "fail" else rc), outcome


def cmd_decide(cfg: Config, a) -> Out:
    why = _need(cfg)
    if why:
        return 1, {"error": why}
    if not a.no_sync:
        sync.run(cfg, "all", days=2)
    return _run_candidate(cfg, _candidate(cfg, a, "decision", "decide"), a.dry_run)


def cmd_remember(cfg: Config, a) -> Out:
    why = _need(cfg)
    if why:
        return 1, {"error": why}
    if not a.no_sync:
        sync.run(cfg, "all", days=2)
    return _run_candidate(cfg, _candidate(cfg, a, a.kind, "operator"), a.dry_run)


def cmd_inbox_add(cfg: Config, a) -> Out:
    why = _need(cfg)
    if why:
        return 1, {"error": why}
    return _run_candidate(cfg, _candidate(cfg, a, a.kind, a.detected_by), a.dry_run)


def cmd_inbox_list(cfg: Config, a) -> Out:
    return 0, inbox.pending(cfg)


def cmd_inbox_verify(cfg: Config, a) -> Out:
    return 0, [inbox.process(cfg, c, dry_run=True) for c in inbox.pending(cfg)]


def cmd_promote(cfg: Config, a) -> Out:
    why = _need(cfg)
    if why:
        return 1, {"error": why}
    sync.run(cfg, "all", days=2)
    cands = {c["id"]: c for c in inbox.pending(cfg)}
    if a.id not in cands:
        return 1, {"error": "no inbox candidate %s" % a.id}
    hits = [h for h in lookup.search(cfg, a.quote) if h.principal]
    if not hits:
        return 1, {"error": "V1/V2: approval quote is not a principal's words in the journal or current turn"}
    cand = dict(cands[a.id], operator_approved=True)
    cand["verification"] = {"status": "pending", "reasons": [], "checked_at": ""}
    code, out = _run_candidate(cfg, cand, False)
    rid = str(out.get("record", "")).rsplit("/", 1)[-1][:-3] if out.get("record") else ""
    if rid and rid.startswith(("D-", "P-", "C-", "F-", "L-")):
        res = promote.change_status(cfg, rid, "confirm", a.quote)  # the operator's approval confirms it
        out["status"] = res.get("status", out.get("status"))
        out["confirmed"] = bool(res.get("confirmed"))
        index.regenerate(cfg)
    return code, out


def cmd_status_change(cfg: Config, a) -> Out:
    why = _need(cfg)
    if why:
        return 1, {"error": why}
    sync.run(cfg, "all", days=2)  # the operator's reply must be on disk to verify it
    cands = {c["id"]: c for c in inbox.pending(cfg)}
    if a.id in cands:  # an inbox candidate (C-YYYYMMDD-HHMM-NN), not a C- correction record
        if a.action != "reject":
            return 1, {"error": "%s is an inbox candidate: reject it, or promote it with the operator's words" % a.id}
        c = cands[a.id]
        c["verification"] = {"status": "fail", "reasons": ["rejected by operator: %s" % a.quote], "checked_at": iso(cfg.now())}
        inbox.save(cfg, c, "rejected")
        (inbox.inbox_dir(cfg) / ("%s.json" % a.id)).unlink()
        index.regenerate(cfg)
        return 0, {"ok": True, "candidate": a.id, "status": "rejected"}
    res = promote.change_status(cfg, a.id, a.action, a.quote)
    index.regenerate(cfg)
    return (0 if res.get("ok") else 1), res


def cmd_review(cfg: Config, a) -> Out:
    items: List[Dict] = []
    for c in inbox.pending(cfg):
        items.append({"id": c["id"], "what": "candidate %s" % c["kind"], "statement": c.get("statement"),
                      "why": c.get("verification", {}).get("reasons") or ["awaiting review"]})
    for r in records.all_records(cfg):
        why = {"proposed": "proposed: needs your confirmation", "unverified": "quote never found in the journal",
               "pending-verification": "waiting for the journal to catch up"}.get(r.status)
        if why is None and r.status in ("accepted", "active") and r.meta.get("confirmed") is False:
            why = "auto-promoted (confirmed: false)"
        if why:
            items.append({"id": r.id, "what": r.kind, "statement": r.meta.get("title") or r.meta.get("statement"),
                          "why": [why], "path": r.rel(cfg)})
    for n, it in enumerate(items, 1):
        it["n"] = n
    return 0, items


def cmd_index(cfg: Config, a) -> Out:
    why = _need(cfg)
    if why:
        return (0 if cfg.is_source_repo() else 1), {"skipped": why}
    rc, msgs = index.regenerate(cfg)
    return rc, {"rc": rc, "messages": msgs}


def cmd_lint(cfg: Config, a) -> Out:
    if not cfg.exists:
        return 0, {"errors": [], "warnings": ["no brain/brain.json; nothing to lint"]}
    res = lint.run(cfg, staged=a.staged)
    return (1 if res["errors"] and not a.warn_only else 0), res


def cmd_status(cfg: Config, a) -> Out:
    why = _need(cfg)
    if why:
        return 0, {"skipped": why}
    s = status.collect(cfg)
    return 0, s if a.json else status.render(cfg, s)


def cmd_save(cfg: Config, a) -> Out:
    why = _need(cfg)
    if why:
        return 1, {"error": why}
    res = save.run(cfg, a.message, dry_run=a.dry_run)
    return (0 if res.get("ok") else 1), res


def cmd_recall(cfg: Config, a) -> Out:
    res = recall.search(cfg, a.query, a.entity, a.type, a.limit, a.private)
    return 0, res if a.json else recall.render(res)


def cmd_githooks(cfg: Config, a) -> Out:
    res = githooks.install(cfg)
    return (1 if "error" in res else 0), res


def cmd_distilled(cfg: Config, a) -> Out:
    return 0, hooks.mark_distilled(cfg)


def cmd_errors(cfg: Config, a) -> Out:
    return 0, {"errors": count_lines(cfg.state / "errors.log")}

