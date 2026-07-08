"""Grader for 15-research-cascading-billing.

Pure JSON comparison against the pinned answer_key.json (computed by the
task author's reference script and committed alongside the fixture). A
small float tolerance covers the 1-dp average; strings compare
case-insensitively.
"""
from __future__ import annotations

from pathlib import Path

from pg_lib.grading import compare_answer_json
from pg_lib.types import GradeResult

TASK_DIR = Path(__file__).resolve().parent


def grade(workdir: Path) -> GradeResult:
    return compare_answer_json(workdir, answer_key_path=TASK_DIR / "answer_key.json", float_tolerance=0.05)
