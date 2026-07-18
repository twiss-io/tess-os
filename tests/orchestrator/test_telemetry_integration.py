"""Integration proof: orchestrator.pipeline.run_pipeline()'s telemetry
hook (Hop 6 -- see that module's own docstring) fires activation/
retention events at the exact right lifecycle point, ONLY when a human
has explicitly opted in, and NEVER on a rejection. Uses the REAL
run_pipeline() end to end -- real LocalIdentityApprovalGate, the real
example intent-router routing table, real spec-engine codegen -- the
same fixtures tests/orchestrator/test_orchestrator_pipeline.py already
uses for its own positive-path proof.

See tests/telemetry/ for this component's own isolated unit suite
(including tests/telemetry/test_events_privacy.py's adversarial "no
PII/content" proof) -- this file proves the SAME contract holds at the
one real integration point, not in isolation.
"""

from __future__ import annotations

import _orchestrator_paths  # noqa: F401 -- sys.path bootstrap
from _orchestrator_paths import EXAMPLE_ROUTING_TABLE

from orchestrator.adapters.local_identity import LocalIdentityApprovalGate
from orchestrator.pipeline import run_pipeline

from telemetry import consent, store

CONFIDENT_INPUT = (
    "I'm seriously considering opening up in a completely new country next year, "
    "is that a smart expansion move for us right now?"
)
ANOTHER_CONFIDENT_INPUT = (
    "We need a small internal tool that tracks vendor invoices and flags overdue ones."
)


def _gate(tmp_path, *, approved=True):
    return LocalIdentityApprovalGate(
        identity_dir=tmp_path / "identity",
        confirm_fn=lambda plan, identity: (approved, ""),
    )


def test_disabled_by_default_run_pipeline_records_no_telemetry(monkeypatch, tmp_path):
    monkeypatch.setenv("TESS_OS_TELEMETRY_DIR", str(tmp_path / "telemetry"))
    result = run_pipeline(
        CONFIDENT_INPUT, EXAMPLE_ROUTING_TABLE, _gate(tmp_path),
        target_dir=tmp_path / "generated-app",
        route_log_path=False, spec_log_path=False,
    )
    assert result.status == "generated"
    assert result.telemetry.recorded is False
    # A true no-op -- telemetry never even created its directory.
    assert not (tmp_path / "telemetry").exists()


def test_enabled_run_pipeline_fires_activation_then_retention(monkeypatch, tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    monkeypatch.setenv("TESS_OS_TELEMETRY_DIR", str(telemetry_dir))
    consent.enable(telemetry_dir)
    gate = _gate(tmp_path)

    first = run_pipeline(
        CONFIDENT_INPUT, EXAMPLE_ROUTING_TABLE, gate,
        target_dir=tmp_path / "generated-app-1",
        route_log_path=False, spec_log_path=False,
    )
    assert first.status == "generated"
    assert first.telemetry.recorded is True
    assert first.telemetry.event_type == "activation"
    assert first.telemetry.mission_ordinal == 1
    assert first.telemetry.days_since_last_mission is None

    second = run_pipeline(
        ANOTHER_CONFIDENT_INPUT, EXAMPLE_ROUTING_TABLE, gate,
        target_dir=tmp_path / "generated-app-2",
        route_log_path=False, spec_log_path=False,
    )
    assert second.status == "generated"
    assert second.telemetry.recorded is True
    assert second.telemetry.event_type == "retention"
    assert second.telemetry.mission_ordinal == 2
    assert second.telemetry.days_since_last_mission is not None
    assert second.telemetry.days_since_last_mission >= 0

    events = list(store.read_events(store.default_events_log_path(telemetry_dir)))
    assert [event["event_type"] for event in events] == ["activation", "retention"]
    # Same install_id both times -- one install, two missions.
    assert len({event["install_id"] for event in events}) == 1
    # No content leaked in either recorded event.
    for event in events:
        assert set(event.keys()) == {
            "schema", "event_id", "event_type", "timestamp",
            "install_id", "mission_ordinal", "days_since_last_mission",
        }


def test_rejected_mission_never_fires_telemetry_even_when_enabled(monkeypatch, tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    monkeypatch.setenv("TESS_OS_TELEMETRY_DIR", str(telemetry_dir))
    consent.enable(telemetry_dir)

    result = run_pipeline(
        CONFIDENT_INPUT, EXAMPLE_ROUTING_TABLE, _gate(tmp_path, approved=False),
        target_dir=tmp_path / "generated-app",
        route_log_path=False, spec_log_path=False,
    )
    assert result.status == "rejected"
    # telemetry is populated ONLY on "generated" -- a rejection is not a
    # completed governed mission and must emit nothing.
    assert result.telemetry is None
    assert list(store.read_events(store.default_events_log_path(telemetry_dir))) == []


def test_disabling_after_one_mission_stops_further_emission(monkeypatch, tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    monkeypatch.setenv("TESS_OS_TELEMETRY_DIR", str(telemetry_dir))
    consent.enable(telemetry_dir)
    gate = _gate(tmp_path)

    run_pipeline(
        CONFIDENT_INPUT, EXAMPLE_ROUTING_TABLE, gate,
        target_dir=tmp_path / "generated-app-1",
        route_log_path=False, spec_log_path=False,
    )
    consent.disable(telemetry_dir)

    second = run_pipeline(
        ANOTHER_CONFIDENT_INPUT, EXAMPLE_ROUTING_TABLE, gate,
        target_dir=tmp_path / "generated-app-2",
        route_log_path=False, spec_log_path=False,
    )
    assert second.status == "generated"  # the mission itself still completes normally
    assert second.telemetry.recorded is False  # but telemetry recorded nothing for it

    events = list(store.read_events(store.default_events_log_path(telemetry_dir)))
    assert len(events) == 1  # only the first mission, recorded before disable(), is on file


def test_store_io_failure_never_breaks_a_completed_governed_mission(monkeypatch, tmp_path, capsys):
    """[Reid MEDIUM] The module docstring on telemetry/store.py promises
    "telemetry failing must NEVER un-complete a governed mission." Before
    this fix, telemetry.store.read_events()'s json.loads(line) could raise
    a raw json.JSONDecodeError -- a type orchestrator.pipeline's Hop 6
    catch (`except TelemetryError`) does NOT catch -- straight out of a
    completed, real run_pipeline() call. Seed exactly the artifact a prior
    crashed process could leave behind (a truncated line in events.jsonl)
    and prove the governed mission still completes end to end, with the
    store failure downgraded to a non-fatal warning instead."""
    telemetry_dir = tmp_path / "telemetry"
    monkeypatch.setenv("TESS_OS_TELEMETRY_DIR", str(telemetry_dir))
    consent.enable(telemetry_dir)

    events_log = store.default_events_log_path(telemetry_dir)
    events_log.parent.mkdir(parents=True, exist_ok=True)
    events_log.write_text('{"schema": "tess.telemetry.v1", "event_typ\n', encoding="utf-8")

    result = run_pipeline(
        CONFIDENT_INPUT, EXAMPLE_ROUTING_TABLE, _gate(tmp_path),
        target_dir=tmp_path / "generated-app",
        route_log_path=False, spec_log_path=False,
    )

    # The governed mission itself -- approval, finalized spec, generated
    # app -- is completely unaffected by the telemetry store's read
    # failure. This is the whole point of Hop 6 being a downstream
    # *observer* of an already-completed mission, never a gate on it.
    assert result.status == "generated"
    assert result.codegen is not None
    assert (tmp_path / "generated-app").exists()

    # Telemetry could not be recorded (the corrupt read failed), but that
    # failure was downgraded to a non-fatal warning, never raised past
    # _record_governed_mission_telemetry()'s own `except TelemetryError`.
    assert result.telemetry is None
    captured = capsys.readouterr()
    assert "WARNING: telemetry not recorded (non-fatal)" in captured.err
