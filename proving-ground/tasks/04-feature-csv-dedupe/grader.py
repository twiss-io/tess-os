"""Grader for 04-feature-csv-dedupe."""
from __future__ import annotations

from pathlib import Path

from pg_lib.grading import run_pytest_in_workdir
from pg_lib.types import GradeResult

TASK_DIR = Path(__file__).resolve().parent


def grade(workdir: Path) -> GradeResult:
    return run_pytest_in_workdir(
        workdir,
        test_files=[],
        hidden_test_sources=[TASK_DIR / "hidden_test_dedupe.py"],
    )
