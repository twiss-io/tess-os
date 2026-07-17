"""Parse human-authored stall_after prose into a machine-comparable timedelta.

Cards store thresholds as prose written alongside the reasoning for the
number (e.g. "20 min (4x cadence) with no new commit/PR-merge/PR-update...",
"7 days with zero implementation activity following a recorded decision...").
This module extracts the first duration token from that prose. It never
invents a number — if nothing parses, it returns a documented fallback and
tells the caller so, so the gap is visible in logs instead of silently
mis-timing a stall.

Ported unchanged from the reference implementation — this module has no
project/org-specific content to generalize.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Tuple

_UNIT_SECONDS = {
    "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "day": 86400, "days": 86400,
    "week": 604800, "weeks": 604800,
}

_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?)\b",
    re.IGNORECASE,
)

# Used only when a card's stall_after prose has no parseable duration token.
# 24h is deliberately conservative (won't fire an alarm too eagerly on a
# malformed card) but the caller must log a warning naming the card so this
# is never a silent substitution.
DEFAULT_FALLBACK = timedelta(hours=24)


def parse_stall_after(prose: str) -> Tuple[timedelta, bool]:
    """Returns (duration, was_parsed). was_parsed=False means DEFAULT_FALLBACK
    was used and the caller must surface a warning."""
    if not prose:
        return DEFAULT_FALLBACK, False
    match = _PATTERN.search(prose)
    if not match:
        return DEFAULT_FALLBACK, False
    value = float(match.group(1))
    unit_seconds = _UNIT_SECONDS.get(match.group(2).lower())
    if unit_seconds is None:
        return DEFAULT_FALLBACK, False
    return timedelta(seconds=value * unit_seconds), True


def humanize(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    if total_seconds < 3600:
        return f"{total_seconds // 60}min"
    if total_seconds < 86400:
        return f"{total_seconds / 3600:.1f}h"
    return f"{total_seconds / 86400:.1f}d"
