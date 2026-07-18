"""Tests for telemetry.summary.build_summary() -- the local
activation/retention reader."""

from __future__ import annotations

import _telemetry_paths  # noqa: F401 -- sys.path bootstrap

from telemetry import consent, store
from telemetry.events import record_mission_completion
from telemetry.summary import build_summary


def test_summary_on_no_events_is_all_empty(tmp_path):
    summary = build_summary(tmp_path / "does-not-exist.jsonl")
    assert summary.activated is False
    assert summary.total_missions == 0
    assert summary.repeat_missions == 0
    assert summary.first_mission_at is None
    assert summary.last_mission_at is None
    assert summary.median_days_between_missions is None


def test_summary_after_three_missions(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    consent.enable(telemetry_dir)
    record_mission_completion(telemetry_dir=telemetry_dir)
    record_mission_completion(telemetry_dir=telemetry_dir)
    record_mission_completion(telemetry_dir=telemetry_dir)

    summary = build_summary(store.default_events_log_path(telemetry_dir))
    assert summary.activated is True
    assert summary.total_missions == 3
    assert summary.repeat_missions == 2
    assert summary.first_mission_at is not None
    assert summary.last_mission_at is not None
    assert summary.median_days_between_missions is not None
    assert summary.median_days_between_missions >= 0
