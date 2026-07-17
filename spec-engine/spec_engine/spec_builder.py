"""Promote an approved `Plan` into a `SpecDocument` — the source of truth.
Deliverable (3), final step: "... -> complete spec generation."

This is the one place the approval gate is actually enforced as a real
control, not a formality: `build_spec()` refuses to run — raises
`SpecEngineError`, fails loud — unless it is handed an `Approval` whose
`plan_id` matches the plan being built AND whose `approved` is `True`.
There is no code path in this package that reaches a `SpecDocument`
without both of those being true.
"""

from __future__ import annotations

from typing import Optional

from .content import SpecEngineError, new_id, utc_now_iso
from .types import Plan, Approval, Provenance, SpecDocument


def build_spec(plan: Plan, approval: Approval, *, spec_id: Optional[str] = None, spec_version: int = 1) -> SpecDocument:
    """Build a `SpecDocument` from `plan`, gated on `approval`.

    Raises `SpecEngineError` if:
      - `approval.plan_id != plan.plan_id` (approval for a different plan)
      - `approval.approved is not True` (rejected or not yet decided)

    The spec's content is copied verbatim from the plan's draft content —
    approval is a gate on WHETHER to proceed, never a silent rewrite of
    WHAT was approved. `spec_version` defaults to 1 (a fresh spec); a
    future spec-diff regeneration flow (Epic E5) would pass a higher
    value when superseding a prior version — out of scope here.
    """
    if approval.plan_id != plan.plan_id:
        raise SpecEngineError(
            f"Approval {approval.approval_id!r} is for plan {approval.plan_id!r}, "
            f"not the plan being built ({plan.plan_id!r})"
        )
    if not approval.approved:
        raise SpecEngineError(
            f"Plan {plan.plan_id!r} was not approved (approval {approval.approval_id!r}, "
            f"approved_by={approval.approved_by!r}) — no spec can be built from an unapproved plan"
        )

    title = (plan.what_it_does.summary or plan.input_excerpt or "Untitled").strip()
    title = (title[:97] + "...") if len(title) > 100 else title

    provenance = Provenance(
        source_type=plan.source_type,
        input_excerpt=plan.input_excerpt,
        approved_by=approval.approved_by,
        approved_at=approval.approved_at,
        generated_at=utc_now_iso(),
        plan_id=plan.plan_id,
        routing_decision_id=plan.routing_context.decision_id if plan.routing_context else None,
        entry_command=plan.routing_context.entry_command if plan.routing_context else None,
        orchestrator=plan.routing_context.orchestrator if plan.routing_context else None,
        mission_id=plan.mission_id,
    )

    return SpecDocument(
        spec_id=spec_id or new_id("spec"),
        title=title,
        spec_version=spec_version,
        status="active",
        provenance=provenance,
        what_it_does=plan.what_it_does,
        how_it_looks=plan.how_it_looks,
        how_it_works=plan.how_it_works,
        data_model=plan.data_model,
        non_goals=list(plan.non_goals),
        acceptance_criteria=list(plan.acceptance_criteria),
        open_questions=list(plan.open_questions),
    )
