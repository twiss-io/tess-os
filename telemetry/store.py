"""Local, append-only JSONL event log for activation/retention telemetry
-- mirrors this repo's existing JSONL-log discipline
(`intent_router.decision_log`, `spec_engine.spec_log`): every record is
schema-validated BEFORE it is written (fail loud on a malformed/
oversharing record, never a silent partial or non-conforming line), and
`read_events()` returns an empty iterator for a log that does not exist
yet (a fresh install that has never completed a governed mission is not
an error).

EVERY failure mode this module can hit -- a non-conforming record, a
disk-full or unwritable `~/.tess-os` on write, a truncated/corrupt line
left behind by a prior crash on read -- surfaces as `telemetry.consent.
TelemetryError` and ONLY that type, never a raw `OSError` or
`json.JSONDecodeError`. This is what makes this module's core promise
enforceable, not just aspirational: telemetry failing must NEVER
un-complete a governed mission. `orchestrator.pipeline.
_record_governed_mission_telemetry()` is the one integration call site,
and it catches exactly `TelemetryError` -- any exception type escaping
this module that is NOT a `TelemetryError` would fly straight past that
catch and crash a mission that had already, genuinely, completed.

Nothing in this module ever opens a socket or imports a networking
library -- see docs/TELEMETRY.md's "No phone-home" section and
tests/telemetry/test_no_network.py for the same style of proof
docs/OBSERVABILITY.md's tessctl trace already carries for itself.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Union

from .consent import TelemetryError, default_telemetry_dir
from .schema_check import SchemaValidationError, validate

PathLike = Union[str, Path]

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "telemetry-event.schema.json"
_schema_cache: Optional[Dict[str, Any]] = None


def _load_schema() -> Dict[str, Any]:
    global _schema_cache
    if _schema_cache is None:
        with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
            _schema_cache = json.load(f)
    return _schema_cache


def default_events_log_path(telemetry_dir: Optional[PathLike] = None) -> Path:
    base = Path(telemetry_dir) if telemetry_dir is not None else default_telemetry_dir()
    return base / "events.jsonl"


def append_event(record: Dict[str, Any], log_path: Optional[PathLike] = None) -> Path:
    """Append `record` (already built by `telemetry.events.
    record_mission_completion()`) as one JSON line. FAILS LOUD (raises
    `TelemetryError`) rather than writing a record that does not conform
    EXACTLY to `schema/telemetry-event.schema.json` -- that schema's
    `additionalProperties: false` is the technical enforcement of "no
    PII, no content, ever", not just a documentation promise; see
    tests/telemetry/test_events_privacy.py for the adversarial proof that
    an extra field (e.g. a stray `spec_id` or `input_excerpt`) is
    rejected here, not merely discouraged by convention.

    Also FAILS LOUD, as `TelemetryError` (never a raw `OSError`), on a
    genuine local file-I/O failure -- disk full, `~/.tess-os` unwritable,
    a permissions error -- while creating the telemetry directory or
    writing the line. This module's own docstring promises "telemetry
    failing must NEVER un-complete a governed mission"; the ONE integration
    call site (`orchestrator.pipeline._record_governed_mission_telemetry()`)
    catches exactly `TelemetryError` and downgrades it to a non-fatal
    warning -- a raw `OSError` escaping this function would fly straight
    past that catch and crash a mission that genuinely completed. See
    `tests/orchestrator/test_telemetry_integration.py`'s
    `test_store_io_failure_never_breaks_a_completed_governed_mission` for
    the end-to-end proof."""
    path = Path(log_path) if log_path is not None else default_events_log_path()
    try:
        validate(record, _load_schema())
    except SchemaValidationError as exc:
        raise TelemetryError(f"refusing to write a non-conforming telemetry event: {exc}") from exc
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True))
            f.write("\n")
    except OSError as exc:
        raise TelemetryError(f"failed to append telemetry event to {str(path)!r}: {exc}") from exc
    return path


def read_events(log_path: Optional[PathLike] = None) -> Iterator[Dict[str, Any]]:
    """Yield each logged event record (dict) from `log_path`, in append
    order. Returns an empty iterator if the file does not exist -- a
    fresh telemetry directory with nothing recorded yet is not an
    error.

    FAILS LOUD, as `TelemetryError` (never a raw `OSError` or
    `json.JSONDecodeError`), if the file DOES exist but cannot be
    read (permissions/disk failure) or contains a truncated/corrupt
    line -- e.g. a partial write left behind by a process that crashed
    mid-`append_event()`. Same rationale as `append_event()`'s own
    docstring: every I/O failure mode this module can hit must funnel
    through the ONE exception type `orchestrator.pipeline`'s Hop 6
    already catches and downgrades to non-fatal, so a corrupt/unreadable
    events log can never un-complete a governed mission that has already,
    genuinely, finished."""
    path = Path(log_path) if log_path is not None else default_events_log_path()
    if not path.is_file():
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise TelemetryError(
                            f"telemetry events log {str(path)!r} contains a corrupt/truncated line: {exc}"
                        ) from exc
    except OSError as exc:
        raise TelemetryError(f"failed to read telemetry events from {str(path)!r}: {exc}") from exc


def delete_all(telemetry_dir: Optional[PathLike] = None) -> None:
    """The explicit, human-invoked delete action (`python -m telemetry.cli
    delete`; see docs/TELEMETRY.md's "How to delete it" section) --
    removes the ENTIRE local telemetry directory (`events.jsonl` AND
    `consent.json`, `install_id` included), not just the events log. A
    fresh `enable()` after this generates a brand-new `install_id`,
    exactly as if telemetry had never been used on this machine before.
    A no-op (not an error) if the directory does not exist."""
    base = Path(telemetry_dir) if telemetry_dir is not None else default_telemetry_dir()
    if base.is_dir():
        shutil.rmtree(base)


__all__ = ["default_events_log_path", "append_event", "read_events", "delete_all"]
