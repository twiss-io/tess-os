"""Records written by onboarding: the first decision and brain/probe.json.

The decision is `pending-verification` with the operator's verbatim step-1
answer as its quote (spec sections 6.4, 9.3); ws-learn's sync later checks
the quote against the operator's real turn and promotes it to `accepted`.

There is ONE record format and ws-learn owns it (scripts/brain/brainlib/
records.py + scripts/brain/templates/record-bodies/, formerly .../records/):
flat front matter, one `key: value` per line, every value JSON-encoded, keys
in ws-learn's decision order, and a body rendered with str.format_map from
ws-learn's decision body template. Onboarding writes exactly that shape. When
ws-learn's template is present it is used verbatim; when ws-learn is not
installed (its drop protocol), FALLBACK_BODY, a copy of that template, keeps
the shape identical. This module ships no record template file of its own.

probe.json seeds the static fresh-clone probe (scripts/brain/probe.py) with
what a zero-context agent must be able to answer from files alone.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import answers, scaffold, state

# ws-learn's decision key order (brainlib/records.py ORDER["decision"]).
DECISION_ORDER = [
    "schema", "id", "type", "kind", "title", "status", "tier", "authority", "decided_by", "decider_seat",
    "entity", "consulted", "informed", "source_quote", "also_quoted", "source_speaker", "source_at",
    "source_ref", "source_session", "approves_quote", "delegation_ref", "detected_by", "confirmed",
    "verified", "verified_at", "supersedes", "superseded_by", "body_sha256", "tags",
]
# ws-learn's body template locations, newest first (both owned by ws-learn).
LEARN_BODY_TEMPLATES = ("record-bodies/decision.md", "records/decision.md")
FALLBACK_BODY = ("\n# {title}\n\n## Context\n\nRecorded from {speaker}'s own words ({source_link}):\n\n"
                 "> {quote}\n\n{context}\n## Decision\n\n{statement}\n\n## Consequences\n\n{consequences}\n")


class _Blank(dict):
    def __missing__(self, key):
        return ""


def encode(value: Any) -> str:
    """ws-learn's front-matter value encoding (brainlib/frontmatter.encode)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
    return json.dumps(str(value), ensure_ascii=False)


def dump(meta: Dict[str, Any], body: str) -> str:
    keys = DECISION_ORDER + [k for k in meta if k not in DECISION_ORDER]
    lines = ["---"] + ["%s: %s" % (k, encode(meta[k])) for k in keys if k in meta] + ["---"]
    return "\n".join(lines) + "\n" + body


def body_template() -> str:
    for rel in LEARN_BODY_TEMPLATES:
        path = scaffold.TEMPLATES / rel
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return FALLBACK_BODY


def _record_id(ddir: Path, local: _dt.datetime, slug: str) -> str:
    rid = "D-%s-%s" % (local.strftime("%Y%m%d-%H%M"), slug)
    n = 2
    while (ddir / ("%s.md" % rid)).exists():
        rid = "D-%s-%s-%d" % (local.strftime("%Y%m%d-%H%M"), slug, n)
        n += 1
    return rid


def mode_decision(plan: scaffold.Plan, brain: Dict[str, Any], ctx: Dict[str, Any],
                  slug: str = "brain-mode", title: Optional[str] = None,
                  entry: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """D-<YYYYMMDD-HHMM>-<slug>.md, pending-verification, quote = the operator's words."""
    ddir = plan.root / "brain" / "decisions"
    if slug == "brain-mode" and ddir.is_dir() and any(ddir.glob("D-*-brain-mode.md")):
        return None
    entry = entry or answers.answered(brain).get("mode") or {}
    moment = state.parse_iso(entry.get("at", "")) or _dt.datetime.now().astimezone()
    rid = _record_id(ddir, state.in_tz(moment, brain.get("timezone")), slug)
    who = ctx.get("operator_slug", "")
    title = title or "Brain mode: %s" % ", ".join(brain["modes"])
    meta = {"schema": 1, "id": rid, "type": "decision", "kind": "decision", "title": title,
            "status": "pending-verification", "tier": "routine", "authority": "principal",
            "decided_by": who, "decider_seat": "", "entity": "", "consulted": [], "informed": [],
            "source_quote": entry.get("quote", ""), "also_quoted": [], "source_speaker": who,
            "source_at": entry.get("at", ""), "source_ref": "brain/brain.json#onboarding.answers.mode",
            "source_session": "%s:%s" % (entry.get("runtime", ""), entry.get("session", "")),
            "approves_quote": "", "delegation_ref": "", "detected_by": "onboarding", "confirmed": False,
            "verified": False, "verified_at": "", "supersedes": "", "superseded_by": "",
            "tags": ["onboarding"]}
    fields = {"title": title, "speaker": ctx.get("operator_name") or who,
              "source_link": "[brain.json](../brain.json), onboarding answer `mode`",
              "quote": entry.get("quote", ""),
              "context": "Recorded by onboarding. It stays `pending-verification` until the quote is found "
                         "in the operator's own turn.\n",
              "statement": "We will run this brain as: %s. Preset: %s." % (ctx["modes_line"], ctx["presets_line"]),
              "consequences": "- Entity roots: %s.\n- The map is `brain/START-HERE.md`; each entity starts "
                              "at its own `AGENTS.md`." % ", ".join(brain.get("entity_roots", []))}
    plan.create("brain/decisions/%s.md" % rid, dump(meta, body_template().format_map(_Blank(fields))))
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
