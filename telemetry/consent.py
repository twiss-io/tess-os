"""Opt-in consent state for local activation/retention telemetry -- OFF by
default. See docs/TELEMETRY.md for the full plain-English privacy
contract (what is/isn't captured, where it's stored, how to
inspect/disable/delete it) and telemetry/README.md for the architecture.

Consent lives in a single local JSON file, `consent.json`, under
`default_telemetry_dir()` (`~/.tess-os/telemetry` -- mirroring the exact
`~/.tess-os/<thing>` local-state convention `spec_engine.gate_identity.
default_identity_dir()` already established for the approval-identity
key; see that module's own docstring). ABSENCE of this file (or
`enabled: false` inside it) means telemetry is OFF: `is_enabled()` is the
ONE gate every event-emitting call site in this repo (today, exactly
one: `orchestrator.pipeline.run_pipeline()`, via `telemetry.events.
record_mission_completion()`) checks BEFORE touching the events log at
all -- no consent file, no counting, no timestamp read, nothing written,
nothing read.

`enable()` is the ONLY thing that turns telemetry on, and no code path in
this repo calls it automatically. A human runs `python -m telemetry.cli
enable` (see cli.py) or calls `enable()` directly from their own
integration. There is no environment variable, config default, or
first-run heuristic that flips this to True on its own -- the ONE env
var this module reads (`TESS_OS_TELEMETRY_DIR`) only relocates WHERE the
consent file lives (test/CI isolation, mirroring
`TESS_OS_APPROVAL_IDENTITY_DIR`'s exact role); it never changes whether
telemetry is enabled.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, Path]

# See default_telemetry_dir()'s own docstring for why this is read lazily
# rather than resolved at import time, and tests/orchestrator/
# _orchestrator_paths.py / tests/telemetry/_telemetry_paths.py for the
# session-wide test isolation that sets this so no test in this repo ever
# touches the real machine's own ~/.tess-os/telemetry/.
_TELEMETRY_DIR_ENV_OVERRIDE = "TESS_OS_TELEMETRY_DIR"


class TelemetryError(ValueError):
    """Fail loud on genuinely broken local telemetry state (a corrupt
    consent.json, an events-log record that fails schema validation) --
    never silently swallowed into a best-effort continue at THIS layer.
    The one integration call site (`orchestrator.pipeline.run_pipeline()`)
    catches this ONE type and downgrades it to a non-fatal warning --
    mirroring docs/OBSERVABILITY.md's own tessctl-trace precedent ('a
    trace-log write failure must never flip the exit code of the
    security-critical command it is merely observing') -- a telemetry bug
    must never break, or retroactively un-complete, the governed mission
    it is merely observing."""


def utc_now_iso() -> str:
    """UTC ISO-8601 with a millisecond-precision 'Z' suffix -- the same
    convention `intent_router.types.utc_now_iso()` / `spec_engine.
    content.utc_now_iso()` already use. Duplicated here (not imported) so
    this component has zero import dependency on any sibling top-level
    component -- see schema_check.py's own docstring for the same
    discipline applied to the validator."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def default_telemetry_dir() -> Path:
    """`~/.tess-os/telemetry` -- resolved LAZILY (at call time), never
    cached as a module-level constant, for the exact reason `spec_engine.
    gate_identity.default_identity_dir()` documents for itself: a
    module-level constant would freeze `Path.home()` at first import,
    before a test's monkeypatched `$HOME` (or this module's own
    `TESS_OS_TELEMETRY_DIR` override) could take effect. Honors
    `TESS_OS_TELEMETRY_DIR` first, if set."""
    override = os.environ.get(_TELEMETRY_DIR_ENV_OVERRIDE)
    if override:
        return Path(override)
    return Path.home() / ".tess-os" / "telemetry"


def _consent_path(telemetry_dir: Optional[PathLike] = None) -> Path:
    base = Path(telemetry_dir) if telemetry_dir is not None else default_telemetry_dir()
    return base / "consent.json"


@dataclass(frozen=True)
class ConsentState:
    """The complete local consent record -- never exposes anything beyond
    what `enable()` itself wrote (no PII, no content, no machine
    fingerprint)."""

    enabled: bool
    install_id: Optional[str] = None
    consented_at: Optional[str] = None


def _read_consent(path: Path) -> ConsentState:
    if not path.is_file():
        # No consent file at all is the normal, default, OFF state -- not
        # an error condition, and not something that should even log a
        # warning (a fresh install/clone of this repo has never seen
        # this file, and never will unless a human explicitly opts in).
        return ConsentState(enabled=False)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise TelemetryError(f"consent file {str(path)!r} is unreadable/corrupt: {exc}") from exc
    if not isinstance(raw, dict):
        raise TelemetryError(f"consent file {str(path)!r} must contain a JSON object, got {type(raw).__name__}")
    return ConsentState(
        enabled=bool(raw.get("enabled", False)),
        install_id=raw.get("install_id"),
        consented_at=raw.get("consented_at"),
    )


def _write_consent(path: Path, state: ConsentState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"enabled": state.enabled}
    if state.install_id is not None:
        record["install_id"] = state.install_id
    if state.consented_at is not None:
        record["consented_at"] = state.consented_at
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def is_enabled(telemetry_dir: Optional[PathLike] = None) -> bool:
    """True iff a human has explicitly opted in via `enable()`. Never
    raises on a missing consent file -- that is the normal, default, OFF
    state, not an error; DOES raise `TelemetryError` on a present-but-
    corrupt consent file (a genuinely broken local state should never be
    silently treated as 'telemetry is off', which would hide a real bug
    from whoever is debugging it)."""
    return _read_consent(_consent_path(telemetry_dir)).enabled


def status(telemetry_dir: Optional[PathLike] = None) -> ConsentState:
    """The full local consent record -- used by `telemetry.cli status`
    and `telemetry.events.record_mission_completion()`."""
    return _read_consent(_consent_path(telemetry_dir))


def enable(telemetry_dir: Optional[PathLike] = None) -> ConsentState:
    """Explicit opt-in -- THE consent mechanism (see module docstring).
    Generates a fresh, random `install_id` (`uuid.uuid4().hex` -- never
    derived from hostname, MAC address, username, or any other
    identifying machine/account property) the FIRST time telemetry is
    enabled for this `telemetry_dir`; re-running `enable()` after a prior
    `enable()` keeps the SAME `install_id` (so retention counts stay
    attributable to one install across an enable -> disable -> enable
    cycle) rather than silently resetting it. Call `disable()` to opt
    back out (keeps local state) or `telemetry.store.delete_all()` to
    erase everything, `install_id` included."""
    path = _consent_path(telemetry_dir)
    existing = _read_consent(path)
    state = ConsentState(
        enabled=True,
        install_id=existing.install_id or uuid.uuid4().hex,
        consented_at=existing.consented_at or utc_now_iso(),
    )
    _write_consent(path, state)
    return state


def disable(telemetry_dir: Optional[PathLike] = None) -> ConsentState:
    """Explicit opt-out. Sets `enabled: false` but KEEPS `install_id` /
    `consented_at` on file (not deleted) so a future re-`enable()` does
    not silently fabricate a new install identity -- see
    `telemetry.store.delete_all()` for the separate, explicit action that
    erases local telemetry state entirely, consent file included."""
    path = _consent_path(telemetry_dir)
    existing = _read_consent(path)
    state = ConsentState(enabled=False, install_id=existing.install_id, consented_at=existing.consented_at)
    _write_consent(path, state)
    return state


__all__ = [
    "TelemetryError",
    "ConsentState",
    "utc_now_iso",
    "default_telemetry_dir",
    "is_enabled",
    "status",
    "enable",
    "disable",
]
