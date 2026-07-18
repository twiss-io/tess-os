"""telemetry -- local-first, OPT-IN activation/retention instrumentation
for tess-os's governed-mission pipeline (`orchestrator.pipeline.
run_pipeline()`). OFF by default: nothing is recorded until a human runs
`python -m telemetry.cli enable`. See docs/TELEMETRY.md for the full
plain-English privacy contract and telemetry/README.md for the
architecture and the exact lifecycle point this is wired into.

Public API:

    from telemetry import consent, store, summary
    from telemetry.events import record_mission_completion, MissionCompletionEvent

    consent.enable()                        # explicit opt-in
    consent.is_enabled()                     # False until enable() is called
    record_mission_completion()              # no-op unless enabled; called by
                                              # orchestrator.pipeline.run_pipeline()
    summary.build_summary()                  # local activation/retention view
"""

from __future__ import annotations

from . import consent, store, summary  # noqa: F401 -- re-exported as submodules
from .consent import ConsentState, TelemetryError, default_telemetry_dir, disable, enable, is_enabled
from .events import MissionCompletionEvent, record_mission_completion
from .summary import LocalSummary, build_summary

__all__ = [
    "consent",
    "store",
    "summary",
    "ConsentState",
    "TelemetryError",
    "default_telemetry_dir",
    "disable",
    "enable",
    "is_enabled",
    "MissionCompletionEvent",
    "record_mission_completion",
    "LocalSummary",
    "build_summary",
]

__version__ = "0.1.0"
