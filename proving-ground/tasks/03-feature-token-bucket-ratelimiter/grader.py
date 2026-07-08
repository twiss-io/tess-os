"""Grader for 03-feature-token-bucket-ratelimiter.

Uses the manifest's `hidden_tests` entry rather than a fixture-shipped
test file — the agent never sees the grading suite.
"""
from __future__ import annotations

from pathlib import Path

from pg_lib.grading import run_pytest_in_workdir
from pg_lib.types import GradeResult

TASK_DIR = Path(__file__).resolve().parent


def grade(workdir: Path) -> GradeResult:
    return run_pytest_in_workdir(
        workdir,
        test_files=[],
        hidden_test_sources=[TASK_DIR / "hidden_test_ratelimiter.py"],
    )
