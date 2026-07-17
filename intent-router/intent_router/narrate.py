"""Deterministic narration templating: the "here's what I'm doing and why"
text the epic requires ("It must NARRATE its choice ... never make the
user pick a slash command"). Pure string templating — no model call, so
this is fully unit-testable on hand-built `RoutingDecision` objects.
"""

from __future__ import annotations

from .types import RoutingDecision


def narrate(decision: RoutingDecision) -> str:
    if decision.ambiguous:
        lines = [
            "I'm not confident enough yet to just pick an entry point for you.",
        ]
        if decision.clarifying_question:
            lines.append(decision.clarifying_question)
        return "\n".join(lines)

    lines = []
    where = f"`{decision.entry_command}`"
    if decision.orchestrator:
        where += f" (orchestrator: `{decision.orchestrator}`)"
    lines.append(
        f"Routing this to {where} — outcome type: `{decision.outcome_type}`."
    )
    if decision.matched_signals:
        lines.append(f"Why: matched on {', '.join(decision.matched_signals)}.")
    if decision.confidence is not None:
        lines.append(f"Confidence: {decision.confidence:.2f}.")
    if decision.assumption_stated:
        lines.append(decision.assumption_stated)
    return "\n".join(lines)


def build_clarifying_question(top, second) -> str:
    """`top`/`second` are `ScoredCandidate`s (see classifier.py). Produces
    the ONE clarifying question the epic allows ("Ambiguity → one
    clarifying question max, then route with stated assumption")."""
    if second is None:
        return (
            f"I want to route this to `{top.route.entry_command}` "
            f"({top.route.description}) but I'm not fully confident yet — "
            "is that the right fit, or is there more context you can give me?"
        )
    return (
        f"This could be a '{top.route.outcome_type}' need "
        f"(→ `{top.route.entry_command}`: {top.route.description}) or a "
        f"'{second.route.outcome_type}' need (→ `{second.route.entry_command}`: "
        f"{second.route.description}). Which is closer to what you're actually after?"
    )


def build_assumption(top, second) -> str:
    """The stated assumption the epic requires when a second clarifying
    question would otherwise be needed ("... then route with stated
    assumption")."""
    basis = ", ".join(top.matched_signals) if top.matched_signals else "the overall shape of your message"
    return (
        f"No second signal resolved the ambiguity, so I'm assuming this is "
        f"primarily a '{top.route.outcome_type}' need based on {basis}, and "
        f"routing to `{top.route.entry_command}`. Tell me if that's wrong and "
        "I'll re-route."
    )
