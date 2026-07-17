"""Top-level convenience entry points gluing the pieces together, mirroring
`intent_router.pipeline`'s two-call shape (`run_intent_router` /
`continue_with_clarification`): one call gets you to the human gate, a
SEPARATE call crosses it. This split is deliberate, not incidental — see
approval.py's module docstring on why the gate is a real control here, not
a formality collapsed into a single function signature.

    plan = run_intake_and_plan(input_text, source_type)
    # ... a human reviews plan.summary_for_approval and decides ...
    spec = finalize_spec(plan, approved_by="Xavier", approved=True)
"""

from __future__ import annotations

from typing import Optional, Union

from .approval import record_approval
from .content import SpecEngineError
from .intake import ModelAssistedHarvest, harvest_intake
from .plan_builder import build_plan
from .spec_builder import build_spec
from .spec_log import DEFAULT_APPROVALS_LOG_PATH, append_approval_note, append_plan, append_spec
from .types import Plan, RoutingContext, SpecDocument

PathLikeOrFalse = Union[str, bool, None]

_UNSET = object()  # sentinel distinguishing "not passed" from an explicit None/False


def run_intake_and_plan(
    input_text: str,
    source_type: str,
    *,
    mission_id: Optional[str] = None,
    routing_context: Optional[RoutingContext] = None,
    model_assisted: Optional[ModelAssistedHarvest] = None,
    log_path: PathLikeOrFalse = None,
) -> Plan:
    """Harvest `input_text` and build the `Plan` an approver reviews. Pass
    `log_path=False` to skip writing to the plans log (e.g. a dry run);
    omit it (or pass `None`) to use the component's default sink."""
    harvest = harvest_intake(input_text, source_type, model_assisted=model_assisted)
    plan = build_plan(harvest, mission_id=mission_id, routing_context=routing_context)
    if log_path is not False:
        append_plan(plan, log_path)
    return plan


def finalize_spec(
    plan: Plan,
    *,
    approved_by: str,
    approved: bool = True,
    notes: str = "",
    spec_id: Optional[str] = None,
    log_path: PathLikeOrFalse = None,
    approvals_log_path=_UNSET,
) -> Optional[SpecDocument]:
    """Cross the approval gate for `plan`. If `approved` is `True`, builds
    and logs a `SpecDocument` and returns it. If `approved` is `False`,
    logs the rejection and returns `None` — never raises on a legitimate
    rejection (that is a normal, expected outcome of human review, not an
    error condition).

    `log_path` controls the SPECS log sink; `approvals_log_path` is a
    SEPARATE, independent sink for the approval/rejection record itself.
    If not given at all, it follows `log_path`: `log_path=False` (a dry
    run — "don't persist anything") skips the approval note too; any
    other `log_path` gets its OWN default approvals sink
    (`specs/approvals.jsonl`) rather than silently sharing `log_path`'s
    file — the two record shapes are never interleaved into one stream
    unless a caller explicitly points both at the same path itself."""
    if approvals_log_path is _UNSET:
        approvals_log_path = False if log_path is False else None
    approval = record_approval(plan, approved_by=approved_by, approved=approved, notes=notes)
    if approvals_log_path is not False:
        append_approval_note(approval, approvals_log_path or DEFAULT_APPROVALS_LOG_PATH)
    if not approval.approved:
        return None
    spec = build_spec(plan, approval, spec_id=spec_id)
    if log_path is not False:
        append_spec(spec, log_path)
    return spec


def run_spec_engine(
    input_text: str,
    source_type: str,
    *,
    approved_by: str,
    mission_id: Optional[str] = None,
    routing_context: Optional[RoutingContext] = None,
    model_assisted: Optional[ModelAssistedHarvest] = None,
    approved: bool = True,
    notes: str = "",
    log_path: PathLikeOrFalse = None,
) -> Optional[SpecDocument]:
    """Convenience wrapper for tests/scripts/evals that already know the
    approval decision up front (e.g. a scripted eval harness, or a
    real integration where a human's decision has already been captured
    upstream and is just being relayed through in one call). A live,
    interactive integration should call `run_intake_and_plan()` and
    `finalize_spec()` separately, with a real human in between — collapsing
    them here does not mean the gate stopped mattering, only that this
    particular caller already has the approval in hand."""
    plan = run_intake_and_plan(
        input_text,
        source_type,
        mission_id=mission_id,
        routing_context=routing_context,
        model_assisted=model_assisted,
        log_path=log_path,
    )
    return finalize_spec(
        plan,
        approved_by=approved_by,
        approved=approved,
        notes=notes,
        log_path=log_path,
    )


__all__ = [
    "run_intake_and_plan",
    "finalize_spec",
    "run_spec_engine",
    "SpecEngineError",
]
