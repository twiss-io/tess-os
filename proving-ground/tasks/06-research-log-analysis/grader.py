"""Grader for 06-research-log-analysis."""
from __future__ import annotations

from pathlib import Path

from pg_lib.grading import compare_answer_json
from pg_lib.types import GradeResult

TASK_DIR = Path(__file__).resolve().parent


def grade(workdir: Path) -> GradeResult:
    return compare_answer_json(workdir, answer_key_path=TASK_DIR / "answer_key.json", float_tolerance=0.05)
