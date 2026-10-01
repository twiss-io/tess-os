"""Command handlers for tessbrain.py. Each returns (exit code, payload)."""
from __future__ import annotations

import json
from typing import Dict, List, Tuple

from . import (claims, confirm, githooks, hooks, inbox, index, lint, promote, recall, records, save, status, sync, verify)
from .config import Config, iso
from .parsers import count_lines

_run_candidate = claims.run_candidate

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
    why = sync.claude_dir_problem(cfg, a.claude_dir)
    homes = sync.home_problem(cfg, a.codex_home, a.gemini_home)  # v1.0.0 audit: --codex/--gemini-home too
    ok = False
    if why or homes:  # one question for every folder that is not the runtime's own
        ok = _operator_allows_claude_dir(cfg, a.claude_dir, "; ".join(x for x in (why, homes) if x))
        if not ok and why:
            return 1, {"error": "refused --claude-dir: %s. Only you, at a terminal outside Claude Code and Codex, "
                                "can journal another folder of Claude conversations as your own words; an agent "
                                "or a pipe cannot" % why}
        if not ok:
            return 1, {"error": "refused: %s. Only you, at a terminal outside Claude Code and Codex, can journal "
                                "another folder of conversations as your own words; an agent or a pipe cannot"
                                % homes}
    res = sync.run(cfg, a.runtime, a.claude_dir, a.codex_home, a.transcript, a.days, wait=not a.no_wait,
                   gemini_home=a.gemini_home, claude_dir_confirmed=ok and bool(why),
                   homes_confirmed=ok and bool(homes))
    if isinstance(res, dict) and res.get("error"):
        return 1, res
    over = any(o.get("status") == inbox.OVER_CAP for o in res.get("outcomes", [])) if isinstance(res, dict) else False
    return (3 if over else (res.get("index", {}).get("rc", 0) if isinstance(res, dict) else 0)), res


def _operator_allows_claude_dir(cfg: Config, path: str, why: str) -> bool:
    """TTY-only, outside an assistant session, typed "yes" (the same bar as `roots add`)."""
    import sys
    from .roots import agent_session_marker
    if agent_session_marker() or not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    print("%s.\nSyncing it journals every conversation in it into THIS brain (%s) as your own words, and they "
          "can count as your decisions and confirmations." % (why, cfg.root))
    try:
        return input('Type "yes" to sync it: ').strip().lower() == "yes"
    except EOFError:
        return False


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


def _entity(cfg: Config, a) -> str:
    """Normalise --entity to an id under brain/ ("brain", "brain/x" -> "", "x"); refuse an unknown one.

    Live run 2026-09-29: a model passed `--entity brain` and the fact landed in brain/brain/facts/."""
    raw = str(getattr(a, "entity", "") or "").strip().strip("/")
    while raw == "brain" or raw.startswith("brain/"):
        raw = raw[len("brain"):].lstrip("/")
    if raw in ("", "."):
        a.entity = ""
        return ""
    if ".." in raw.split("/") or not (cfg.brain / raw / "AGENTS.md").is_file():
        return ("unknown entity %r: use an entity id listed in brain/START-HERE.md (for example clients/acme), "
                "or leave --entity out to record under brain/" % raw)
    a.entity = raw
    return ""


def _register(cfg: Config, a) -> str:
    """Normalise --register to a folder inside brain/; '' or the plain reason it is refused."""
    raw = str(getattr(a, "register", "") or "")
    if not raw:
        return ""
    target, why = records.register_target(cfg, raw)
    if why:
        return why
    a.register = target
    return ""


def _candidate(cfg: Config, a, kind: str, detected: str) -> Dict:
    return inbox.new_candidate(
        cfg, kind, a.statement or a.quote, a.quote, detected_by=detected, source_ref=getattr(a, "source_ref", ""),
        speaker=getattr(a, "speaker", ""), entity=getattr(a, "entity", "") or "", supersedes=a.supersedes or "",
        tier=getattr(a, "tier", "") or "routine", target=getattr(a, "register", "") or "",
        title=getattr(a, "title", "") or "", approves_quote=getattr(a, "approves_quote", "") or "",
        also_quoted=getattr(a, "also_quoted", None) or [], decision_kind=getattr(a, "decision_kind", "") or "",
        due=getattr(a, "due", "") or "", owner=getattr(a, "owner", "") or "",
        verify_via=getattr(a, "verify_via", "") or "")


def _shown(cfg: Config, a, res: Out) -> Out:
    """The agent relays this outcome: a proposed record or held candidate is now shown, id and all."""
    if not getattr(a, "dry_run", False) and isinstance(res[1], dict):
        out = res[1]
        confirm.present_outcome(cfg, out)
        held = [c for c in inbox.pending(cfg) if c["id"] == out.get("candidate")]
        if held:
            short = confirm.present(cfg, held[0]["id"], confirm.candidate_hash(held[0]))
            out["short_id"], out["reply"] = short, confirm.reply_phrase(short)
    return res


def cmd_decide(cfg: Config, a) -> Out:
    why = _need(cfg) or _entity(cfg, a) or _register(cfg, a)
    if why:
        return 1, {"error": why}
    if not a.no_sync:
        sync.run(cfg, "all", days=2)
    return _shown(cfg, a, _run_candidate(cfg, _candidate(cfg, a, "decision", "decide"), a.dry_run))


def cmd_remember(cfg: Config, a) -> Out:
    why = _need(cfg) or _entity(cfg, a)
    if why:
        return 1, {"error": why}
    if not a.no_sync:
        sync.run(cfg, "all", days=2)
    return _shown(cfg, a, _run_candidate(cfg, _candidate(cfg, a, a.kind, "operator"), a.dry_run))


def cmd_inbox_add(cfg: Config, a) -> Out:
    why = _need(cfg) or _entity(cfg, a) or _register(cfg, a)
    if why:
        return 1, {"error": why}
    return _shown(cfg, a, _run_candidate(cfg, _candidate(cfg, a, a.kind, a.detected_by), a.dry_run))


def cmd_inbox_list(cfg: Config, a) -> Out:
    return 0, inbox.pending(cfg)


def cmd_inbox_verify(cfg: Config, a) -> Out:
    return 0, [inbox.process(cfg, c, dry_run=True) for c in inbox.pending(cfg)]


def cmd_promote(cfg: Config, a) -> Out:
    """Approve an inbox candidate: only with the operator's fresh, authenticated words naming its id
    after it was shown (confirm.py), consumed in the external ledger first (claims.py). A candidate file
    cannot approve itself (inbox.sanitize)."""
    why = _need(cfg)
    if why:
        return 1, {"error": why}
    sync.run(cfg, "all", days=2)
    return claims.apply_promote(cfg, a)


def cmd_status_change(cfg: Config, a) -> Out:
    why = _need(cfg)
    if why:
        return 1, {"error": why}
    sync.run(cfg, "all", days=2)  # the operator's reply must be on disk to verify it
    return claims.apply_status(cfg, a)


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
    confirm.present_all(cfg, items)  # shown now: the operator confirms each by its id, after this listing
    return 0, items


def cmd_index(cfg: Config, a) -> Out:
    why = _need(cfg)
    if why:
        return (0 if cfg.is_source_repo() else 1), {"skipped": why}
    rc, msgs = index.regenerate(cfg)
    return rc, {"rc": rc, "messages": msgs}


def cmd_lint(cfg: Config, a) -> Out:
    if not cfg.exists:
        if a.warn_only and not a.json:
            return 0, None
        return 0, {"errors": [], "warnings": ["no brain/brain.json; nothing to lint"]}
    res = lint.run(cfg, staged=a.staged)
    if a.warn_only and not a.json:  # the pre-commit hook: silent when clean, plain lines otherwise
        problems = list(res["errors"]) + list(res["warnings"])
        if not problems:
            return 0, None
        return 0, "\n".join(["Tess brain check (a warning only; the commit goes ahead):"]
                             + ["  - %s" % p for p in problems])
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

