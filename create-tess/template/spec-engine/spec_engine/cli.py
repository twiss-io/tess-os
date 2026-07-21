#!/usr/bin/env python3
"""Command-line entry point for manually exercising the spec engine,
independent of any Claude/Codex session — a debugging/demo tool, same
role `intent_router.cli` plays for the front door.

    python -m spec_engine.cli plan "some freeform idea" --source fragment
    python -m spec_engine.cli finalize <plan.json path printed by `plan --json`> \\
        --approved-by Xavier
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .pipeline import finalize_spec, run_intake_and_plan
from .render import render_markdown
from .types import Plan


def _plan_from_dict(data: dict) -> Plan:
    # Minimal, deliberately permissive reconstruction for CLI round-tripping
    # only — NOT a general deserializer. Real integrations should keep the
    # in-memory Plan object and call finalize_spec() directly rather than
    # round-tripping through this CLI's JSON.
    from .content import DataModel, HowItLooks, HowItWorks, OpenQuestion, WhatItDoes
    from .types import RoutingContext

    rc = data.get("routing_context")
    return Plan(
        plan_id=data["plan_id"],
        mission_id=data.get("mission_id"),
        created_at=data["created_at"],
        source_type=data["source_type"],
        input_excerpt=data["input_excerpt"],
        what_it_does=WhatItDoes(**data["what_it_does"]),
        how_it_looks=HowItLooks(**data["how_it_looks"]),
        how_it_works=HowItWorks(**data["how_it_works"]),
        data_model=DataModel(entities=data["data_model"]["entities"]),
        non_goals=data.get("non_goals", []),
        acceptance_criteria=data.get("acceptance_criteria", []),
        open_questions=[OpenQuestion(**q) for q in data.get("open_questions", [])],
        routing_context=RoutingContext(**rc) if rc else None,
        summary_for_approval=data.get("summary_for_approval", ""),
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="spec_engine.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    plan_p = sub.add_parser("plan", help="Harvest freeform input into a Plan for approval")
    plan_p.add_argument("input_text")
    plan_p.add_argument("--source", required=True, choices=[
        "voice_transcript", "pasted_doc", "fragment", "structured_brief",
    ])
    plan_p.add_argument("--json", action="store_true", help="Print the full Plan record as JSON")
    plan_p.add_argument("--no-log", action="store_true")

    fin_p = sub.add_parser("finalize", help="Approve/reject a Plan (JSON on stdin) and build the spec")
    fin_p.add_argument("--approved-by", required=True)
    fin_p.add_argument("--reject", action="store_true")
    fin_p.add_argument("--notes", default="")
    fin_p.add_argument("--markdown", action="store_true", help="Print rendered SPEC.md instead of JSON")
    fin_p.add_argument(
        "--identity-dir", default=None, dest="identity_dir",
        help="Override where the local approval-signing key is stored "
             "(default: ~/.tess-os/approval-identity) — mainly for tests/CI sandboxing. "
             "finalize_spec() now mints a genuine, gate-verifiable signature under the hood "
             "(see spec_engine.gate_approval); this only affects where that key lives.",
    )

    args = parser.parse_args(argv)

    if args.cmd == "plan":
        plan = run_intake_and_plan(args.input_text, args.source, log_path=False if args.no_log else None)
        if args.json:
            print(json.dumps(plan.to_log_record(), indent=2, sort_keys=True))
        else:
            print(plan.summary_for_approval)
        return 0

    if args.cmd == "finalize":
        data = json.loads(sys.stdin.read())
        plan = _plan_from_dict(data)
        spec = finalize_spec(
            plan, approved_by=args.approved_by, approved=not args.reject, notes=args.notes, log_path=False,
            identity_dir=args.identity_dir,
        )
        if spec is None:
            print(f"Plan {plan.plan_id!r} was rejected — no spec generated.")
            return 1
        if args.markdown:
            print(render_markdown(spec))
        else:
            print(json.dumps(spec.to_log_record(), indent=2, sort_keys=True))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
