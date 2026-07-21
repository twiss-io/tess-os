#!/usr/bin/env python3
"""Command-line entry point for manually exercising the intent router,
independent of any Claude/Codex session. This is a debugging/demo tool,
not itself a slash command — see intent-router/README.md "Integration
status" for how this maps to a future CLAUDE.md/command wiring.

    python -m intent_router.cli route "some freeform text" \\
        --table routing_table.example.yaml [--json] [--force] [--no-log]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .pipeline import run_intent_router


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="intent_router.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    route_p = sub.add_parser("route", help="Route one freeform input")
    route_p.add_argument("input_text", help="Freeform user input to route")
    route_p.add_argument("--table", required=True, help="Path to a routing table YAML file")
    route_p.add_argument("--mission-id", default=None, dest="mission_id")
    route_p.add_argument(
        "--force",
        action="store_true",
        help="Never ask a clarifying question; route with a stated assumption if ambiguous",
    )
    route_p.add_argument(
        "--json",
        action="store_true",
        help="Print the full decision record as JSON instead of the narration text",
    )
    route_p.add_argument(
        "--no-log",
        action="store_true",
        help="Skip writing to the decision log (dry run)",
    )

    args = parser.parse_args(argv)

    if args.cmd == "route":
        decision = run_intent_router(
            args.input_text,
            args.table,
            mission_id=args.mission_id,
            force=args.force,
            log_path=False if args.no_log else None,
        )
        if args.json:
            print(json.dumps(decision.to_log_record(), indent=2, sort_keys=True))
        else:
            print(decision.narration)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
