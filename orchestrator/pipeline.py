"""The wired spine: freeform input -> intent-router classify/route ->
spec-engine intake -> Plan -> REAL authenticated approval gate ->
spec-engine finalize -> spec_engine.codegen.generate_app().

`run_pipeline()` is the ONE function that glues all three components
together end to end — this is the first debt this epic closes: the three
spine components existed but were never wired into one callable flow.
Every hop below is real, working glue code calling INTO the existing
component APIs — nothing here reimplements classify/route/harvest/build/
codegen logic, and nothing here invents a new stub of its own. Where a
downstream hop is itself partially a stub (`spec_engine.codegen`'s
`service`/`integration` module honesty), that labeling rides through
unchanged in `CodegenResult.manifest` — this module makes no claim about
it either way.

    from orchestrator.adapters.local_identity import LocalIdentityApprovalGate
    from orchestrator.pipeline import run_pipeline

    gate = LocalIdentityApprovalGate()
    result = run_pipeline(
        "An app that tracks vendor invoices and flags overdue ones.",
        "intent-router/routing_table.example.yaml",
        gate,
        target_dir="/tmp/generated-app",
    )
    # result.status in {"generated", "rejected", "needs_clarification"}
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from intent_router.pipeline import continue_with_clarification, run_intent_router
from intent_router.types import RoutingDecision

from spec_engine.codegen import DEFAULT_TARGET_STACK, CodegenResult, generate_app
from spec_engine.integrations.from_intent_router import routing_context_from_decision
from spec_engine.pipeline import finalize_spec, run_intake_and_plan
from spec_engine.types import Approval, Plan, SpecDocument

from .approval_gate import ApprovalAuthenticationError, ApprovalGate

PathLike = Union[str, Path]
PathLikeOrFalse = Union[PathLike, bool, None]

DEFAULT_SOURCE_TYPE = "fragment"


class PipelineError(ValueError):
    """Fail loud for a wiring-level error raised by THIS module. A
    component's own error (IntentRouterError, SpecEngineError,
    ApprovalAuthenticationError) always surfaces as itself, never laundered
    into this type — a caller can still catch the specific failure."""


@dataclass
class PipelineResult:
    """Everything one `run_pipeline()` call produced. `status` is one of:

    - `"needs_clarification"` — intent-router's own one-clarifying-question
      contract fired and no answer was supplied; nothing past routing ran.
    - `"rejected"` — the approval gate's human decision was a rejection;
      no spec or app was built (a normal, expected outcome, not an error).
    - `"generated"` — the full pipeline ran end to end; `spec` and `codegen`
      are populated.
    """

    status: str
    decision: Optional[RoutingDecision] = None
    plan: Optional[Plan] = None
    approval: Optional[Approval] = None
    spec: Optional[SpecDocument] = None
    codegen: Optional[CodegenResult] = None
    clarifying_question: Optional[str] = None


def _route(
    input_text: str, routing_table_path: PathLike, *, mission_id, clarification_answer,
    force_route: bool, route_log_path: PathLikeOrFalse,
) -> RoutingDecision:
    decision = run_intent_router(
        input_text, routing_table_path, mission_id=mission_id, force=force_route,
        log_path=route_log_path,
    )
    if decision.ambiguous and clarification_answer is not None:
        decision = continue_with_clarification(
            decision, clarification_answer, routing_table_path, log_path=route_log_path,
        )
    return decision


def run_pipeline(
    input_text: str,
    routing_table_path: PathLike,
    approval_gate: ApprovalGate,
    *,
    target_dir: PathLike,
    source_type: str = DEFAULT_SOURCE_TYPE,
    mission_id: Optional[str] = None,
    clarification_answer: Optional[str] = None,
    force_route: bool = False,
    codegen_target_stack: str = DEFAULT_TARGET_STACK,
    route_log_path: PathLikeOrFalse = None,
    spec_log_path: PathLikeOrFalse = None,
) -> PipelineResult:
    """Run the full idea -> spec -> approval -> app pipeline once.

    Hop 1 (REAL): `intent_router.pipeline.run_intent_router()` classifies
    and routes `input_text`. If ambiguous and no `clarification_answer` is
    given (and `force_route` is False), this stops HONESTLY at
    `"needs_clarification"` — intent-router's own contract is "one
    clarifying question max, never silently guess" and this wiring does
    not override that.

    Hop 2 (REAL): `spec_engine.pipeline.run_intake_and_plan()` harvests
    `input_text` into a `Plan`, carrying the routing decision's provenance
    via `routing_context_from_decision()`.

    Hop 3 (REAL, the second debt this epic closes): `approval_gate.
    request_approval(plan)` blocks for a real, authenticated human
    decision; `approval_gate.verify()` independently re-checks the result
    BEFORE anything downstream runs. This is an ADDITIONAL control in
    front of `finalize_spec()` — it does not touch or weaken
    `spec_builder.build_spec()`'s own existing structural gate (an
    `Approval` matching `plan_id` with `approved=True` is still required).

    Hop 4 (REAL): `spec_engine.pipeline.finalize_spec()` builds the
    `SpecDocument` — only reachable past a verified Hop 3.

    Hop 5 (REAL codegen — with per-module honesty already labeled by
    `spec_engine.codegen` itself, see its manifest): `generate_app()`
    writes the running app to `target_dir`.
    """
    decision = _route(
        input_text, routing_table_path, mission_id=mission_id,
        clarification_answer=clarification_answer, force_route=force_route,
        route_log_path=route_log_path,
    )
    if decision.ambiguous:
        return PipelineResult(
            status="needs_clarification", decision=decision,
            clarifying_question=decision.clarifying_question,
        )

    routing_context = routing_context_from_decision(decision)
    plan = run_intake_and_plan(
        input_text, source_type, mission_id=decision.mission_id,
        routing_context=routing_context, log_path=spec_log_path,
    )

    approval = approval_gate.request_approval(plan)
    if not approval_gate.verify(approval):
        raise ApprovalAuthenticationError(
            f"approval {getattr(approval, 'approval_id', '?')!r} for plan "
            f"{plan.plan_id!r} failed authentication — refusing to build a spec "
            "or generate code from it"
        )

    spec = finalize_spec(
        plan, approved_by=approval.approved_by, approved=approval.approved,
        notes=approval.notes, log_path=spec_log_path,
    )
    if spec is None:
        return PipelineResult(status="rejected", decision=decision, plan=plan, approval=approval)

    codegen_result = generate_app(spec, target_dir, target_stack=codegen_target_stack)
    return PipelineResult(
        status="generated", decision=decision, plan=plan, approval=approval,
        spec=spec, codegen=codegen_result,
    )


__all__ = ["run_pipeline", "PipelineResult", "PipelineError", "DEFAULT_SOURCE_TYPE"]
