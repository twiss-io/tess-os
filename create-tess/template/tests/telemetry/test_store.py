"""Tests for telemetry.store -- the local, schema-validated JSONL event
log."""

from __future__ import annotations

from pathlib import Path

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


# --- [Reid MEDIUM] I/O failures must funnel through TelemetryError, never
# escape as a raw OSError/json.JSONDecodeError -- see store.py's module
# docstring and tests/orchestrator/test_telemetry_integration.py's
# test_store_io_failure_never_breaks_a_completed_governed_mission for the
# end-to-end proof that this is what keeps a store failure from ever
# un-completing a governed mission.


def test_append_event_wraps_a_directory_creation_failure_as_telemetry_error(tmp_path):
    # `blocker` exists as a plain FILE. append_event's log_path resolves
    # to blocker/events.jsonl, so path.parent.mkdir(parents=True,
    # exist_ok=True) must create/verify `blocker` as a directory -- but it
    # already exists as a non-directory file, so mkdir raises
    # FileExistsError (an OSError subclass) regardless of exist_ok=True
    # (pathlib only ignores FileExistsError for an existing *directory*).
    # This reproduces a real "can't write to ~/.tess-os" failure mode
    # deterministically, with no chmod / root-bypass platform dependence.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    log_path = blocker / "events.jsonl"
    with pytest.raises(consent.TelemetryError):
        store.append_event(_valid_record(), log_path)


def test_read_events_wraps_a_corrupt_truncated_line_as_telemetry_error(tmp_path):
    # A truncated/corrupt line is exactly what a process crashing
    # mid-append_event() could leave behind -- json.loads() must never
    # raise json.JSONDecodeError straight out of read_events().
    log_path = tmp_path / "events.jsonl"
    log_path.write_text('{"schema": "tess.telemetry.v1", "event_typ\n', encoding="utf-8")
    with pytest.raises(consent.TelemetryError):
        list(store.read_events(log_path))


def test_read_events_wraps_a_file_read_failure_as_telemetry_error(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    store.append_event(_valid_record(), log_path)  # a real, valid, pre-existing log

    def _raise_os_error(self, *args, **kwargs):
        raise OSError("simulated disk read failure")

    monkeypatch.setattr(Path, "open", _raise_os_error)
    with pytest.raises(consent.TelemetryError):
        list(store.read_events(log_path))


# --- [Cyra LOW-1] event_id/install_id/timestamp are now pattern-enforced
# by schema/telemetry-event.schema.json (not just documentation) -- the
# privacy contract is airtight regardless of what a future caller passes
# in, not merely honored by convention from today's only caller
# (telemetry.events.record_mission_completion()).


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("event_id", "not-a-valid-uuid-hex"),
        ("event_id", "A" * 32),  # uppercase -- pattern is lowercase-hex only
        ("event_id", "a" * 31),  # one char short
        ("install_id", "z" * 32),  # 'z' is not a hex digit
        ("timestamp", "2026-07-18T00:00:00Z"),  # missing millisecond precision
        ("timestamp", "2026-07-18 00:00:00.000Z"),  # missing the 'T' separator
        ("timestamp", "2026-07-18T00:00:00.000"),  # missing the 'Z' suffix
    ],
)
def test_append_rejects_a_record_whose_field_does_not_match_its_schema_pattern(tmp_path, field, bad_value):
    record = _valid_record(**{field: bad_value})
    with pytest.raises(consent.TelemetryError):
        store.append_event(record, tmp_path / "events.jsonl")
    assert not (tmp_path / "events.jsonl").exists()


def test_append_accepts_a_real_uuid4_hex_and_real_utc_iso_timestamp(tmp_path):
    """The exact shapes telemetry.events.record_mission_completion()
    actually produces -- uuid.uuid4().hex and consent.utc_now_iso() --
    still validate against the new patterns."""
    from uuid import uuid4

    from telemetry.consent import utc_now_iso

    record = _valid_record(event_id=uuid4().hex, install_id=uuid4().hex, timestamp=utc_now_iso())
    log_path = tmp_path / "events.jsonl"
    store.append_event(record, log_path)
    assert list(store.read_events(log_path)) == [record]
