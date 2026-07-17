"""Tests for the routing engine: confident routing, ambiguity handling
(exactly one clarifying question, then a forced route with a stated
assumption), and mission-id plumbing."""

from __future__ import annotations

import pytest

import _paths  # noqa: F401 -- sys.path bootstrap, see _paths.py docstring
from _paths import example_routing_table  # noqa: F401 -- pytest fixture, used by parameter name

from intent_router import ExternalSignal, Route, RoutingTable
from intent_router.router import resolve_clarification, route


def _two_route_table():
    a = Route(
        id="alpha",
        entry_command="/alpha",
        outcome_type="build",
        description="Alpha route",
        keywords=["alpha signal"],
    )
    b = Route(
        id="beta",
        entry_command="/beta",
        outcome_type="convert",
        description="Beta route",
        keywords=["beta signal"],
    )
    return RoutingTable([a, b])


def test_confident_route_returns_non_ambiguous_decision(example_routing_table):
    decision = route(
        "I'm seriously considering opening up in a completely new country next year, "
        "is that a smart expansion move for us right now?",
        example_routing_table,
    )
    assert decision.ambiguous is False
    assert decision.route_id == "strategic-mode"
    assert decision.entry_command == "/strategic-mode"
    assert decision.orchestrator == "strategic-growth-orchestrator"
    assert decision.clarifying_question is None
    assert decision.crew_plan_sketch is not None
    assert decision.narration


def test_low_signal_input_is_ambiguous_and_asks_exactly_one_question(example_routing_table):
    decision = route("hello", example_routing_table)
    assert decision.ambiguous is True
    assert decision.clarifying_question is not None
    assert decision.crew_plan_sketch is None
    assert decision.assumption_stated is None


def test_close_scoring_candidates_are_ambiguous():
    a = Route(id="a", entry_command="/a", outcome_type="build", keywords=["shared term"])
    b = Route(id="b", entry_command="/b", outcome_type="convert", keywords=["shared term"])
    table = RoutingTable([a, b])
    decision = route("there is a shared term right here", table, ambiguity_margin=0.5)
    assert decision.ambiguous is True
    assert decision.runner_up_route_id in ("a", "b")


def test_resolve_clarification_never_asks_a_second_question(example_routing_table):
    first = route("hello", example_routing_table)
    assert first.ambiguous is True

    second = resolve_clarification(
        first,
        "It's about whether we should expand into a brand new country market.",
        example_routing_table,
    )
    assert second.ambiguous is False
    assert second.clarifying_question is None
    # forced decisions must ALWAYS carry a route, never leave the caller stuck
    assert second.route_id is not None


def test_resolve_clarification_states_an_assumption_when_still_ambiguous():
    a = Route(id="a", entry_command="/a", outcome_type="build", keywords=["shared term"])
    b = Route(id="b", entry_command="/b", outcome_type="convert", keywords=["shared term"])
    table = RoutingTable([a, b])
    first = route("there is a shared term right here", table, ambiguity_margin=0.5)
    assert first.ambiguous is True

    second = resolve_clarification(first, "still not sure honestly", table, ambiguity_margin=0.5)
    assert second.ambiguous is False
    assert second.assumption_stated is not None
    assert second.route_id is not None


def test_resolve_clarification_rejects_a_non_ambiguous_prior_decision(example_routing_table):
    confident = route("we need to build a new feature and finish the roadmap", example_routing_table)
    assert confident.ambiguous is False
    with pytest.raises(ValueError):
        resolve_clarification(confident, "anything", example_routing_table)


def test_force_flag_skips_ambiguity_and_states_assumption():
    table = _two_route_table()
    decision = route("no matching signal at all here", table, force=True)
    assert decision.ambiguous is False
    assert decision.assumption_stated is not None
    assert decision.route_id is not None


def test_mission_id_is_passed_through_when_provided(example_routing_table):
    decision = route(
        "we need to build a new feature and finish the roadmap",
        example_routing_table,
        mission_id="2026-07-17-my-custom-mission",
    )
    assert decision.mission_id == "2026-07-17-my-custom-mission"
    assert decision.crew_plan_sketch["mission_id"] == "2026-07-17-my-custom-mission"


def test_mission_id_falls_back_to_a_generated_slug_when_absent(example_routing_table):
    decision = route(
        "we need to build a new feature and finish the roadmap",
        example_routing_table,
    )
    assert decision.mission_id is not None
    assert decision.mission_id.startswith("intent-router-")


def test_external_signal_can_tip_a_route_that_keywords_alone_would_miss(example_routing_table):
    # Deliberately generic input with no strong keyword signal for any route.
    vague_input = "we should really talk about where this is all going long term"
    unaided = route(vague_input, example_routing_table)
    assert unaided.ambiguous is True  # weak/no signal without help

    signal = ExternalSignal(
        suggested_route_id="founder-mode",
        confidence=0.9,
        reasoning="Reads as a founder-level direction question.",
    )
    aided = route(vague_input, example_routing_table, external_signal=signal, force=True)
    assert aided.route_id == "founder-mode"


def test_narration_is_populated_for_confident_decisions(example_routing_table):
    decision = route(
        "our conversion rate dropped and the sales pipeline is empty",
        example_routing_table,
    )
    assert decision.narration
    assert decision.entry_command in decision.narration


def test_narration_carries_the_clarifying_question_when_ambiguous(example_routing_table):
    decision = route("hello", example_routing_table)
    assert decision.clarifying_question in decision.narration
