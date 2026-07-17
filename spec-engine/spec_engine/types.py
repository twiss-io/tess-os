"""Pipeline-stage contract types: `Plan` (pre-approval draft), `Approval`
(the human-in-the-loop gate record), `SpecDocument` (the post-approval
source of truth), and `ScaffoldPlan` (the spec->scaffold stub's output
shape). Content dataclasses (WhatItDoes/HowItLooks/HowItWorks/DataModel/
OpenQuestion) live in content.py; this module is the wrapper around them.

Spec: TESS-VISION-AND-BUILD-SPEC.html, Phase 1, Epic E2.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .content import (
    DataModel,
    HowItLooks,
    HowItWorks,
    OpenQuestion,
    SpecEngineError,
    WhatItDoes,
    is_valid_slug,
)

SOURCE_TYPES = ("voice_transcript", "pasted_doc", "fragment", "structured_brief")
SPEC_STATUSES = ("active", "superseded")
MODULE_KINDS = ("backend-model", "frontend-page", "service", "integration", "test-suite")
CODEGEN_STATUSES = ("not_started",)  # v1 is a stub — see scaffold.py module docstring

# Verbatim copy of core/contracts/crew-plan.schema.json's `outcome_type`
# enum, same as intent_router.types.OUTCOME_TYPES — one vocabulary, not
# two. Duplicated (not imported) to keep spec-engine's import graph free
# of intent-router; tests/spec_engine/test_types.py carries the same
# drift-detection test intent-router's own suite does against the live
# schema, so a future change to the real enum is caught here too.
ROUTING_OUTCOME_TYPES = (
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


@dataclass(frozen=True)
class RoutingContext:
    """Duck-typed adapter target for an intent-router `RoutingDecision`.
    spec_engine has ZERO import dependency on the `intent_router` package
    (each top-level tess-os component stays independently deployable) —
    see integrations/from_intent_router.py for the thin adapter that
    builds one of these FROM a real `intent_router.types.RoutingDecision`
    by reading attributes, not by isinstance-checking against that
    package's class."""

    decision_id: Optional[str] = None
    mission_id: Optional[str] = None
    entry_command: Optional[str] = None
    orchestrator: Optional[str] = None
    outcome_type: Optional[str] = None

    def __post_init__(self) -> None:
        if self.outcome_type is not None and self.outcome_type not in ROUTING_OUTCOME_TYPES:
            raise SpecEngineError(
                f"RoutingContext.outcome_type {self.outcome_type!r} must be "
                f"one of {ROUTING_OUTCOME_TYPES} or None"
            )


@dataclass(frozen=True)
class Provenance:
    """Where a spec came from and who approved it — the governance half of
    Pillar 02 made concrete: every generated app's spec must be traceable
    back to the raw input and the human who approved the plan it was
    built from, not just to a model's say-so."""

    source_type: str
    input_excerpt: str
    approved_by: str
    approved_at: str
    generated_at: str
    plan_id: str
    routing_decision_id: Optional[str] = None
    entry_command: Optional[str] = None
    orchestrator: Optional[str] = None
    mission_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.source_type not in SOURCE_TYPES:
            raise SpecEngineError(
                f"Provenance.source_type {self.source_type!r} must be one of {SOURCE_TYPES}"
            )
        if not self.approved_by.strip():
            raise SpecEngineError("Provenance.approved_by must be non-empty")
        if not is_valid_slug(self.plan_id):
            raise SpecEngineError(f"Provenance.plan_id {self.plan_id!r} is not a safe slug")


@dataclass
class Plan:
    """The pre-approval draft: harvested content + the open-questions
    ledger, plus a human-readable summary for the approval gate. This is
    NOT yet a `SpecDocument` — approval is what promotes it into the
    source of truth (see spec_builder.build_spec). A Plan is always
    producible from ANY non-empty input, however minimal or rambling —
    see intake.py's module docstring for why this pipeline never blocks
    on incomplete input."""

    plan_id: str
    mission_id: Optional[str]
    created_at: str
    source_type: str
    input_excerpt: str
    what_it_does: WhatItDoes
    how_it_looks: HowItLooks
    how_it_works: HowItWorks
    data_model: DataModel
    non_goals: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    open_questions: List[OpenQuestion] = field(default_factory=list)
    routing_context: Optional[RoutingContext] = None
    summary_for_approval: str = ""

    def __post_init__(self) -> None:
        if not is_valid_slug(self.plan_id):
            raise SpecEngineError(f"Plan.plan_id {self.plan_id!r} is not a safe slug")
        if self.source_type not in SOURCE_TYPES:
            raise SpecEngineError(f"Plan.source_type {self.source_type!r} must be one of {SOURCE_TYPES}")

    def to_log_record(self) -> Dict[str, Any]:
        """The exact shape schema/plan.schema.json validates."""
        record = asdict(self)
        record["open_question_count"] = len(self.open_questions)
        return record


@dataclass
class Approval:
    """The human-in-the-loop gate record. Deliverable (3): 'Plan ->
    Xavier/user approval gate -> complete spec generation.' `approved_by`
    is required even on a rejection — every decision on a plan must be
    attributable, never anonymous. This dataclass never decides anything
    itself; it only RECORDS a decision a human (or an explicitly-named
    caller acting on one) already made — see approval.py."""

    approval_id: str
    plan_id: str
    approved: bool
    approved_by: str
    approved_at: str
    notes: str = ""

    def __post_init__(self) -> None:
        if not is_valid_slug(self.plan_id):
            raise SpecEngineError(f"Approval.plan_id {self.plan_id!r} is not a safe slug")
        if not self.approved_by.strip():
            raise SpecEngineError("Approval.approved_by must be non-empty — no anonymous approvals")


@dataclass
class SpecDocument:
    """The post-approval source of truth — the SPEC.md contract. 'Code is
    generated from spec, never the reverse' (Pillar 02): everything
    downstream (scaffold.py, and eventually real codegen) reads FROM a
    SpecDocument; nothing writes back into one except a future explicit
    spec-diff regeneration flow (Epic E5, out of scope here — see
    render.py and scaffold.py for exactly where this v1 stops)."""

    spec_id: str
    title: str
    spec_version: int
    status: str
    provenance: Provenance
    what_it_does: WhatItDoes
    how_it_looks: HowItLooks
    how_it_works: HowItWorks
    data_model: DataModel
    non_goals: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    open_questions: List[OpenQuestion] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not is_valid_slug(self.spec_id):
            raise SpecEngineError(f"SpecDocument.spec_id {self.spec_id!r} is not a safe slug")
        if not self.title.strip():
            raise SpecEngineError("SpecDocument.title must be non-empty")
        if self.spec_version < 1:
            raise SpecEngineError("SpecDocument.spec_version must be >= 1")
        if self.status not in SPEC_STATUSES:
            raise SpecEngineError(f"SpecDocument.status {self.status!r} must be one of {SPEC_STATUSES}")

    def to_log_record(self) -> Dict[str, Any]:
        """The exact shape schema/spec.schema.json validates — also the
        literal content of the `spec.json` artifact scaffold.py writes
        alongside the rendered SPEC.md."""
        return asdict(self)


@dataclass(frozen=True)
class ScaffoldModule:
    module_id: str
    source_section: str
    kind: str
    description: str = ""
    depends_on: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not is_valid_slug(self.module_id):
            raise SpecEngineError(f"ScaffoldModule.module_id {self.module_id!r} is not a safe slug")
        if self.kind not in MODULE_KINDS:
            raise SpecEngineError(f"ScaffoldModule.kind {self.kind!r} must be one of {MODULE_KINDS}")


@dataclass
class ScaffoldPlan:
    """Deliverable (3): the spec->scaffold DIRECTION, as a stub. This is a
    PLAN for what a future real codegen step would produce, not code
    itself — `codegen_status` is always `"not_started"` in v1 (see
    scaffold.py module docstring for the honest-labeling rationale, same
    discipline the parent build spec applies everywhere else: 'these
    labels are load-bearing... do not silently upgrade a label')."""

    spec_id: str
    spec_version: int
    generated_at: str
    modules: List[ScaffoldModule] = field(default_factory=list)
    target_stack: str = "unspecified"
    codegen_status: str = "not_started"
    notes: str = ""

    def __post_init__(self) -> None:
        if not is_valid_slug(self.spec_id):
            raise SpecEngineError(f"ScaffoldPlan.spec_id {self.spec_id!r} is not a safe slug")
        if self.spec_version < 1:
            raise SpecEngineError("ScaffoldPlan.spec_version must be >= 1")
        if self.codegen_status not in CODEGEN_STATUSES:
            raise SpecEngineError(
                f"ScaffoldPlan.codegen_status {self.codegen_status!r} must be one of {CODEGEN_STATUSES}"
            )

    def to_log_record(self) -> Dict[str, Any]:
        """The exact shape schema/scaffold-plan.schema.json validates."""
        return asdict(self)
