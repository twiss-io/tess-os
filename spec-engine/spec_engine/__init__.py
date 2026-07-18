"""spec_engine — the idea -> spec -> app core of Tess OS
(TESS-VISION-AND-BUILD-SPEC.html Phase 1, Epic E2, "Spec Engine v1: Idea ->
Complete Spec").

Public API:

    from spec_engine import (
        harvest_intake, ModelAssistedHarvest,
        build_plan, record_approval, reject_plan, build_spec,
        render_markdown, lint, plan_scaffold_from_spec, write_scaffold_stub,
        run_intake_and_plan, finalize_spec, run_spec_engine,
    )

See spec-engine/README.md for the full component contract and how it
composes with intent-router (the front door).
"""

from .approval import record_approval, reject_plan
from .connector_resolver import default_registry_root, resolve_connectors
from .content import (
    DataModel,
    Entity,
    EntityField,
    HowItLooks,
    HowItWorks,
    KeyFlow,
    KeyScreen,
    OpenQuestion,
    ResolvedConnector,
    ResolvedConnectorOperation,
    SpecEngineError,
    WhatItDoes,
    plan_content_hash,
)
from .gate_approval import (
    ApprovalReplayError,
    ApprovalVerificationError,
    GateVerifiedApproval,
    sign_local_approval,
    verify_gate_approval,
)
from .intake import IntakeHarvest, ModelAssistedHarvest, harvest_intake
from .pipeline import finalize_spec, finalize_spec_with_approval, run_intake_and_plan, run_spec_engine
from .plan_builder import build_plan
from .render import render_markdown
from .scaffold import plan_scaffold_from_spec, write_scaffold_stub
from .spec_builder import build_spec
from .spec_lint import LintFinding, has_blocking_errors, lint
from .spec_log import append_approval_note, append_plan, append_spec, read_jsonl
from .types import (
    Approval,
    Plan,
    Provenance,
    RoutingContext,
    ScaffoldModule,
    ScaffoldPlan,
    SpecDocument,
)

__all__ = [
    "record_approval",
    "reject_plan",
    "default_registry_root",
    "resolve_connectors",
    "DataModel",
    "Entity",
    "EntityField",
    "HowItLooks",
    "HowItWorks",
    "KeyFlow",
    "KeyScreen",
    "OpenQuestion",
    "ResolvedConnector",
    "ResolvedConnectorOperation",
    "SpecEngineError",
    "WhatItDoes",
    "plan_content_hash",
    "ApprovalReplayError",
    "ApprovalVerificationError",
    "GateVerifiedApproval",
    "sign_local_approval",
    "verify_gate_approval",
    "IntakeHarvest",
    "ModelAssistedHarvest",
    "harvest_intake",
    "finalize_spec",
    "finalize_spec_with_approval",
    "run_intake_and_plan",
    "run_spec_engine",
    "build_plan",
    "render_markdown",
    "plan_scaffold_from_spec",
    "write_scaffold_stub",
    "build_spec",
    "LintFinding",
    "has_blocking_errors",
    "lint",
    "append_approval_note",
    "append_plan",
    "append_spec",
    "read_jsonl",
    "Approval",
    "Plan",
    "Provenance",
    "RoutingContext",
    "ScaffoldModule",
    "ScaffoldPlan",
    "SpecDocument",
]

__version__ = "0.1.0"
