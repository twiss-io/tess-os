"""REQUIRED adversarial proof: NO event telemetry.events.
record_mission_completion() ever writes can carry PII or content. The
allowed field set is EXACTLY {schema, event_id, event_type, timestamp,
install_id, mission_ordinal, days_since_last_mission}, enforced by
schema/telemetry-event.schema.json's additionalProperties: false, not
merely a promise in this component's own Python code -- see
tests/telemetry/test_store.py's
test_append_rejects_a_record_with_an_undocumented_extra_field for the
same proof at the store layer directly."""

from __future__ import annotations

import pytest

import _telemetry_paths  # noqa: F401 -- sys.path bootstrap

from telemetry import consent, store
from telemetry.events import record_mission_completion

ALLOWED_FIELDS = {
    "schema",
    "event_id",
    "event_type",
    "timestamp",
    "install_id",
    "mission_ordinal",
    "days_since_last_mission",
}


def test_recorded_event_contains_exactly_the_allowed_fields_no_more_no_less(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    consent.enable(telemetry_dir)
    record_mission_completion(telemetry_dir=telemetry_dir)
    events = list(store.read_events(store.default_events_log_path(telemetry_dir)))
    assert len(events) == 1
    assert set(events[0].keys()) == ALLOWED_FIELDS


def test_event_values_carry_no_free_text_content(tmp_path):
    """Every value is a fixed enum/schema string, a uuid, a timestamp, an
    int, or None/float -- never a free-form string that could carry a
    fragment of a spec/plan (a title, an entity name, a file path)."""
    telemetry_dir = tmp_path / "telemetry"
    consent.enable(telemetry_dir)
    record_mission_completion(telemetry_dir=telemetry_dir)
    event = next(iter(store.read_events(store.default_events_log_path(telemetry_dir))))

    assert event["schema"] == "tess.telemetry.v1"
    assert event["event_type"] in ("activation", "retention")
    assert isinstance(event["mission_ordinal"], int)
    assert event["days_since_last_mission"] is None or isinstance(event["days_since_last_mission"], (int, float))
    # event_id / install_id are opaque uuid4-hex identifiers, never a
    # human-supplied or content-derived string.
    assert len(event["event_id"]) == 32
    int(event["event_id"], 16)
    assert len(event["install_id"]) == 32
    int(event["install_id"], 16)


@pytest.mark.parametrize(
    "extra_field,extra_value",
    [
        ("spec_id", "vendor-invoice-tracker"),
        ("plan_id", "plan-abc123"),
        ("input_excerpt", "An app that tracks vendor invoices and flags overdue ones."),
        ("approved_by", "local:xavier"),
        ("title", "Vendor Invoice Tracker"),
        ("mission_id", "m1"),
    ],
)
def test_store_refuses_to_write_an_event_carrying_any_content_shaped_extra_field(tmp_path, extra_field, extra_value):
    """Even if a future code change tried to smuggle a content-shaped
    field into an event record, telemetry.store.append_event()'s schema
    validation (additionalProperties: false) rejects it before a single
    byte is written -- the technical enforcement of the privacy
    contract, not just a promise in events.py's own code."""
    record = {
        "schema": "tess.telemetry.v1",
        "event_id": "a" * 32,
        "event_type": "activation",
        "timestamp": "2026-07-18T00:00:00.000Z",
        "install_id": "b" * 32,
        "mission_ordinal": 1,
        "days_since_last_mission": None,
        extra_field: extra_value,
    }
    with pytest.raises(consent.TelemetryError):
        store.append_event(record, tmp_path / "events.jsonl")
    assert not (tmp_path / "events.jsonl").exists()
