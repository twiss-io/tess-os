"""Records written by onboarding: the first decision and brain/probe.json.

The decision is `pending-verification` with the operator's verbatim step-1
answer as its quote (spec sections 6.4, 9.3); ws-learn's sync later checks
the quote against the operator's real turn. probe.json seeds the static
fresh-clone probe (scripts/brain/probe.py) with what a zero-context agent
must be able to answer from files alone.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import answers, scaffold, state


def mode_decision(plan: scaffold.Plan, brain: Dict[str, Any], ctx: Dict[str, Any],
                  slug: str = "brain-mode", title: Optional[str] = None,
                  entry: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """D-<YYYYMMDD-HHMM>-<slug>.md, pending-verification, quote = the operator's words."""
    ddir = plan.root / "brain" / "decisions"
    if slug == "brain-mode" and ddir.is_dir() and any(ddir.glob("D-*-brain-mode.md")):
        return None
    entry = entry or answers.answered(brain).get("mode") or {}
    moment = state.parse_iso(entry.get("at", "")) or _dt.datetime.now().astimezone()
    local = state.in_tz(moment, brain.get("timezone"))
    rid = "D-%s-%s" % (local.strftime("%Y%m%d-%H%M"), slug)
    n = 2
    while (ddir / ("%s.md" % rid)).exists():
        rid = "D-%s-%s-%d" % (local.strftime("%Y%m%d-%H%M"), slug, n)
        n += 1
    fields = dict(ctx)
    fields.update({"record_id": rid, "title": title or "Brain mode: %s" % ", ".join(brain["modes"]),
                   "quote": entry.get("quote", ""), "source_at": entry.get("at", ""),
                   "source_session": "%s:%s" % (entry.get("runtime", ""), entry.get("session", "")),
                   "entity_roots_line": ", ".join(brain.get("entity_roots", []))})
    plan.create("brain/decisions/%s.md" % rid,
                scaffold.render((scaffold.TEMPLATES / "records" / "decision.md").read_text(encoding="utf-8"),
                                fields))
    return rid


def probe_seed(plan: scaffold.Plan, brain: Dict[str, Any], rid: Optional[str]) -> None:
    ents = entity_ids(plan.root, brain)
    mode_entry = answers.answered(brain).get("mode") or {}
    first = rid or _first_decision(plan.root)
    probe = {"schema": 1, "questions": [
        {"id": "mode", "ask": "Which mode is this brain in?", "expect": brain["modes"]},
        {"id": "operator", "ask": "Who is the operator?", "expect": brain["identity"]["operator_name"]},
        {"id": "entities", "ask": "Which entities exist?", "expect": sorted(ents)},
        {"id": "first-decision", "ask": "What was the first decision, with its quote?",
         "expect": {"id": first, "quote": mode_entry.get("quote", "")}},
        {"id": "research", "ask": "Where does research go?", "expect": "brain/kb/research/"},
    ], "negative_control": {"id": "bank-account", "ask": "What is the operator's bank account number?",
                            "expect": "unknown"}}
    plan.create("brain/probe.json", json.dumps(probe, indent=2, ensure_ascii=False) + "\n")


def entity_ids(root: Path, brain: Dict[str, Any]) -> List[str]:
    """Entity ids (paths under brain/) for every entity root that has an AGENTS.md."""
    out: List[str] = []
    for pattern in brain.get("entity_roots", []):
        for path in sorted(root.glob(pattern)):
            rel = path.relative_to(root / "brain").as_posix()
            if (path / "AGENTS.md").exists() and rel not in out:
                out.append(rel)
    return out


def _first_decision(root: Path) -> str:
    found = sorted((root / "brain" / "decisions").glob("D-*.md"))
    return found[0].stem if found else ""
