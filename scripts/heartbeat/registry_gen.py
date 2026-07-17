"""Regenerate memory/registry.md's dynamic dashboard from the cards.

registry.md may carry hand-authored narrative below the tables (an operator
can document why the registry exists in their own terms, e.g. an incident
record) that must never be touched by an automated regeneration. This module
regenerates everything ABOVE that marker (the STALLED table + the priority
tables) and reattaches the tail verbatim.

Sort order matches the doc's own stated contract: priority (P0-P3), then
staleness-risk (time-since-last_activity as a fraction of the card's own
stall_after) descending within a priority band.

Ported from the reference implementation with paths generalized from
`state/` to `memory/` and the header prose made framework-neutral.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from . import cards as cards_mod
from .duration import parse_stall_after

TAIL_MARKER = "## Why this registry exists"

_PRIORITIES = ["P0", "P1", "P2", "P3"]


class RegistryGenError(Exception):
    """Raised when regenerate() cannot safely tell whether hand-authored
    tail content would be silently dropped. Fail loud — matching cards.py's
    own discipline (apply_updates / _replace_scalar_line hard-stop on a
    schema-drift 0-or-2+-match rather than guess and risk a silent partial
    write)."""


def _staleness_risk(card: "cards_mod.Card", now: datetime) -> float:
    last = card.last_activity
    if last is None:
        return 1.0
    stall_after, _ = parse_stall_after(card.heartbeat.get("stall_after", ""))
    if stall_after.total_seconds() <= 0:
        return 1.0
    elapsed = (now - last).total_seconds()
    return elapsed / stall_after.total_seconds()


def _fmt_ts(ts) -> str:
    if ts is None:
        return "unknown"
    return ts.isoformat().replace("+00:00", "Z")


def _stalled_table(stalled_cards: List["cards_mod.Card"]) -> str:
    if not stalled_cards:
        return ""
    rows = []
    for c in sorted(stalled_cards, key=lambda c: c.stall_since or datetime.min.replace(tzinfo=timezone.utc)):
        since = c.stall_since
        since_str = _fmt_ts(since)
        rows.append(
            f"| [`{c.slug}`](projects/{c.path.name}) | {c.state} | {since_str} | "
            f"{c.stall_reason or 'unexplained'} | {c.frontmatter.get('next_move', '')[:140]} |"
        )
    header = (
        "## STALLED right now (needs a look before anything else)\n\n"
        "| Project | State | Since | Reason | Next move |\n"
        "|---|---|---|---|---|\n"
    )
    return header + "\n".join(rows) + "\n"


def _priority_table(priority: str, group: List["cards_mod.Card"], now: datetime) -> str:
    if not group:
        return ""
    ordered = sorted(group, key=lambda c: _staleness_risk(c, now), reverse=True)
    rows = []
    for c in ordered:
        stalled_flag = "**Yes**" if c.is_stalled else "No"
        rows.append(
            f"| [`{c.slug}`](projects/{c.path.name}) | {c.state} | {c.owner} | "
            f"{_fmt_ts(c.last_activity)} — {c.heartbeat.get('activity_proof', '')[:100]} | "
            f"{stalled_flag} | {c.frontmatter.get('next_move', '')[:140]} |"
        )
    header = (
        f"## {priority}"
        + (" — highest priority" if priority == "P0" else "")
        + "\n\n| Project | State | Owner | Last activity (evidence) | Stalled? | Next move |\n"
        "|---|---|---|---|---|---|\n"
    )
    return header + "\n".join(rows) + "\n"


def regenerate(all_cards: List["cards_mod.Card"], existing_text: str, now: datetime) -> str:
    idx = existing_text.find(TAIL_MARKER)
    if idx == -1:
        if existing_text.strip():
            # The file exists and has content, but the hand-authored tail
            # marker is gone — could be a first-time schema migration, a
            # typo'd edit, or genuine corruption. Silently truncating here
            # would permanently delete any hand-authored narrative on the
            # very next recompile write. Hard stop instead, matching
            # cards.py's own discipline (apply_updates refuses a
            # 0-or-2+-match write rather than guessing) — a human has to
            # look at this once, not lose prose forever without ever being
            # told.
            raise RegistryGenError(
                f"existing {TAIL_MARKER!r} marker not found in a non-empty "
                "registry.md — refusing to regenerate over what may be "
                "hand-authored content that would otherwise be silently "
                "dropped. Restore the marker (or confirm there is truly no "
                "tail to preserve and pass existing_text='') before "
                "rerunning."
            )
        # existing_text is empty/whitespace-only — genuinely nothing to
        # preserve (e.g. registry.md doesn't exist yet, first-ever run).
        tail = ""
    else:
        tail = existing_text[idx:]

    stalled = [c for c in all_cards if c.is_stalled]
    by_priority = {p: [c for c in all_cards if c.priority == p] for p in _PRIORITIES}

    parts = [
        "# Open Projects Registry\n\n",
        "> **AUTO-GENERATED from `memory/projects/*` — do not hand-edit.** "
        "Regenerated by scripts/heartbeat/run.py (the memory-continuity heartbeat, "
        "see docs/memory-continuity.md). This is the file session-start/session-end "
        "checklists should read to recover open work.\n>\n"
        "> Sort order: priority (P0 → P3), then staleness-risk "
        "(time-since-last-activity as a fraction of the card's own `stall_after`).\n>\n"
        f"> Compiled: {_fmt_ts(now)}. Every `last_activity` below was re-verified against a "
        "primary source (`gh api .../commits`, `gh pr list`) at or before this timestamp.\n\n---\n\n",
    ]

    stalled_block = _stalled_table(stalled)
    if stalled_block:
        parts.append(stalled_block + "\n---\n\n")

    for priority in _PRIORITIES:
        block = _priority_table(priority, by_priority[priority], now)
        if block:
            parts.append(block + "\n")

    header = "".join(parts).rstrip() + "\n\n---\n\n"
    return header + tail
