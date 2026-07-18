"""Tests for spec_engine.approval — the human-in-the-loop gate record."""

from __future__ import annotations

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.approval import record_approval, reject_plan
from spec_engine.content import SpecEngineError
from spec_engine.intake import harvest_intake
from spec_engine.plan_builder import build_plan


def _plan():
    return build_plan(harvest_intake("An app that tracks invoices.", "fragment"))


def test_record_approval_requires_non_empty_approved_by():
    plan = _plan()
    with pytest.raises(SpecEngineError):
        record_approval(plan, approved_by="")


def test_record_approval_ties_to_the_plan_id():
    plan = _plan()
    approval = record_approval(plan, approved_by="Xavier")
    assert approval.plan_id == plan.plan_id
    assert approval.approved is True


def test_reject_plan_still_requires_an_attributed_approver():
    plan = _plan()
    with pytest.raises(SpecEngineError):
        reject_plan(plan, approved_by="")


def test_reject_plan_sets_approved_false():
    plan = _plan()
    approval = reject_plan(plan, approved_by="Xavier", notes="Not the right idea yet.")
    assert approval.approved is False
    assert approval.notes == "Not the right idea yet."
