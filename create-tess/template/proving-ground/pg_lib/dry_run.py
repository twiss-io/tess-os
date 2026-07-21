"""`--dry-run`: validate every task manifest + the matrix wiring, spending
zero tokens (no `claude` subprocess is ever invoked from this module).

Split out of `run.py` so both the CLI and the test suite can call
`validate_everything()` directly without shelling out to a subprocess.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from pg_lib.grading import load_grader_callable
from pg_lib.matrix import build_matrix
from pg_lib.scaffolds import ALL_SCAFFOLDS, TESS_OS, validate_tess_os_scaffold_available
from pg_lib.task_registry import load_all_manifests
from pg_lib.types import Manifest


def validate_everything(
    tasks_root: Path,
    repo_root: Path,
    model_ids: Dict[str, str],
) -> List[str]:
    """Run every dry-run check. Returns a list of problem strings — empty
    means the harness is structurally sound and ready to run for real."""
    problems: List[str] = []

    manifests, manifest_errors = load_all_manifests(tasks_root)
    problems += [f"manifest: {e}" for e in manifest_errors]
    problems += _check_grader_importability(manifests)
    problems += _check_task_count(manifests)
    problems += _check_category_coverage(manifests)

    if TESS_OS in ALL_SCAFFOLDS:
        problems += [f"scaffold: {p}" for p in validate_tess_os_scaffold_available(repo_root)]

    problems += _check_matrix_wiring(list(manifests), model_ids)
    return problems


def _check_grader_importability(manifests: Dict[str, Manifest]) -> List[str]:
    problems = []
    for task_id, manifest in manifests.items():
        try:
            load_grader_callable(manifest)
        except Exception as exc:  # noqa: BLE001 - any import failure is a dry-run problem, not a crash
            problems.append(f"{task_id}: grader did not import cleanly — {exc}")
    return problems


def _check_task_count(manifests: Dict[str, Manifest]) -> List[str]:
    if len(manifests) < 10:
        return [f"expected at least 10 valid tasks, found {len(manifests)}"]
    return []


def _check_category_coverage(manifests: Dict[str, Manifest]) -> List[str]:
    categories = {m.category for m in manifests.values()}
    required = {"bug", "feature", "research", "trap"}
    missing = required - categories
    if missing:
        return [f"task suite is missing required categories: {sorted(missing)}"]
    if not any(m.planted_trap for m in manifests.values()):
        return ["task suite has no task with planted_trap: true"]
    return []


def _check_matrix_wiring(task_ids: List[str], model_ids: Dict[str, str]) -> List[str]:
    problems = []
    try:
        cells = build_matrix(list(model_ids.keys()), list(ALL_SCAFFOLDS), model_ids)
    except ValueError as exc:
        return [f"matrix: {exc}"]
    if len(cells) != len(model_ids) * len(ALL_SCAFFOLDS):
        problems.append(f"matrix: expected {len(model_ids) * len(ALL_SCAFFOLDS)} cells, built {len(cells)}")
    if not task_ids:
        problems.append("matrix: no tasks available to run against the cells")
    return problems
