"""Activation/retention event construction -- the SINGLE place in this
component that decides what an event record contains, and the ONE
function (`record_mission_completion()`) any product-layer call site
calls. See `schema/telemetry-event.schema.json` for the enforced field
set and `docs/TELEMETRY.md` for the plain-English privacy contract.

Exactly two `event_type` values exist:

  - `"activation"` -- the FIRST governed mission this install has ever
    completed (`mission_ordinal == 1`): a human approval -> a finalized
    spec -> a generated app, the full accountability chain, firing once.
    This is the precondition metric the brief this module was built for
    measures: whether a real human ever got a real governed mission all
    the way through the pipeline at all.

  - `"retention"` -- every governed mission completed AFTER the first
    (`mission_ordinal >= 2`), carrying `days_since_last_mission` so a
    week-N-return / repeat-use view can be computed later from the
    ordinal + gap sequence alone (see `telemetry.summary.build_summary()`
    for the local reader that does exactly this).

Neither event type carries spec content, plan content, entity names,
file paths, or any other free-text/identifying field -- `mission_ordinal`
(a coarse count) and `days_since_last_mission` (a coarse gap) are the
only mission-shaped data in either record; see the schema file's own
`description` for why that is as specific as this ever gets.

## Where this is called from

Exactly one call site in this repo today: `orchestrator.pipeline.
run_pipeline()`, immediately after a `PipelineResult(status="generated")`
-- i.e. after `spec_engine.codegen.generate_app()` has ALREADY
successfully run against a spec that ALREADY passed a REAL, independently
verified `ApprovalGate` decision (see that module's own docstring for the
full hop-by-hop trace). This function does not itself know or care what
"a governed mission" means upstream -- it only counts "one more call to
`record_mission_completion()` happened" -- so the correctness of "this
only fires on the real accountability chain, never on a rejection or a
bare `spec_engine.codegen.generate_app()` call made outside the approval
gate" is a property of WHERE `orchestrator.pipeline.run_pipeline()` calls
it, not of anything in this file.

## Known limitation -- concurrent processes

`mission_ordinal` is derived by counting existing lines in the local
events log at call time (see `record_mission_completion()` below), not by
a separately-locked counter file. Two governed missions completing at
the exact same instant, from two different processes sharing one
`telemetry_dir`, could race to the same ordinal. This is a disclosed,
accepted v1 scope boundary (mirrors this repo's own disclosed-scope-
boundary discipline, e.g. `spec_engine.codegen`'s in-memory-persistence
note) -- a single human's local governed-mission cadence is not a
high-concurrency workload, and the events log itself (append-only,
`event_id`-keyed) is still a complete, honest record either way; a future
file-locked counter is an additive hardening, not a schema break.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union
from uuid import uuid4

from . import consent, store
from .consent import TelemetryError, utc_now_iso

PathLike = Union[str, Path]

SCHEMA_ID = "tess.telemetry.v1"
EVENT_TYPES = ("activation", "retention")

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _parse_iso(timestamp: str) -> datetime:
    return datetime.strptime(timestamp, _TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class MissionCompletionEvent:
    """What `record_mission_completion()` actually did. `recorded=False`
    (all other fields `None`) means telemetry was OFF for this
    `telemetry_dir` -- nothing was counted, timestamped, or written. A
    caller (`orchestrator.pipeline.run_pipeline()`) can inspect
    `.event_type` / `.mission_ordinal` for its own reporting without
    re-reading the events file."""

    recorded: bool
    event_type: Optional[str] = None
    mission_ordinal: Optional[int] = None
    days_since_last_mission: Optional[float] = None


def record_mission_completion(
    *,
    telemetry_dir: Optional[PathLike] = None,
    log_path: Optional[PathLike] = None,
) -> MissionCompletionEvent:
    """Call this ONCE per completed governed mission (human approval ->
    finalized spec -> generated app). NO-OPS INSTANTLY -- returns
    `MissionCompletionEvent(recorded=False)` without reading or writing
    ANYTHING else -- if `telemetry.consent.is_enabled(telemetry_dir)` is
    False. The opt-in check always happens FIRST: no counting, no
    timestamp, no file touched, when consent is absent. This is the
    ENTIRE opt-in enforcement for this component -- every other function
    in this package is a plain read/write helper that trusts its caller;
    this is the one gate.

    Raises `TelemetryError` (never a bare exception type) if telemetry IS
    enabled but the local state is broken (a corrupt consent file, or an
    events-log record that somehow fails schema validation) -- the
    integration call site is expected to catch this ONE type and
    downgrade it to non-fatal (see `orchestrator.pipeline`'s own
    integration point and its docstring for why)."""
    if not consent.is_enabled(telemetry_dir):
        return MissionCompletionEvent(recorded=False)

    state = consent.status(telemetry_dir)
    if not state.install_id:
        raise TelemetryError(
            "telemetry is enabled but no install_id is on file -- the consent "
            "file may be corrupt; re-run `python -m telemetry.cli enable`"
        )

    resolved_log_path = log_path if log_path is not None else store.default_events_log_path(telemetry_dir)
    prior = list(store.read_events(resolved_log_path))
    mission_ordinal = len(prior) + 1
    event_type = "activation" if mission_ordinal == 1 else "retention"

    now = datetime.now(timezone.utc)
    days_since_last_mission: Optional[float] = None
    if prior:
        last_timestamp = _parse_iso(prior[-1]["timestamp"])
        days_since_last_mission = round((now - last_timestamp).total_seconds() / 86400.0, 4)

    record = {
        "schema": SCHEMA_ID,
        "event_id": uuid4().hex,
        "event_type": event_type,
        "timestamp": utc_now_iso(),
        "install_id": state.install_id,
        "mission_ordinal": mission_ordinal,
        "days_since_last_mission": days_since_last_mission,
    }
    store.append_event(record, resolved_log_path)
    return MissionCompletionEvent(
        recorded=True,
        event_type=event_type,
        mission_ordinal=mission_ordinal,
        days_since_last_mission=days_since_last_mission,
    )


__all__ = ["MissionCompletionEvent", "record_mission_completion", "SCHEMA_ID", "EVENT_TYPES"]
