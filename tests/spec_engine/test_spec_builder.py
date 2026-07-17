"""Tests for spec_engine.spec_builder — the real approval-gate enforcement."""

from __future__ import annotations

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.approval import record_approval
from spec_engine.content import SpecEngineError
from spec_engine.intake import harvest_intake
from spec_engine.plan_builder import build_plan
from spec_engine.spec_builder import build_spec


def _plan(text="An app that tracks invoices."):
    return build_plan(harvest_intake(text, "fragment"))


def test_build_spec_raises_on_unapproved_plan():
    plan = _plan()
    rejection = record_approval(plan, approved_by="Xavier", approved=False)
    with pytest.raises(SpecEngineError):
        build_spec(plan, rejection)


def test_build_spec_raises_on_mismatched_plan_id():
    plan_a = _plan("An app that tracks invoices.")
    plan_b = _plan("A different app entirely.")
    approval_for_a = record_approval(plan_a, approved_by="Xavier")
    with pytest.raises(SpecEngineError):
        build_spec(plan_b, approval_for_a)


def test_build_spec_copies_content_verbatim_from_the_plan():
    plan = _plan()
    approval = record_approval(plan, approved_by="Xavier")
    spec = build_spec(plan, approval)
    assert spec.what_it_does == plan.what_it_does
    assert spec.how_it_looks == plan.how_it_looks
    assert spec.how_it_works == plan.how_it_works
    assert spec.data_model == plan.data_model
    assert spec.open_questions == plan.open_questions


def test_build_spec_sets_provenance_from_plan_and_approval():
    plan = _plan()
    approval = record_approval(plan, approved_by="Xavier", notes="Looks good.")
    spec = build_spec(plan, approval)
    assert spec.provenance.plan_id == plan.plan_id
    assert spec.provenance.approved_by == "Xavier"
    assert spec.provenance.source_type == plan.source_type
    assert spec.status == "active"
    assert spec.spec_version == 1


def test_build_spec_title_falls_back_to_input_excerpt_when_summary_is_thin():
    plan = _plan("x")
    approval = record_approval(plan, approved_by="Xavier")
    spec = build_spec(plan, approval)
    assert spec.title.strip() != ""
