"""Tests for spec_engine.pipeline — the two-call gated flow plus the
scripted-convenience wrapper."""

from __future__ import annotations

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.pipeline import finalize_spec, run_intake_and_plan, run_spec_engine
from spec_engine.spec_log import read_jsonl


def test_run_intake_and_plan_never_raises_on_thin_input():
    plan = run_intake_and_plan("x", "fragment", log_path=False)
    assert plan.plan_id


def test_finalize_spec_returns_none_on_rejection_not_an_exception():
    plan = run_intake_and_plan("An app that tracks invoices.", "fragment", log_path=False)
    result = finalize_spec(plan, approved_by="Xavier", approved=False, log_path=False)
    assert result is None


def test_finalize_spec_returns_a_spec_on_approval():
    plan = run_intake_and_plan("An app that tracks invoices.", "fragment", log_path=False)
    spec = finalize_spec(plan, approved_by="Xavier", log_path=False)
    assert spec is not None
    assert spec.provenance.plan_id == plan.plan_id


def test_run_spec_engine_end_to_end_convenience():
    spec = run_spec_engine(
        "An app that tracks invoices and nudges clients.", "fragment", approved_by="Xavier", log_path=False,
    )
    assert spec is not None
    assert spec.provenance.approved_by == "Xavier"


def test_run_spec_engine_rejection_path_returns_none():
    spec = run_spec_engine("An app idea.", "fragment", approved_by="Xavier", approved=False, log_path=False)
    assert spec is None


def test_pipeline_logs_plan_and_spec_to_a_custom_log_path(tmp_path):
    log_path = tmp_path / "specs.jsonl"
    plan_log_path = tmp_path / "plans.jsonl"
    plan = run_intake_and_plan("An app that tracks invoices.", "fragment", log_path=plan_log_path)
    spec = finalize_spec(plan, approved_by="Xavier", log_path=log_path)

    assert spec is not None
    plans_logged = list(read_jsonl(plan_log_path))
    specs_logged = list(read_jsonl(log_path))
    assert len(plans_logged) == 1
    assert plans_logged[0]["plan_id"] == plan.plan_id
    assert len(specs_logged) == 1
    assert specs_logged[0]["spec_id"] == spec.spec_id


def test_pipeline_never_blocks_across_the_three_input_styles():
    """Deliverable (2) + Epic E2 acceptance criterion, exercised directly:
    every input style must reach a spec (given approval) with no
    exception raised."""
    inputs = [
        ("A fully detailed app idea with clear scope.", "structured_brief"),
        ("um, so, I think maybe it should work like this, not sure though?", "voice_transcript"),
        ("A single terse idea in one paragraph.", "fragment"),
    ]
    for text, source in inputs:
        spec = run_spec_engine(text, source, approved_by="Xavier", log_path=False)
        assert spec is not None
