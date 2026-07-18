"""Tests for deterministic narration templating."""

from __future__ import annotations

import _paths  # noqa: F401 -- sys.path bootstrap, see _paths.py docstring

from intent_router.narrate import build_assumption, build_clarifying_question, narrate
from intent_router.types import RoutingDecision


def _confident_decision(**overrides):
    defaults = dict(
        decision_id="d1",
        timestamp="2026-07-17T00:00:00.000Z",
        input_text="build a new feature",
        ambiguous=False,
        route_id="product-mode",
        entry_command="/product-mode",
        orchestrator="product-delivery-orchestrator",
        outcome_type="build",
        confidence=0.8,
        matched_signals=["feature", "roadmap"],
    )
    defaults.update(overrides)
    return RoutingDecision(**defaults)


def test_narrate_confident_decision_names_entry_point_and_reason():
    decision = _confident_decision()
    text = narrate(decision)
    assert "/product-mode" in text
    assert "product-delivery-orchestrator" in text
    assert "build" in text
    assert "feature" in text
    assert "0.80" in text


def test_narrate_includes_stated_assumption_when_present():
    decision = _confident_decision(assumption_stated="Assuming X because Y.")
    text = narrate(decision)
    assert "Assuming X because Y." in text


def test_narrate_ambiguous_decision_surfaces_the_clarifying_question():
    decision = RoutingDecision(
        decision_id="d2",
        timestamp="2026-07-17T00:00:00.000Z",
        input_text="hello",
        ambiguous=True,
        clarifying_question="Is this about X or Y?",
    )
    text = narrate(decision)
    assert "Is this about X or Y?" in text
    assert "not confident" in text.lower()


class _FakeCandidate:
    def __init__(self, route, matched_signals=None):
        self.route = route
        self.matched_signals = matched_signals or []


class _FakeRoute:
    def __init__(self, entry_command, description, outcome_type):
        self.entry_command = entry_command
        self.description = description
        self.outcome_type = outcome_type


def test_build_clarifying_question_with_two_candidates_names_both():
    top = _FakeCandidate(_FakeRoute("/founder-mode", "Founder strategy", "decide"))
    second = _FakeCandidate(_FakeRoute("/strategic-mode", "Market expansion", "scale"))
    question = build_clarifying_question(top, second)
    assert "/founder-mode" in question
    assert "/strategic-mode" in question
    assert "decide" in question
    assert "scale" in question


def test_build_clarifying_question_with_no_second_candidate_asks_for_more_context():
    top = _FakeCandidate(_FakeRoute("/help", "Help", "communicate"))
    question = build_clarifying_question(top, None)
    assert "/help" in question
    assert "more context" in question.lower()


def test_build_assumption_cites_matched_signals_when_present():
    top = _FakeCandidate(_FakeRoute("/revenue-mode", "Revenue work", "convert"), matched_signals=["pricing"])
    assumption = build_assumption(top, None)
    assert "pricing" in assumption
    assert "/revenue-mode" in assumption


def test_build_assumption_falls_back_when_no_matched_signals():
    top = _FakeCandidate(_FakeRoute("/revenue-mode", "Revenue work", "convert"), matched_signals=[])
    assumption = build_assumption(top, None)
    assert "overall shape" in assumption
