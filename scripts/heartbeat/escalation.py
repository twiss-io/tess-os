"""Repeat-stall handling for an ALREADY-classified card — pure arithmetic,
no LLM. A card only reaches this path after Tier-2 has already picked its
`stall.reason` once (on the original stall event); re-deciding "is this
still awaiting a decision" every tick would be a waste of a token for a
question that's really just "how many hours since `since`, and did we
already remind recently".

Branching:
  - awaiting-decision / frontier-reached: escalate (notify) once the stall
    has been open >= ESCALATE_AFTER, then re-remind at most every
    REMIND_COOLDOWN thereafter (never spam every tick).
  - blocked-external: silent by design — the only way this clears is fresh
    evidence, which is caught by the Tier-1 "moving" path, not here.
  - attention-shift / error / anything else: already alarmed at the
    original stall event (see tier2_classify); repeat runs re-alarm on the
    same REMIND_COOLDOWN as a "still open, still nobody's looked" nudge.

Ported unchanged from the reference implementation aside from renaming the
"awaiting-xavier" enum value to the operator-neutral "awaiting-decision"
(see tier2_classify.py's STALL_REASON_ENUM) — the arithmetic itself has no
project/org-specific content to generalize.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

ESCALATE_AFTER = timedelta(hours=48)
REMIND_COOLDOWN = timedelta(hours=24)


@dataclass
class EscalationDecision:
    should_notify: bool
    message: Optional[str]


def decide(
    slug: str,
    title: str,
    reason: Optional[str],
    since: Optional[datetime],
    last_alarmed: Optional[datetime],
    now: datetime,
) -> EscalationDecision:
    if since is None:
        return EscalationDecision(False, None)

    open_for = now - since
    is_reminder_class = reason in ("awaiting-decision", "frontier-reached")

    if reason == "blocked-external":
        return EscalationDecision(False, None)

    if is_reminder_class and open_for < ESCALATE_AFTER:
        return EscalationDecision(False, None)

    if last_alarmed is not None and (now - last_alarmed) < REMIND_COOLDOWN:
        return EscalationDecision(False, None)

    hours = open_for.total_seconds() / 3600
    verb = "still awaiting a decision" if reason == "awaiting-decision" else (
        "at a frontier needing sign-off" if reason == "frontier-reached" else
        f"still stalled ({reason or 'unexplained'})"
    )
    message = (
        f"[heartbeat] {title} ({slug}) — {verb}, {hours:.0f}h since {since.isoformat().replace('+00:00', 'Z')}. "
        f"See memory/projects/{slug}.md for next_move/resume."
    )
    return EscalationDecision(True, message)
