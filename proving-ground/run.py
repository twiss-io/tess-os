#!/usr/bin/env python3
"""The matrix runner — the #3 deliverable of the proving-ground.

    python run.py --dry-run
    python run.py --models weak --scaffolds bare --tasks 01-bug-average-empty-list \\
                  --max-attempts 1 --max-budget-usd 0.25

A cell is one (model tier x scaffold) combination — four cells total:
weak/bare, weak/tess-os, strong/bare, strong/tess-os. Every cell is run
against every selected task, up to `--max-attempts` attempts each (stopping
at the first pass), and the run produces `verified-pass-rate`,
`total cost`, and `mean attempts-to-pass` per cell.

`--dry-run` validates every task manifest and the matrix wiring and exits
— it NEVER invokes `claude` and spends exactly $0. This is the mode the
unit tests and CI exercise; a full real matrix run is explicitly out of
scope for routine use (see README.md "What's runnable now vs. what a
full run would cost").
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pg_lib.claude_driver import bare_mode_available, run_claude  # noqa: E402
from pg_lib.dry_run import validate_everything  # noqa: E402
from pg_lib.grading import grade_task  # noqa: E402
from pg_lib.matrix import build_matrix  # noqa: E402
from pg_lib.paths import PROVING_GROUND_ROOT, REPO_ROOT_DEFAULT, RESULTS_ROOT, TASKS_ROOT  # noqa: E402
from pg_lib.report import aggregate_by_cell, render_report  # noqa: E402
from pg_lib.scaffolds import ALL_SCAFFOLDS, BARE  # noqa: E402
from pg_lib.task_registry import load_all_manifests, resolve_task_ids  # noqa: E402
from pg_lib.types import GradeResult  # noqa: E402


def main(argv=None) -> int:
    args = _parse_args(argv)
    model_ids = _model_ids_for(args.models, args.weak_model, args.strong_model)

    if args.dry_run:
        return _run_dry_run(args, model_ids)
    return _run_real_matrix(args, model_ids)


def _run_dry_run(args, model_ids: Dict[str, str]) -> int:
    problems = validate_everything(TASKS_ROOT, args.repo_root, model_ids)
    if problems:
        print("DRY RUN: FAILED\n")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("DRY RUN: OK — all task manifests valid, all graders importable, matrix wiring sound.")
    print("No `claude` subprocess was invoked. $0 spent.")
    return 0


def _run_real_matrix(args, model_ids: Dict[str, str]) -> int:
    manifests, errors = load_all_manifests(TASKS_ROOT)
    if errors:
        print("Refusing to run: task suite has invalid manifests. Run --dry-run for details.", file=sys.stderr)
        return 2

    try:
        task_ids = resolve_task_ids(TASKS_ROOT, args.tasks)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    cells = build_matrix(args.models, args.scaffolds, model_ids)
    strict_bare = not args.allow_impure_bare
    if BARE in args.scaffolds and strict_bare and not bare_mode_available():
        print(
            "WARNING: no ANTHROPIC_API_KEY set — `--bare` mode cannot authenticate.\n"
            "  Bare-scaffold cells will be SKIPPED. Pass --allow-impure-bare to run them\n"
            "  anyway without the --bare CLI flag (results will be marked impure_bare).",
            file=sys.stderr,
        )

    work_root = Path(args.work_root) if args.work_root else Path(tempfile.mkdtemp(prefix="proving-ground-"))
    work_root.mkdir(parents=True, exist_ok=True)

    budget = _BudgetTracker(args.max_total_budget_usd)
    trials: List[Dict[str, Any]] = []
    skipped_cells: List[str] = []

    for cell in cells:
        if cell.scaffold == BARE and strict_bare and not bare_mode_available():
            skipped_cells.append(f"{cell.cell_id}: requires ANTHROPIC_API_KEY for strict --bare")
            continue
        for task_id in task_ids:
            trials += _run_cell_task(
                cell, manifests[task_id], args, work_root, budget, strict_bare and cell.scaffold == BARE,
            )
            if budget.exhausted:
                break
        if budget.exhausted:
            break

    return _finalize(args, trials, skipped_cells, budget)


def _run_cell_task(cell, manifest, args, work_root: Path, budget: "_BudgetTracker", strict_bare: bool) -> List[Dict[str, Any]]:
    from pg_lib.workdir import stage_workdir  # local import: avoids importing shutil-heavy module in --dry-run path

    records: List[Dict[str, Any]] = []
    prompt = manifest.brief_path.read_text(encoding="utf-8")
    cell_task_key = f"{cell.cell_id}__{manifest.id}"

    for attempt in range(1, args.max_attempts + 1):
        if budget.exhausted:
            break
        workdir = stage_workdir(manifest, cell.scaffold, args.repo_root, work_root, f"{cell_task_key}-a{attempt}")
        claude_result = run_claude(
            prompt=prompt, cwd=workdir, model=cell.model_id, scaffold=cell.scaffold,
            max_budget_usd=args.max_budget_usd, timeout_seconds=args.timeout_seconds, strict_bare=strict_bare,
        )
        budget.add(claude_result.cost_usd)
        grade_result = _grade_or_error(claude_result, manifest, workdir)
        records.append(_trial_record(cell, manifest, attempt, claude_result, grade_result, strict_bare))
        print(f"  [{'PASS' if grade_result.passed else 'fail'}] {cell.cell_id} / {manifest.id} "
              f"attempt {attempt}/{args.max_attempts} — ${claude_result.cost_usd:.4f} — {grade_result.reason}")
        if grade_result.passed:
            break
    return records


def _grade_or_error(claude_result, manifest, workdir) -> GradeResult:
    if not claude_result.ok or claude_result.is_error:
        return GradeResult(False, f"claude invocation did not complete cleanly: {claude_result.stderr[:300]}")
    return grade_task(manifest, workdir)


def _trial_record(cell, manifest, attempt, claude_result, grade_result, strict_bare: bool) -> Dict[str, Any]:
    return {
        "cell_id": cell.cell_id,
        "model_tier": cell.model_tier,
        "model_id": cell.model_id,
        "scaffold": cell.scaffold,
        "task_id": manifest.id,
        "attempt": attempt,
        "passed": grade_result.passed,
        "grade_reason": grade_result.reason,
        "cost_usd": claude_result.cost_usd,
        "duration_ms": claude_result.duration_ms,
        "num_turns": claude_result.num_turns,
        "is_error": claude_result.is_error,
        "timed_out": claude_result.timed_out,
        "impure_bare": (cell.scaffold == BARE and not strict_bare),
    }


class _BudgetTracker:
    def __init__(self, cap_usd: float):
        self.cap_usd = cap_usd
        self.spent_usd = 0.0

    def add(self, cost_usd: float) -> None:
        self.spent_usd += cost_usd

    @property
    def exhausted(self) -> bool:
        return self.spent_usd >= self.cap_usd


def _finalize(args, trials: List[Dict[str, Any]], skipped_cells: List[str], budget: "_BudgetTracker") -> int:
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    meta = {
        "timestamp_utc": timestamp,
        "models": ", ".join(args.models),
        "scaffolds": ", ".join(args.scaffolds),
        "max_attempts": args.max_attempts,
        "tasks": ", ".join(args.tasks),
        "total_cost_usd": round(budget.spent_usd, 4),
        "budget_exhausted": budget.exhausted,
        "skipped_cells": skipped_cells,
    }
    out_path = args.out or (RESULTS_ROOT / f"run-{timestamp}.json")
    Path(out_path).write_text(json.dumps({"meta": meta, "trials": trials}, indent=2), encoding="utf-8")
    print(f"\nResults written to {out_path}")

    if trials:
        aggregated = aggregate_by_cell(trials)
        _write_report(args, aggregated, meta, timestamp)
        print(json.dumps(aggregated, indent=2))
    else:
        print("No trials were run (all cells skipped or zero tasks selected) — no report generated.")
    return 0


def _write_report(args, aggregated: Dict[str, Any], meta: Dict[str, Any], timestamp: str) -> None:
    template_path = PROVING_GROUND_ROOT / "REPORT-template.md"
    report_out = args.report_out or (RESULTS_ROOT / f"REPORT-{timestamp}.md")
    rendered = render_report(template_path.read_text(encoding="utf-8"), aggregated, meta)
    Path(report_out).write_text(rendered, encoding="utf-8")
    print(f"Report written to {report_out}")


def _model_ids_for(models: List[str], weak_model: str, strong_model: str) -> Dict[str, str]:
    all_ids = {"weak": weak_model, "strong": strong_model}
    return {tier: all_ids[tier] for tier in models}


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="proving-ground matrix runner")
    parser.add_argument("--dry-run", action="store_true", help="validate manifests + matrix wiring, spend $0, exit")
    parser.add_argument("--tasks", type=lambda s: s.split(","), default=["all"], help='comma-separated task ids, or "all"')
    parser.add_argument("--models", type=lambda s: s.split(","), default=["weak", "strong"], choices=None)
    parser.add_argument("--scaffolds", type=lambda s: s.split(","), default=list(ALL_SCAFFOLDS))
    parser.add_argument("--weak-model", default="haiku", help="claude --model alias/id for the weak tier")
    parser.add_argument("--strong-model", default="opus", help="claude --model alias/id for the strong tier")
    parser.add_argument("--max-attempts", type=int, default=3, help="matches the framework's own retry-protocol cap")
    parser.add_argument("--max-budget-usd", type=float, default=1.0, help="per-attempt claude --max-budget-usd cap")
    parser.add_argument("--max-total-budget-usd", type=float, default=5.0, help="hard stop for the whole run")
    parser.add_argument("--timeout-seconds", type=int, default=600, help="per-attempt wall-clock subprocess timeout")
    parser.add_argument("--allow-impure-bare", action="store_true",
                         help="run bare-scaffold cells without --bare when ANTHROPIC_API_KEY is unset "
                              "(marks results impure_bare instead of skipping)")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT_DEFAULT)
    parser.add_argument("--work-root", type=Path, default=None, help="default: a fresh system temp dir")
    parser.add_argument("--out", type=Path, default=None, help="default: results/run-<timestamp>.json")
    parser.add_argument("--report-out", type=Path, default=None, help="default: results/REPORT-<timestamp>.md")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
