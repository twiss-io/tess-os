"""Turn an `IntakeHarvest` into a `Plan` — the artifact presented at the
approval gate. Deliverable (3): "Plan -> Xavier/user approval gate ->
complete spec generation." This module builds the FIRST half (the plan);
approval.py + spec_builder.py handle the gate and the second half.
"""

from __future__ import annotations

from typing import Optional

from .content import new_id, utc_now_iso
from .intake import IntakeHarvest
from .types import Plan, RoutingContext


def _summarize_for_approval(harvest: IntakeHarvest, open_question_count: int) -> str:
    """Human-readable text a real approver reads before approving —
    mirrors intent_router.narrate's "here's what I'm doing and why"
    discipline: plain language, never a raw data dump."""
    lines = [
        f"What it does: {harvest.what_it_does.summary or '(not yet clear from the input)'}",
    ]
    if harvest.how_it_looks.description:
        lines.append(f"How it looks: {harvest.how_it_looks.description}")
    if harvest.how_it_works.description:
        lines.append(f"How it works: {harvest.how_it_works.description}")
    if harvest.data_model.entities:
        entity_names = ", ".join(e.name for e in harvest.data_model.entities)
        lines.append(f"Data model: {entity_names}")
    lines.append(
        f"{open_question_count} open question(s) harvested into the ledger — "
        "none of them block this plan from being approved; they carry forward "
        "into the spec for whoever builds from it."
    )
    return "\n".join(lines)


def build_plan(
    harvest: IntakeHarvest,
    *,
    mission_id: Optional[str] = None,
    routing_context: Optional[RoutingContext] = None,
) -> Plan:
    """Build a `Plan` from a harvest. Always succeeds for any valid
    `IntakeHarvest` (harvest_intake() itself never blocks — see its module
    docstring) — a Plan can always be produced and put in front of an
    approver, however thin the underlying idea is."""
    plan_id = new_id("plan")
    created_at = utc_now_iso()
    summary_for_approval = _summarize_for_approval(harvest, len(harvest.open_questions))

    return Plan(
        plan_id=plan_id,
        mission_id=mission_id,
        created_at=created_at,
        source_type=harvest.source_type,
        input_excerpt=harvest.input_text[:280],
        what_it_does=harvest.what_it_does,
        how_it_looks=harvest.how_it_looks,
        how_it_works=harvest.how_it_works,
        data_model=harvest.data_model,
        non_goals=list(harvest.non_goals),
        acceptance_criteria=list(harvest.acceptance_criteria),
        open_questions=list(harvest.open_questions),
        routing_context=routing_context,
        summary_for_approval=summary_for_approval,
    )
