"""brain/org/seats/CHART.md: the generated seat chart (organisation mode).

Built from the front matter of every `brain/org/seats/<seat>.md` card (name,
holder, reports_to_seat). Fully generated (`generated: true`): the seat cards
are the source of truth and this file is rewritten from them, so edits belong
in the cards. Deterministic (no timestamps), so a re-run with unchanged cards
writes nothing and a second `apply` stays a no-op.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from . import scaffold, state

SEATS = "brain/org/seats"
CHART = "brain/org/seats/CHART.md"
HEADER = """---
schema: 1
type: seat-chart
generated: true
---
# Seat chart

Generated from the seat cards in this folder (`onboard.py apply` and `onboard.py add seat`
rewrite it). Edit the cards, not this file. Every seat has exactly one holder.

| Seat | Holder | Reports to |
|---|---|---|
"""


def _front_matter(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not text.startswith("---\n"):
        return out
    for line in text[4:].split("\n---", 1)[0].splitlines():
        key, sep, raw = line.partition(":")
        if not sep:
            continue
        raw = raw.strip()
        try:
            value = json.loads(raw)
        except ValueError:
            value = raw
        out[key.strip()] = value if isinstance(value, str) else ""
    return out


def rows(root: Path) -> List[str]:
    lines = []
    for card in sorted((root / SEATS).glob("*.md")):
        if card.name == "CHART.md":
            continue
        fm = _front_matter(card.read_text(encoding="utf-8"))
        name = (fm.get("name") or card.stem).replace("|", "/")
        holder = (fm.get("holder") or "unfilled").replace("|", "/")
        boss = fm.get("reports_to_seat") or "-"
        lines.append("| [%s](%s) | %s | %s |" % (name, card.name, holder, boss))
    return lines


def write(plan: scaffold.Plan) -> None:
    """(Re)generate the chart when the organisation seats folder exists."""
    if not (plan.root / SEATS).is_dir():
        return
    text = HEADER + "\n".join(rows(plan.root)) + "\n"
    existed = (plan.root / CHART).exists()
    if plan.dry:
        plan.actions.append(("generated", CHART))
        return
    if state.atomic_write(plan.root / CHART, text):
        plan.actions.append(("updated" if existed else "created", CHART))
