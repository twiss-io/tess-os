"""The one place spec_engine and intent_router actually meet: adapting an
intent-router `RoutingDecision` into a spec_engine `RoutingContext`.

Epic E2's own dependency line: "Dependencies: E1 (intake routes to it)."
This module is that composition, made concrete — how the front door's
output becomes the spec engine's input.

Deliberately duck-typed, NOT `isinstance`-checked against
`intent_router.types.RoutingDecision`: this file does not `import
intent_router` at module load time, so spec_engine keeps zero hard import
dependency on the sibling component (per spec-engine/README.md
"Independent deployability"). A caller that HAS both packages installed
(the common case — see tests/spec_engine/test_intent_router_bridge.py for
a real end-to-end proof) passes a real `RoutingDecision` in; a caller that
only has spec_engine can pass anything with the same five attributes.
"""

from __future__ import annotations

from ..types import RoutingContext


def routing_context_from_decision(decision) -> RoutingContext:
    """Build a `RoutingContext` from any object exposing `decision_id`,
    `mission_id`, `entry_command`, `orchestrator`, and `outcome_type`
    attributes — the shape `intent_router.types.RoutingDecision` has.
    Raises `AttributeError` (fails loud) if `decision` is missing any of
    them, rather than silently defaulting fields to `None`."""
    return RoutingContext(
        decision_id=decision.decision_id,
        mission_id=decision.mission_id,
        entry_command=decision.entry_command,
        orchestrator=decision.orchestrator,
        outcome_type=decision.outcome_type,
    )
