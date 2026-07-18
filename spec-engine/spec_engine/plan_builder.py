"""Turn an `IntakeHarvest` into a `Plan` — the artifact presented at the
approval gate. Deliverable (3): "Plan -> Xavier/user approval gate ->
complete spec generation." This module builds the FIRST half (the plan);
approval.py + spec_builder.py handle the gate and the second half.

**Connectors v1** (`docs/design/connectors-architecture.md` §6.2/§6.4):
`build_plan()` resolves `harvest.how_it_works.integrations` against the
connector registry HERE, at plan-build time — the one and only place
resolution ever runs (see `connector_resolver.py`'s module docstring for
why generate-time re-resolution would defeat the whole point). The
resolved surface rides on `Plan.resolved_connectors` and is folded into
`summary_for_approval` in plain language, so a human approving this plan
sees exactly which external calls they're approving before they approve
anything — never an abstract "3 integrations" count.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

from .connector_resolver import resolve_connectors
from .content import ResolvedConnector, new_id, utc_now_iso
from .intake import IntakeHarvest
from .types import Plan, RoutingContext

PathLike = Union[str, Path]


def _summarize_connectors(resolved_connectors: List[ResolvedConnector]) -> List[str]:
    """Plain-language lines for `summary_for_approval` — the design doc's
    own worked example (§6.4): *"This app will call Anthropic (spend-class)
    using the key in ANTHROPIC_API_KEY. 'Stripe' has no registered
    connector and will be generated as a non-functional labeled stub."*"""
    lines = []
    for rc in resolved_connectors:
        if rc.status == "resolved":
            side_effects = sorted({op.side_effect for op in rc.operations})
            lines.append(
                f"This app will call {rc.display_name or rc.connector_id} "
                f"({'/'.join(side_effects)}-class) using the key in "
                f"{'/'.join(rc.auth_env_vars)}."
            )
        else:
            lines.append(
                f"{rc.integration_name!r} has no registered connector and will be generated "
                "as a non-functional labeled stub (HTTP 501)."
            )
    return lines


def _summarize_for_approval(
    harvest: IntakeHarvest, open_question_count: int, resolved_connectors: List[ResolvedConnector]
) -> str:
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
    lines.extend(_summarize_connectors(resolved_connectors))
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
    registry_root: Optional[PathLike] = None,
) -> Plan:
    """Build a `Plan` from a harvest. Always succeeds for any valid
    `IntakeHarvest` (harvest_intake() itself never blocks — see its module
    docstring) — a Plan can always be produced and put in front of an
    approver, however thin the underlying idea is.

    `registry_root` overrides where `connector_resolver.resolve_connectors()`
    reads `connectors/registry/` from (default:
    `connector_resolver.default_registry_root()`) — tests use this to
    resolve against a throwaway fixture registry instead of this repo's
    real one; a caller integrating a non-default registry location should
    thread its own value through here."""
    plan_id = new_id("plan")
    created_at = utc_now_iso()
    resolved_connectors = resolve_connectors(harvest.how_it_works.integrations, registry_root=registry_root)
    summary_for_approval = _summarize_for_approval(harvest, len(harvest.open_questions), resolved_connectors)

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
        resolved_connectors=resolved_connectors,
    )
