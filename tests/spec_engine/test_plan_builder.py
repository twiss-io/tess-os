"""Tests for spec_engine.plan_builder."""

from __future__ import annotations

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.content import is_valid_slug
from spec_engine.intake import harvest_intake
from spec_engine.plan_builder import build_plan
from spec_engine.types import RoutingContext


def test_build_plan_produces_a_safe_slug_plan_id():
    harvest = harvest_intake("An app that tracks invoices.", "fragment")
    plan = build_plan(harvest)
    assert is_valid_slug(plan.plan_id)


def test_build_plan_truncates_input_excerpt_to_280_chars():
    long_text = "An app that tracks invoices. " * 20
    harvest = harvest_intake(long_text, "fragment")
    plan = build_plan(harvest)
    assert len(plan.input_excerpt) <= 280


def test_build_plan_carries_routing_context_through():
    harvest = harvest_intake("An app that tracks invoices.", "fragment")
    rc = RoutingContext(decision_id="dec-1", entry_command="/product-mode", orchestrator="product-delivery-orchestrator", outcome_type="build")
    plan = build_plan(harvest, routing_context=rc)
    assert plan.routing_context is rc


def test_build_plan_summary_for_approval_mentions_open_question_count():
    harvest = harvest_intake("An app that tracks invoices.", "fragment")
    plan = build_plan(harvest)
    assert f"{len(harvest.open_questions)} open question(s)" in plan.summary_for_approval


def test_build_plan_never_blocks_on_any_non_empty_harvest():
    """Deliverable (2): 'harvesting ambiguities... rather than demanding a
    finished brief.' A Plan must always be producible."""
    for text, source in [
        ("x", "fragment"),
        ("An app that does a thing, I think, not totally sure though.", "voice_transcript"),
        ("A fully detailed structured brief with everything specified.", "structured_brief"),
    ]:
        harvest = harvest_intake(text, source)
        plan = build_plan(harvest)
        assert plan.plan_id
