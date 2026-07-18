"""Local, append-only JSONL event log for activation/retention telemetry
-- mirrors this repo's existing JSONL-log discipline
(`intent_router.decision_log`, `spec_engine.spec_log`): every record is
schema-validated BEFORE it is written (fail loud on a malformed/
oversharing record, never a silent partial or non-conforming line), and
`read_events()` returns an empty iterator for a log that does not exist
yet (a fresh install that has never completed a governed mission is not
an error).

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
    rejected here, not merely discouraged by convention."""
    path = Path(log_path) if log_path is not None else default_events_log_path()
    try:
        validate(record, _load_schema())
    except SchemaValidationError as exc:
        raise TelemetryError(f"refusing to write a non-conforming telemetry event: {exc}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True))
        f.write("\n")
    return path


def read_events(log_path: Optional[PathLike] = None) -> Iterator[Dict[str, Any]]:
    """Yield each logged event record (dict) from `log_path`, in append
    order. Returns an empty iterator if the file does not exist -- a
    fresh telemetry directory with nothing recorded yet is not an
    error."""
    path = Path(log_path) if log_path is not None else default_events_log_path()
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


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
