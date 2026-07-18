#!/usr/bin/env python3
"""Command-line entry point for the wired spine: freeform idea -> route ->
plan -> REAL authenticated approval -> generated app. A debugging/demo
tool, same role `intent_router.cli` / `spec_engine.cli` play for their own
components — this is the first CLI that chains all three end to end.

    python -m orchestrator.cli run "An app that tracks vendor invoices" \\
        --table intent-router/routing_table.example.yaml \\
        --target-dir /tmp/generated-app

If routing is ambiguous, this prints the one clarifying question and
exits (code 2) instead of guessing — re-run with `--clarification "..."`
(or `--force-route` to skip asking, matching `intent_router.cli`'s own
`--force` semantics). Pass `--no-log` to skip both intent-router's
decisions log and spec-engine's plans/specs/approvals logs entirely
(mirrors each sibling CLI's own `--no-log`).

Uses `LocalIdentityApprovalGate` (the shipped default adapter) — see
orchestrator/README.md for how to plug in a different `ApprovalGate`
implementation instead.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .adapters.local_identity import LocalIdentityApprovalGate
from .approval_gate import ApprovalAuthenticationError
from .identity import IdentityError
from .pipeline import PipelineError, PipelineResult, run_pipeline


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orchestrator.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run the full idea -> app pipeline once")
    run_p.add_argument("input_text")
    run_p.add_argument("--table", required=True, help="Path to an intent-router routing table YAML file")
    run_p.add_argument("--target-dir", required=True, dest="target_dir", help="Where to write the generated app")
    run_p.add_argument("--source", default="fragment", choices=[
        "voice_transcript", "pasted_doc", "fragment", "structured_brief",
    ])
    run_p.add_argument("--mission-id", default=None, dest="mission_id")
    run_p.add_argument("--clarification", default=None, help="Answer to a prior clarifying question")
    run_p.add_argument("--force-route", action="store_true", dest="force_route",
                        help="Never ask a clarifying question; route with a stated assumption")
    run_p.add_argument(
        "--identity-dir", default=None, dest="identity_dir",
        help="Override where LocalIdentityApprovalGate stores its signing key "
             "(default: ~/.tess-os/approval-identity) — mainly for tests/CI sandboxing.",
    )
    run_p.add_argument(
        "--no-log", action="store_true", dest="no_log",
        help="Skip writing to intent-router's decisions log and spec-engine's "
             "plans/specs/approvals logs (mirrors intent_router.cli's and "
             "spec_engine.cli's own --no-log).",
    )
    return parser


def _report(result: PipelineResult, target_dir: str) -> int:
    if result.status == "needs_clarification":
        print(f"Ambiguous — clarifying question: {result.clarifying_question}")
        print('Re-run with --clarification "<answer>" (or --force-route to skip asking).')
        return 2
    if result.status == "rejected":
        print(f"Plan {result.plan.plan_id!r} was rejected by {result.approval.approved_by!r} — no app generated.")
        return 1
    print(f"Generated app at: {target_dir}")
    print(f"Spec: {result.spec.spec_id!r} v{result.spec.spec_version} "
          f"— approved_by={result.spec.provenance.approved_by!r}")
    print(f"Codegen manifest: {len(result.codegen.manifest['modules'])} module(s), "
          f"{len(result.codegen.manifest['infrastructure_files'])} infrastructure file(s) "
          "— see .spec-engine/codegen-manifest.json for the per-module generated/stub labels.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.cmd == "run":
        gate = LocalIdentityApprovalGate(identity_dir=args.identity_dir)
        try:
            result = run_pipeline(
                args.input_text, args.table, gate,
                target_dir=args.target_dir, source_type=args.source,
                mission_id=args.mission_id, clarification_answer=args.clarification,
                force_route=args.force_route,
                route_log_path=False if args.no_log else None,
                spec_log_path=False if args.no_log else None,
            )
        except ApprovalAuthenticationError as exc:
            print(f"Approval authentication failed — no spec or app was generated: {exc}", file=sys.stderr)
            return 3
        except (IdentityError, PipelineError) as exc:
            # [Reid LOW] A local approval-identity failure (corrupt/missing/
            # over-permissive key file — see spec_engine.gate_identity) or a
            # wiring-level pipeline error must not dump a raw Python
            # traceback at a CLI user — report it cleanly on stderr with a
            # distinct exit code, mirroring the ApprovalAuthenticationError
            # handling immediately above.
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 4
        return _report(result, args.target_dir)

    return 1


if __name__ == "__main__":
    sys.exit(main())
