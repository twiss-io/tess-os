"""The routing engine: classify -> decide (confident / ambiguous) -> build a
crew-plan sketch -> narrate. This is the deterministic core the epic asks
to be "testable separately" from any model call — every function here is a
pure function of its inputs plus the routing table.

Ambiguity handling implements the epic's exact rule verbatim: "Ambiguity ->
one clarifying question max, then route with stated assumption." A single
`route()` call either returns a confident decision, or an ambiguous one
carrying exactly one clarifying question. A second call — via
`resolve_clarification()` — is FORCED (`force=True` internally) and can
never itself return a second clarifying question; if the combined input
is still ambiguous it picks the top candidate and states the assumption
instead of asking again.
"""

from __future__ import annotations

from typing import Optional

from .classifier import classify
from .crew_plan_sketch import build_sketch, default_notes
from .narrate import build_assumption, build_clarifying_question, narrate
from .routing_table import RoutingTable
from .types import ExternalSignal, RoutingDecision, new_decision_id, utc_now_iso

DEFAULT_MIN_CONFIDENCE = 0.35
DEFAULT_AMBIGUITY_MARGIN = 0.12


def default_mission_id(input_text: str, decision_id: str) -> str:
    """A safe, deterministic-enough mission id sketch callers can use if
    they have no real mission ledger id yet. Real integrations (e.g. a
    future `tessctl mission new` wiring) should pass their own id via
    `mission_id=` instead — this is a fallback, not a mission-ledger
    substitute (`missions/**` is out of scope for this component; see
    README 'Integration status')."""
    return f"intent-router-{decision_id[:12]}"


def _ambiguous_decision(top, second, *, decision_id, timestamp, input_text, mission_id) -> RoutingDecision:
    decision = RoutingDecision(
        decision_id=decision_id,
        timestamp=timestamp,
        input_text=input_text,
        ambiguous=True,
        route_id=top.route.id,
        entry_command=top.route.entry_command,
        orchestrator=top.route.orchestrator,
        outcome_type=top.route.outcome_type,
        confidence=top.confidence,
        matched_signals=top.matched_signals,
        runner_up_route_id=second.route.id if second else None,
        clarifying_question=build_clarifying_question(top, second),
        assumption_stated=None,
        crew_plan_sketch=None,
        narration="",
        mission_id=mission_id,
    )
    decision.narration = narrate(decision)
    return decision


def _confident_decision(
    top, second, *, decision_id, timestamp, input_text, mission_id, assumption
) -> RoutingDecision:
    decision = RoutingDecision(
        decision_id=decision_id,
        timestamp=timestamp,
        input_text=input_text,
        ambiguous=False,
        route_id=top.route.id,
        entry_command=top.route.entry_command,
        orchestrator=top.route.orchestrator,
        outcome_type=top.route.outcome_type,
        confidence=top.confidence,
        matched_signals=top.matched_signals,
        runner_up_route_id=second.route.id if second else None,
        clarifying_question=None,
        assumption_stated=assumption,
        crew_plan_sketch=build_sketch(
            top.route, mission_id, notes=default_notes(top.route, top.matched_signals)
        ),
        narration="",
        mission_id=mission_id,
    )
    decision.narration = narrate(decision)
    return decision


def route(
    input_text: str,
    routing_table: RoutingTable,
    *,
    external_signal: Optional[ExternalSignal] = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ambiguity_margin: float = DEFAULT_AMBIGUITY_MARGIN,
    mission_id: Optional[str] = None,
    force: bool = False,
) -> RoutingDecision:
    """Route one freeform input to an entry point.

    `force=True` skips the ambiguity check entirely: the top candidate is
    always chosen, and if it would otherwise have been ambiguous, the
    returned decision carries `assumption_stated` instead of
    `clarifying_question`. This is what `resolve_clarification()` uses so a
    SECOND clarifying question is structurally impossible.
    """
    candidates = classify(input_text, routing_table, external_signal)
    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None

    would_be_ambiguous = top.confidence < min_confidence or (
        second is not None and (top.confidence - second.confidence) < ambiguity_margin
    )
    decision_id = new_decision_id()
    timestamp = utc_now_iso()

    if would_be_ambiguous and not force:
        return _ambiguous_decision(
            top, second, decision_id=decision_id, timestamp=timestamp,
            input_text=input_text, mission_id=mission_id,
        )

    resolved_mission_id = mission_id or default_mission_id(input_text, decision_id)
    assumption = build_assumption(top, second) if (would_be_ambiguous and force) else None
    return _confident_decision(
        top, second, decision_id=decision_id, timestamp=timestamp,
        input_text=input_text, mission_id=resolved_mission_id, assumption=assumption,
    )


def resolve_clarification(
    prior_decision: RoutingDecision,
    clarification_answer: str,
    routing_table: RoutingTable,
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ambiguity_margin: float = DEFAULT_AMBIGUITY_MARGIN,
) -> RoutingDecision:
    """Resolve a prior ambiguous decision using the user's one-line answer
    to the single clarifying question that was asked. This is ALWAYS
    forced — it never returns a second `clarifying_question` (epic: "one
    clarifying question max, then route with stated assumption")."""
    if not prior_decision.ambiguous:
        raise ValueError("resolve_clarification() called on a non-ambiguous decision")
    combined_input = f"{prior_decision.input_text}\n{clarification_answer}"
    return route(
        combined_input,
        routing_table,
        min_confidence=min_confidence,
        ambiguity_margin=ambiguity_margin,
        mission_id=prior_decision.mission_id,
        force=True,
    )
