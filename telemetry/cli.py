#!/usr/bin/env python3
"""Command-line entry point for local activation/retention telemetry --
consent management (enable/disable/status) and the local summary reader.
A NEW, product-surface CLI -- deliberately NOT `.tess/bin/tessctl` (that
file is the ship-gate engine; this is a product-layer instrumentation
concern, out of scope for it) and deliberately its own module, not folded
into `orchestrator.cli` (telemetry is usable, and inspectable/erasable,
independent of any one pipeline run).

    python -m telemetry.cli status     # show consent state + where events live
    python -m telemetry.cli enable     # explicit opt-in -- the ONLY way telemetry turns on
    python -m telemetry.cli disable    # explicit opt-out (existing local events are kept)
    python -m telemetry.cli summary    # local activation/retention summary from events.jsonl
    python -m telemetry.cli delete     # permanently erase ALL local telemetry state

See docs/TELEMETRY.md for the full privacy contract this CLI manages.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import consent, store
from .summary import build_summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="telemetry.cli", description="Local, opt-in activation/retention telemetry for tess-os."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="Show whether telemetry is enabled, the local install id, and where events live")
    sub.add_parser("enable", help="Opt in to local activation/retention telemetry (OFF by default)")
    sub.add_parser("disable", help="Opt out -- existing local events are kept; see 'delete' to erase everything")
    sub.add_parser("summary", help="Print the local activation/retention summary computed from events.jsonl")
    sub.add_parser("delete", help="Permanently delete ALL local telemetry state (consent.json + events.jsonl)")
    return parser


def _cmd_status() -> int:
    state = consent.status()
    print(f"enabled:      {state.enabled}")
    print(f"install_id:   {state.install_id or '(none yet -- run `enable` to opt in)'}")
    print(f"consented_at: {state.consented_at or '(none yet)'}")
    print(f"events log:   {store.default_events_log_path()}")
    return 0


def _cmd_enable() -> int:
    state = consent.enable()
    print("Telemetry ENABLED -- local activation/retention events will now be recorded.")
    print(f"install_id: {state.install_id}")
    print(f"stored at:  {store.default_events_log_path()}")
    print("See docs/TELEMETRY.md for exactly what is captured and how to disable/delete it.")
    return 0


def _cmd_disable() -> int:
    consent.disable()
    print("Telemetry DISABLED -- no further events will be recorded.")
    print("Existing local events are kept; run `python -m telemetry.cli delete` to erase them.")
    return 0


def _cmd_summary() -> int:
    summary = build_summary()
    if summary.total_missions == 0:
        print("No local telemetry events recorded yet.")
        return 0
    print(f"Activated:                    {summary.activated}")
    print(f"Total governed missions:      {summary.total_missions}")
    print(f"Repeat governed missions:     {summary.repeat_missions}")
    print(f"First mission at:             {summary.first_mission_at}")
    print(f"Last mission at:              {summary.last_mission_at}")
    if summary.median_days_between_missions is not None:
        print(f"Median days between missions: {summary.median_days_between_missions}")
    return 0


def _cmd_delete() -> int:
    store.delete_all()
    print("All local telemetry state deleted (consent.json + events.jsonl).")
    return 0


_HANDLERS = {
    "status": _cmd_status,
    "enable": _cmd_enable,
    "disable": _cmd_disable,
    "summary": _cmd_summary,
    "delete": _cmd_delete,
}


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    return _HANDLERS[args.cmd]()


if __name__ == "__main__":
    sys.exit(main())
