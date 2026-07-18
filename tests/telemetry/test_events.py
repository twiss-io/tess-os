"""Tests for telemetry.events.record_mission_completion() -- the ONE
function orchestrator.pipeline.run_pipeline() calls. See
tests/orchestrator/test_telemetry_integration.py for the same proof at
the real orchestrator lifecycle point, and test_events_privacy.py for
the adversarial "no PII/content" proof."""

from __future__ import annotations

import _telemetry_paths  # noqa: F401 -- sys.path bootstrap

from telemetry import consent, store
from telemetry.events import record_mission_completion


def test_disabled_by_default_records_nothing(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    event = record_mission_completion(telemetry_dir=telemetry_dir)
    assert event.recorded is False
    assert event.event_type is None
    assert event.mission_ordinal is None
    assert event.days_since_last_mission is None
    # A true no-op -- no directory, no file, nothing touched.
    assert not telemetry_dir.exists()


def test_first_call_after_enable_is_an_activation_event(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    consent.enable(telemetry_dir)
    event = record_mission_completion(telemetry_dir=telemetry_dir)
    assert event.recorded is True
    assert event.event_type == "activation"
    assert event.mission_ordinal == 1
    assert event.days_since_last_mission is None
    events_on_disk = list(store.read_events(store.default_events_log_path(telemetry_dir)))
    assert len(events_on_disk) == 1
    assert events_on_disk[0]["event_type"] == "activation"


def test_second_call_is_a_retention_event_with_a_nonnegative_gap(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    consent.enable(telemetry_dir)
    record_mission_completion(telemetry_dir=telemetry_dir)
    second = record_mission_completion(telemetry_dir=telemetry_dir)
    assert second.recorded is True
    assert second.event_type == "retention"
    assert second.mission_ordinal == 2
    assert second.days_since_last_mission is not None
    assert second.days_since_last_mission >= 0


def test_third_call_is_ordinal_three(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    consent.enable(telemetry_dir)
    record_mission_completion(telemetry_dir=telemetry_dir)
    record_mission_completion(telemetry_dir=telemetry_dir)
    third = record_mission_completion(telemetry_dir=telemetry_dir)
    assert third.event_type == "retention"
    assert third.mission_ordinal == 3


def test_disable_stops_emission_immediately(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    consent.enable(telemetry_dir)
    record_mission_completion(telemetry_dir=telemetry_dir)
    consent.disable(telemetry_dir)
    event = record_mission_completion(telemetry_dir=telemetry_dir)
    assert event.recorded is False
    # The one event recorded before disabling is still there -- disable
    # stops future writes, it does not retroactively erase history.
    events_on_disk = list(store.read_events(store.default_events_log_path(telemetry_dir)))
    assert len(events_on_disk) == 1


def test_disable_then_reenable_continues_the_ordinal_sequence(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    consent.enable(telemetry_dir)
    record_mission_completion(telemetry_dir=telemetry_dir)
    consent.disable(telemetry_dir)
    record_mission_completion(telemetry_dir=telemetry_dir)  # no-op while disabled
    consent.enable(telemetry_dir)
    resumed = record_mission_completion(telemetry_dir=telemetry_dir)
    assert resumed.event_type == "retention"
    assert resumed.mission_ordinal == 2
