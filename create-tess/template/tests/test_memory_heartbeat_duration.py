"""Unit tests for scripts/heartbeat/duration.py — stall_after prose parsing."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from heartbeat import duration  # noqa: E402


def test_parses_minutes():
    d, ok = duration.parse_stall_after("20 min (4x cadence) with no new commit")
    assert ok is True
    assert d == timedelta(minutes=20)


def test_parses_days():
    d, ok = duration.parse_stall_after("7 days with zero implementation activity")
    assert ok is True
    assert d == timedelta(days=7)


def test_parses_hours_decimal():
    d, ok = duration.parse_stall_after("1.5 hours since last nudge")
    assert ok is True
    assert d == timedelta(hours=1.5)


def test_parses_weeks():
    d, ok = duration.parse_stall_after("2 weeks of silence")
    assert ok is True
    assert d == timedelta(weeks=2)


def test_empty_prose_falls_back():
    d, ok = duration.parse_stall_after("")
    assert ok is False
    assert d == duration.DEFAULT_FALLBACK


def test_unparseable_prose_falls_back():
    d, ok = duration.parse_stall_after("whenever someone gets around to it")
    assert ok is False
    assert d == duration.DEFAULT_FALLBACK


def test_humanize_minutes():
    assert duration.humanize(timedelta(minutes=45)) == "45min"


def test_humanize_hours():
    assert duration.humanize(timedelta(hours=3, minutes=30)) == "3.5h"


def test_humanize_days():
    assert duration.humanize(timedelta(days=2, hours=12)) == "2.5d"
