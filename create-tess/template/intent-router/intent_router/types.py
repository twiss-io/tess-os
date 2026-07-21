"""Core data types for the intent router.

Spec: TESS-VISION-AND-BUILD-SPEC.html, Phase 1, Epic E1 ("Intent Router —
'Tess Picks the Command'"). This module intentionally has zero dependency
on any specific deployment's command set, orchestrator roster, or model
provider — it is the generalized contract every routing table, classifier,
and caller in this package shares.

`OUTCOME_TYPES` and `GATES` are copied VERBATIM (not re-derived) from this
repo's own `core/contracts/crew-plan.schema.json` (`Stage.gate_in` enum,
`outcome_type` enum) — one vocabulary, not two. A drift-detection test
(`tests/intent_router/test_crew_plan_sketch.py`) reads that schema file at
test time and asserts these two tuples still match it byte-for-byte, so if
the framework's real vocabulary ever changes, this module's copy is caught
out of date rather than silently diverging.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Verbatim copy of core/contracts/crew-plan.schema.json's `outcome_type` enum.
OUTCOME_TYPES = (
    "decide",
    "design",
    "build",
    "convert",
    "recover",
    "govern",
    "review",
    "communicate",
    "scale",
)

# Verbatim copy of core/contracts/crew-plan.schema.json's `Stage.gate_in` enum
# (== conductor/doctrine.md "The Gates" table, five canonical gate names).
GATES = (
    "intake-before-anything",
    "research-before-build",
    "crew-before-deploy",
    "review-before-synthesis",
    "verification-before-externally-visible",
)

# Same safe-slug pattern crew-plan.schema.json's own `Task.id`/`mission_id`
# fields use: lowercase-alnum first char, then alnum/'.'/'_'/'-' only. No '/'
# or '\\' can ever validate, so a route id can never escape a path join.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def is_valid_slug(value: str) -> bool:
    return bool(value) and bool(_SLUG_RE.match(value))


class IntentRouterError(ValueError):
    """Base class for all intent-router validation errors. Fail loud, never
    silently coerce a malformed route/table/signal into something plausible-
    looking."""


@dataclass(frozen=True)
class Route(object):
    """One entry in a routing table: an internal command/orchestrator pair
    the router can select, plus the signal vocabulary (keywords/examples)
    the deterministic classifier scores freeform input against.

    `entry_command` and `orchestrator` are deliberately free-text strings,
    not an enum tied to any one deployment's 26 commands / 6 orchestrators
    — a different tess-os instance can ship a completely different routing
    table without changing a line of this module.
    """

    id: str
    entry_command: str
    outcome_type: str
    description: str = ""
    orchestrator: Optional[str] = None
    default_guilds: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not is_valid_slug(self.id):
            raise IntentRouterError(
                f"Route id {self.id!r} is not a safe slug (must match {_SLUG_RE.pattern!r})"
            )
        if self.outcome_type not in OUTCOME_TYPES:
            raise IntentRouterError(
                f"Route {self.id!r} has outcome_type {self.outcome_type!r}, "
                f"must be one of {OUTCOME_TYPES}"
            )
        if not self.entry_command:
            raise IntentRouterError(f"Route {self.id!r} must have a non-empty entry_command")


@dataclass(frozen=True)
class ExternalSignal(object):
    """Optional structured output from a model-assisted classification pass
    (e.g. an LLM reading the freeform input inside a live Claude Code
    session). NEVER required to route — the router is fully deterministic
    and unit-testable without one; this is the hook point a caller uses
    to make classification more nuanced without making the mapping from
    signal to entry point non-deterministic or untestable.

    See intent-router/README.md "Model-assisted classification" for the
    contract a caller should produce.
    """

    outcome_type: Optional[str] = None
    suggested_route_id: Optional[str] = None
    confidence: float = 0.0
    reasoning: str = ""

    def __post_init__(self) -> None:
        if self.outcome_type is not None and self.outcome_type not in OUTCOME_TYPES:
            raise IntentRouterError(
                f"ExternalSignal.outcome_type {self.outcome_type!r} must be one "
                f"of {OUTCOME_TYPES} or None"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise IntentRouterError("ExternalSignal.confidence must be within [0.0, 1.0]")


@dataclass
class ScoredCandidate(object):
    """One route's deterministic score against a given input."""

    route: Route
    raw_score: float
    confidence: float
    matched_signals: List[str] = field(default_factory=list)


@dataclass
class RoutingDecision(object):
    """The router's final (or in-progress, if ambiguous) output. This is the
    object the narration and decision-log modules both read from — no
    caller reconstructs routing facts from the narration string.
    """

    decision_id: str
    timestamp: str
    input_text: str
    ambiguous: bool
    route_id: Optional[str] = None
    entry_command: Optional[str] = None
    orchestrator: Optional[str] = None
    outcome_type: Optional[str] = None
    confidence: Optional[float] = None
    matched_signals: List[str] = field(default_factory=list)
    runner_up_route_id: Optional[str] = None
    clarifying_question: Optional[str] = None
    assumption_stated: Optional[str] = None
    crew_plan_sketch: Optional[Dict[str, Any]] = None
    narration: str = ""
    mission_id: Optional[str] = None

    def to_log_record(self) -> Dict[str, Any]:
        """The exact shape schema/routing-decision.schema.json validates.
        `input_text` is truncated to a 280-char excerpt — the log is a
        routing rationale record, not a durable transcript store."""
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp,
            "input_excerpt": self.input_text[:280],
            "ambiguous": self.ambiguous,
            "route_id": self.route_id,
            "entry_command": self.entry_command,
            "orchestrator": self.orchestrator,
            "outcome_type": self.outcome_type,
            "confidence": self.confidence,
            "matched_signals": list(self.matched_signals),
            "runner_up_route_id": self.runner_up_route_id,
            "clarifying_question": self.clarifying_question,
            "assumption_stated": self.assumption_stated,
            "crew_plan_sketch": self.crew_plan_sketch,
            "narration": self.narration,
            "mission_id": self.mission_id,
        }


def new_decision_id() -> str:
    return uuid.uuid4().hex


def utc_now_iso() -> str:
    """UTC ISO-8601 with a millisecond-precision 'Z' suffix — the same
    timestamp convention core/contracts/mission.schema.json documents for
    `created_at`."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
