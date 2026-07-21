"""intent_router — the deterministic core of Tess OS's orchestrator
front door (TESS-VISION-AND-BUILD-SPEC.html Phase 1, Epic E1).

Public API:

    from intent_router import RoutingTable, ExternalSignal, route, resolve_clarification
    from intent_router import run_intent_router, continue_with_clarification

See intent-router/README.md for the full component contract.
"""

from .classifier import classify, score_route
from .crew_plan_sketch import build_sketch
from .decision_log import append_decision, read_decisions
from .narrate import narrate
from .pipeline import continue_with_clarification, run_intent_router
from .router import resolve_clarification, route
from .routing_table import RoutingTable, RoutingTableError
from .types import (
    GATES,
    OUTCOME_TYPES,
    ExternalSignal,
    IntentRouterError,
    Route,
    RoutingDecision,
    ScoredCandidate,
)

__all__ = [
    "classify",
    "score_route",
    "build_sketch",
    "append_decision",
    "read_decisions",
    "narrate",
    "continue_with_clarification",
    "run_intent_router",
    "resolve_clarification",
    "route",
    "RoutingTable",
    "RoutingTableError",
    "GATES",
    "OUTCOME_TYPES",
    "ExternalSignal",
    "IntentRouterError",
    "Route",
    "RoutingDecision",
    "ScoredCandidate",
]

__version__ = "0.1.0"
