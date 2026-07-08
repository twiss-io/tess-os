"""Grader for 01-bug-average-empty-list.

Protected-path enforcement (test_calc.py must stay untouched) is already
handled generically by `pg_lib.grading.grade_task` before this module is
even called — this file only needs to run the fixture's own test.
"""
from __future__ import annotations

from pathlib import Path

from pg_lib.grading import run_pytest_in_workdir
from pg_lib.types import GradeResult


def grade(workdir: Path) -> GradeResult:
    return run_pytest_in_workdir(workdir, test_files=["test_calc.py"])
