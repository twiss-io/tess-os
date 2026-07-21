"""Unit-test the grader for the cascading research task (15). A correct
answer.json passes; a cascade-wrong answer (wrong busiest month, so every
downstream number is wrong) fails; including failed/refunded rows in
revenue fails; and a missing answer.json fails.
"""
from __future__ import annotations

import json

from pg_lib.grading import grade_task

CORRECT_15 = {
    "busiest_month": "2026-02",
    "captured_count": 14,
    "gross_revenue_cents": 23290,
    "avg_captured_cents": 1663.6,
}


def test_15_correct_answer_passes(stage_task):
    manifest, workdir = stage_task("15-research-cascading-billing")
    (workdir / "answer.json").write_text(json.dumps(CORRECT_15))
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason


def test_15_wrong_busiest_month_cascade_fails(stage_task):
    """Picking 2026-03 (highest revenue, but NOT the busiest by count)
    cascades to wrong numbers everywhere downstream."""
    manifest, workdir = stage_task("15-research-cascading-billing")
    wrong = {
        "busiest_month": "2026-03",
        "captured_count": 10,
        "gross_revenue_cents": 61200,
        "avg_captured_cents": 6120.0,
    }
    (workdir / "answer.json").write_text(json.dumps(wrong))
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_15_revenue_including_excluded_rows_fails(stage_task):
    """Right month, but revenue that included the failed/refunded rows."""
    manifest, workdir = stage_task("15-research-cascading-billing")
    wrong = dict(CORRECT_15)
    wrong["gross_revenue_cents"] = 23290 + 9900 + 1200 - 1000 - 2500  # added failed, kept refunds
    (workdir / "answer.json").write_text(json.dumps(wrong))
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_15_missing_answer_file_fails(stage_task):
    manifest, workdir = stage_task("15-research-cascading-billing")
    result = grade_task(manifest, workdir)
    assert result.passed is False
    assert "not found" in result.reason.lower()
