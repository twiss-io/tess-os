#!/usr/bin/env python3
"""Deterministic grader CLI — the #2 deliverable of the proving-ground.

    python grade.py <task_id> --workdir <path> [--json]

Grades a single task's produced workdir (the state left behind after an
agent — or a human, or a hand-crafted fixture in a unit test — worked on
it) and prints pass/fail. Never invokes `claude`; never spends a token.
This is the module `run.py` calls internally, and the module the unit
tests call directly against crafted "known good" / "known bad" fixtures.

Exit codes: 0 = task passed grading. 1 = task failed grading (a normal,
expected outcome — a weak model IS expected to fail some tasks). 2 = the
harness itself couldn't grade (bad task id, missing workdir, a manifest
that doesn't validate) — this must never be conflated with "1".
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pg_lib.grading import grade_task  # noqa: E402
from pg_lib.manifest import ManifestError, load_manifest  # noqa: E402
from pg_lib.paths import TASKS_ROOT  # noqa: E402


def main(argv=None) -> int:
    args = _parse_args(argv)
    task_dir = args.tasks_root / args.task_id
    if not task_dir.is_dir():
        print(f"ERROR: no such task directory: {task_dir}", file=sys.stderr)
        return 2

    try:
        manifest = load_manifest(task_dir)
    except ManifestError as exc:
        print(f"ERROR: manifest invalid, cannot grade: {exc}", file=sys.stderr)
        return 2

    workdir = args.workdir
    if not workdir.is_dir():
        print(f"ERROR: no such workdir: {workdir}", file=sys.stderr)
        return 2

    result = grade_task(manifest, workdir)
    _report(args.task_id, result, as_json=args.json)
    return 0 if result.passed else 1


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="Grade one proving-ground task against a produced workdir.")
    parser.add_argument("task_id", help="e.g. 01-bug-average-empty-list")
    parser.add_argument("--workdir", type=Path, required=True, help="directory the agent produced")
    parser.add_argument("--tasks-root", type=Path, default=TASKS_ROOT)
    parser.add_argument("--json", action="store_true", help="print the GradeResult as JSON instead of text")
    return parser.parse_args(argv)


def _report(task_id: str, result, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"task_id": task_id, **result.to_dict()}, default=str))
        return
    status = "PASS" if result.passed else "FAIL"
    print(f"[{status}] {task_id} — {result.reason}")


if __name__ == "__main__":
    raise SystemExit(main())
