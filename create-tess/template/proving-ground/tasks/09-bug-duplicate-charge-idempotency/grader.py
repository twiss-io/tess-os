"""Grader for 09-bug-duplicate-charge-idempotency."""
from __future__ import annotations

from pathlib import Path

from pg_lib.grading import run_pytest_in_workdir
from pg_lib.types import GradeResult


def grade(workdir: Path) -> GradeResult:
    return run_pytest_in_workdir(workdir, test_files=["test_payments.py"])
