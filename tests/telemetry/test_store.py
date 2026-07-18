"""Tests for telemetry.store -- the local, schema-validated JSONL event
log."""

from __future__ import annotations

import pytest

import _telemetry_paths  # noqa: F401 -- sys.path bootstrap

from telemetry import consent, store


def _valid_record(**overrides):
    record = {
        "schema": "tess.telemetry.v1",
        "event_id": "a" * 32,
        "event_type": "activation",
        "timestamp": "2026-07-18T00:00:00.000Z",
        "install_id": "b" * 32,
        "mission_ordinal": 1,
        "days_since_last_mission": None,
    }
    record.update(overrides)
    return record


def test_read_events_on_missing_log_returns_empty_iterator(tmp_path):
    assert list(store.read_events(tmp_path / "does-not-exist.jsonl")) == []


def test_append_and_read_round_trip(tmp_path):
    log_path = tmp_path / "events.jsonl"
    record = _valid_record()
    store.append_event(record, log_path)
    events = list(store.read_events(log_path))
    assert events == [record]


def test_append_writes_one_json_line_per_call(tmp_path):
    log_path = tmp_path / "events.jsonl"
    store.append_event(_valid_record(event_id="a" * 32), log_path)
    store.append_event(
        _valid_record(event_id="c" * 32, event_type="retention", mission_ordinal=2, days_since_last_mission=1.5),
        log_path,
    )
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_append_rejects_a_record_missing_a_required_field(tmp_path):
    record = _valid_record()
    del record["install_id"]
    with pytest.raises(consent.TelemetryError):
        store.append_event(record, tmp_path / "events.jsonl")
    assert not (tmp_path / "events.jsonl").exists()


def test_append_rejects_a_record_with_an_undocumented_extra_field(tmp_path):
    record = _valid_record(spec_id="vendor-invoice-tracker")
    with pytest.raises(consent.TelemetryError):
        store.append_event(record, tmp_path / "events.jsonl")
    assert not (tmp_path / "events.jsonl").exists()


def test_delete_all_removes_the_entire_telemetry_directory(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    consent.enable(telemetry_dir)
    store.append_event(_valid_record(), store.default_events_log_path(telemetry_dir))
    assert telemetry_dir.is_dir()
    store.delete_all(telemetry_dir)
    assert not telemetry_dir.exists()


def test_delete_all_on_nonexistent_directory_is_a_no_op(tmp_path):
    store.delete_all(tmp_path / "never-existed")  # must not raise
