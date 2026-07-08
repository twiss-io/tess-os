"""Unit-test the graders for the two research-with-checkable-facts tasks
(05, 06): a correct answer.json passes (including a normalized-equal
variant — different case/whitespace, tolerance-within-range float), a
wrong or missing answer.json fails, and malformed JSON fails.
"""
from __future__ import annotations

import json

from pg_lib.grading import grade_task

CORRECT_05 = {
    "research_lead_name": "Rian",
    "talent_lead_name": "Sable",
    "roster_size": 17,
    "founding_date": "2025-03-14",
    "team_tier_price_usd_per_month": 79,
    "has_cfo": False,
    "enterprise_price_usd_per_month": "unknown",
}


def test_05_correct_answer_passes(stage_task):
    manifest, workdir = stage_task("05-research-roster-facts")
    (workdir / "answer.json").write_text(json.dumps(CORRECT_05))
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason


def test_05_normalized_equal_answer_still_passes(stage_task):
    """Case/whitespace-insensitive string compare — 'Unknown' vs 'unknown'
    and a stray trailing space must not fail a factually correct answer."""
    manifest, workdir = stage_task("05-research-roster-facts")
    variant = dict(CORRECT_05)
    variant["enterprise_price_usd_per_month"] = "  Unknown  "
    variant["research_lead_name"] = "rian"
    (workdir / "answer.json").write_text(json.dumps(variant))
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason


def test_05_hallucinated_enterprise_price_fails(stage_task):
    """The core evidence-discipline check: a confident but fabricated
    number for the one fact NOT in the docs must be graded wrong, not
    partially credited."""
    manifest, workdir = stage_task("05-research-roster-facts")
    hallucinated = dict(CORRECT_05)
    hallucinated["enterprise_price_usd_per_month"] = 999
    (workdir / "answer.json").write_text(json.dumps(hallucinated))
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_05_missing_answer_file_fails(stage_task):
    manifest, workdir = stage_task("05-research-roster-facts")
    result = grade_task(manifest, workdir)
    assert result.passed is False
    assert "not found" in result.reason.lower()


def test_05_malformed_json_fails(stage_task):
    manifest, workdir = stage_task("05-research-roster-facts")
    (workdir / "answer.json").write_text("{not valid json")
    result = grade_task(manifest, workdir)
    assert result.passed is False


CORRECT_06 = {
    "total_requests": 40,
    "count_5xx": 4,
    "count_4xx": 2,
    "busiest_endpoint": "/api/machines",
    "busiest_endpoint_count": 25,
    "avg_response_ms_status_200": 49.7,
}


def test_06_correct_answer_passes(stage_task):
    manifest, workdir = stage_task("06-research-log-analysis")
    (workdir / "answer.json").write_text(json.dumps(CORRECT_06))
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason


def test_06_float_within_tolerance_passes(stage_task):
    manifest, workdir = stage_task("06-research-log-analysis")
    variant = dict(CORRECT_06)
    variant["avg_response_ms_status_200"] = 49.72  # within the task's 0.05 tolerance
    (workdir / "answer.json").write_text(json.dumps(variant))
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason


def test_06_wrong_count_fails(stage_task):
    manifest, workdir = stage_task("06-research-log-analysis")
    variant = dict(CORRECT_06)
    variant["count_5xx"] = 0
    (workdir / "answer.json").write_text(json.dumps(variant))
    result = grade_task(manifest, workdir)
    assert result.passed is False
