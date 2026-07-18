"""Read-only local activation/retention summary -- the LOCAL analogue of
a week-N-return dashboard, computed ENTIRELY from this install's own
`events.jsonl` (never aggregated across installs, never phoned anywhere
-- see docs/TELEMETRY.md's "No phone-home" section). This is what
`python -m telemetry.cli summary` prints; it is also directly importable
for a caller that wants the structured `LocalSummary` object instead of
formatted text.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from . import store

PathLike = Union[str, Path]


@dataclass(frozen=True)
class LocalSummary:
    activated: bool
    total_missions: int
    repeat_missions: int
    first_mission_at: Optional[str]
    last_mission_at: Optional[str]
    median_days_between_missions: Optional[float]


def build_summary(log_path: Optional[PathLike] = None) -> LocalSummary:
    """Read every event in `log_path` (default: this install's telemetry
    dir) and compute the local activation/retention view. Returns an
    all-empty `LocalSummary` (never raises) if no events exist yet --
    telemetry being off, or on but with zero completed governed missions
    so far, are both perfectly normal states for this to see."""
    events = sorted(store.read_events(log_path), key=lambda event: event["timestamp"])
    if not events:
        return LocalSummary(
            activated=False,
            total_missions=0,
            repeat_missions=0,
            first_mission_at=None,
            last_mission_at=None,
            median_days_between_missions=None,
        )

    gaps: List[float] = [
        event["days_since_last_mission"]
        for event in events
        if event.get("days_since_last_mission") is not None
    ]
    return LocalSummary(
        activated=True,
        total_missions=len(events),
        repeat_missions=max(0, len(events) - 1),
        first_mission_at=events[0]["timestamp"],
        last_mission_at=events[-1]["timestamp"],
        median_days_between_missions=round(statistics.median(gaps), 4) if gaps else None,
    )


__all__ = ["LocalSummary", "build_summary"]
