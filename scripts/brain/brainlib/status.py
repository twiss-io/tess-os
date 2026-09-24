"""`tessbrain.py status`: the mechanical definition of "saved" (spec 10.9),
plus what was learned, what awaits review, budgets and errors. Also renders
the SessionStart snapshot (hooks.py).
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, List

from . import caps, gitutil, reach, records
from .config import Config, iso, parse_iso, read_json, write_json
from .parsers import claude, codex, count_lines

ENGINE_STATE = {"brain", "locks", "memory", "tasks", "ledger", "receipts", "skills", "trace"}
WATCHED = ["kb", "clients", "missions", ".tess/state"]


def _misplaced(cfg: Config, deadline: float) -> List[str]:
    """Files written in the last 7 days where git ignores them or the gate refuses them."""
    paths = [p for p in WATCHED if (cfg.root / p).exists()]
    if not paths or not gitutil.is_repo(cfg.root):
        return []
    rc, out, _ = gitutil.run(cfg.root, ["status", "--porcelain=v1", "-z", "--ignored=matching",
                                         "--untracked-files=all", "--"] + paths, timeout=5)
    cutoff = time.time() - 7 * 86400
    found = []
    for rec in out.split("\0") if rc == 0 else []:
        if time.monotonic() > deadline or len(rec) < 4:
            break
        rel = rec[3:]
        parts = rel.split("/")
        if parts[-1] in (".gitkeep", ".gitignore") or rel.startswith("clients/_template/"):
            continue
        if rel.startswith(".tess/state/") and (len(parts) < 3 or parts[2] in ENGINE_STATE):
            continue
        try:
            if (cfg.root / rel).stat().st_mtime >= cutoff:
                found.append(rel)
        except OSError:
            continue
    return sorted(found)[:50]


def _unjournaled(cfg: Config, deadline: float, sweep_codex: bool) -> int:
    from .journal import cursors
    cur = cursors(cfg)
    known = [v.get("transcript_path", "") for v in read_json(cfg.state / "sessions.json", {}).values()]
    paths = claude.discover(cfg.root, None, [k for k in known if k])
    if sweep_codex:
        paths += codex.discover(cfg.root, None, [], 30, deadline)
    n = 0
    for p in paths:
        if time.monotonic() > deadline:
            break
        if count_lines(p) > int((cur.get(os.path.realpath(str(p))) or {}).get("through") or 0):
            n += 1
    return n


def _review(recs) -> Dict[str, int]:
    unconfirmed = [r for r in recs if r.status in ("accepted", "active") and r.meta.get("confirmed") is False]
    proposed = [r for r in recs if r.status == "proposed"]
    unverified = [r for r in recs if r.status in ("pending-verification", "unverified")]
    return {"unconfirmed": len(unconfirmed), "proposed": len(proposed), "unverified": len(unverified)}


def _budgets(cfg: Config) -> List[str]:
    out = []
    for name, fn in (("START-HERE.md", caps.start_here), ("profile.md", caps.profile)):
        p = cfg.brain / name
        if p.is_file():
            err = fn(cfg, p.read_text(encoding="utf-8", errors="replace"))
            if err:
                out.append("brain/%s over budget (%s)" % (name, err))
    settings = cfg.root / ".claude" / "settings.json"
    if settings.is_file() and "tessbrain.py" not in settings.read_text(encoding="utf-8", errors="replace"):
        out.append("brain hooks missing from .claude/settings.json (capture is not mechanical)")
    mem = claude.default_dirs(cfg.root)[0] / "memory" / "MEMORY.md"
    if mem.is_file() and (mem.stat().st_size >= 20 * 1024 or count_lines(mem) >= 150):
        out.append("Claude MEMORY.md is %d B; the runtime cuts it at load (brain/ is the source of truth)"
                   % mem.stat().st_size)
    return out


def learned_since(cfg: Config, recs, since: str) -> List[records.Record]:
    try:
        t0 = parse_iso(since).replace(microsecond=0)  # verified_at has whole seconds
    except (ValueError, TypeError):
        return []
    out = []
    for r in recs:
        try:
            if parse_iso(str(r.meta.get("verified_at") or "")) >= t0 and r.status not in ("pending-verification",):
                out.append(r)
        except (ValueError, TypeError):
            continue
    return sorted(out, key=records.sort_key, reverse=True)


def collect(cfg: Config, fast: bool = False) -> Dict:
    deadline = time.monotonic() + (0.8 if fast else 1.5)
    recs = records.all_records(cfg)
    unsaved = [p for _, p in gitutil.porcelain(cfg.root, [p for p in ("brain", cfg.state_cards) if (cfg.root / p).exists()])]
    unpushed, note = gitutil.unpushed(cfg.root)
    last = read_json(cfg.state / "last-session.json", {})
    errors = count_lines(cfg.state / "errors.log")
    answers = ((cfg.data.get("onboarding") or {}).get("answers") or {})
    return {
        "onboarded": cfg.onboarding_status, "unsaved": unsaved, "unpushed": unpushed, "unpushed_note": note,
        "unreachable": [cfg.rel(p) for p in reach.unreachable(cfg)],
        "misplaced": _misplaced(cfg, deadline), "unjournaled": _unjournaled(cfg, deadline, not fast),
        "inbox": len(list((cfg.brain / "inbox").glob("C-*.json"))) if (cfg.brain / "inbox").is_dir() else 0,
        "review": _review(recs), "budgets": _budgets(cfg), "errors": errors,
        "learned_since_last_session": [r.id for r in learned_since(cfg, recs, last.get("at") or "")],
        "onboarding_unverified": sorted(k for k, a in answers.items() if isinstance(a, dict) and a.get("quote")
                                        and not a.get("verified")),
        "records": len(recs),
    }


def render(cfg: Config, s: Dict, recs=None) -> str:
    lines = ["[brain] Tess brain (%d records). Map: brain/START-HERE.md. Search: tessbrain.py recall \"<words>\"." % s["records"]]
    learned = s["learned_since_last_session"]
    if learned:
        by_id = {r.id: r for r in (recs or records.all_records(cfg))}
        names = ["%s \"%s\"" % (i, str(by_id[i].meta.get("title") or by_id[i].meta.get("statement") or "")[:80])
                 for i in learned[:3] if i in by_id]
        lines.append("- Since last session I learned %d thing(s) (brain/learned.md): %s" % (len(learned), "; ".join(names)))
    rv = s["review"]
    if s["inbox"] or rv["proposed"] or rv["unconfirmed"] or rv["unverified"]:
        lines.append("- Review (skill brain-review): %d inbox candidate(s), %d proposed, %d unconfirmed auto-promotion(s),"
                     " %d unverified." % (s["inbox"], rv["proposed"], rv["unconfirmed"], rv["unverified"]))
    if s["unsaved"] or s["unpushed"] or s["unreachable"]:
        lines.append("- NOT SAVED: %d brain file(s) uncommitted, %d unpushed commit(s)%s, %d unreachable from START HERE."
                     " Run skill brain-save before saying \"saved\"." % (len(s["unsaved"]), s["unpushed"],
                     " (%s)" % s["unpushed_note"] if s["unpushed_note"] else "", len(s["unreachable"])))
    for rel in s["misplaced"][:5]:
        lines.append("- Ignored or gate-blocked, never committed: %s (move to brain/...)" % rel)
    if s["unjournaled"]:
        lines.append("- %d session(s) not journaled yet (a background sync is running)." % s["unjournaled"])
    lines += ["- Budget: %s" % b for b in s["budgets"]]
    if s["onboarding_unverified"] and s["onboarded"] == "complete":
        lines.append("- Onboarding answers not yet matched to your own words: %s" % ", ".join(s["onboarding_unverified"]))
    if s["errors"]:
        lines.append("- %d error(s) logged in .tess/state/brain/errors.log" % s["errors"])
    return "\n".join(lines)


def snapshot(cfg: Config, runtime: str) -> str:
    s = collect(cfg, fast=True)
    text = render(cfg, s)
    cfg.ensure_state()
    write_json(cfg.state / "last-session.json", {"at": iso(cfg.now()), "runtime": runtime})
    return text
