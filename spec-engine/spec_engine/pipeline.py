"""Top-level convenience entry points gluing the pieces together, mirroring
`intent_router.pipeline`'s two-call shape (`run_intent_router` /
`continue_with_clarification`): one call gets you to the human gate, a
SEPARATE call crosses it. This split is deliberate, not incidental — see
approval.py's module docstring on why the gate is a real control here, not
a formality collapsed into a single function signature.

    plan = run_intake_and_plan(input_text, source_type)
    # ... a human reviews plan.summary_for_approval and decides ...
    spec = finalize_spec(plan, approved_by="Xavier", approved=True)

## `finalize_spec()` vs. `finalize_spec_with_approval()`

As of the codegen-boundary hardening epic, `spec_builder.build_spec()`
requires a GATE-VERIFIABLE `Approval` (see its own module docstring and
`gate_approval.py`) — a bare `approval.record_approval(approved_by=...)`
call is no longer sufficient. Two entry points cross the gate, for two
different kinds of caller:

  - `finalize_spec(plan, approved_by=..., approved=..., notes=...)` —
    UNCHANGED call signature (one new optional `identity_dir` kwarg) for
    a caller that only has a plain approved_by/approved/notes decision
    and wants THIS package to mint a genuine, locally-signed approval on
    its behalf (`gate_approval.sign_local_approval()`). This is what
    tests, the eval harness, and `spec_engine.cli`'s `finalize` subcommand
    already do — none of them need to change.
  - `finalize_spec_with_approval(plan, approval, ...)` — for a caller
    that ALREADY HAS a real, independently-verified `Approval` object
    (e.g. `orchestrator.pipeline.run_pipeline()`, after its
    `ApprovalGate.request_approval()` + `.verify()` round-trip) and must
    NOT have it silently re-signed/re-minted with a fresh approval_id,
    timestamp, and nonce under a possibly-DIFFERENT identity scope than
    the one the approval was actually signed under.
"""

from __future__ import annotations

from typing import Optional, Union

from .content import SpecEngineError
from .gate_approval import sign_local_approval
from .intake import ModelAssistedHarvest, harvest_intake
from .plan_builder import build_plan
from .spec_builder import build_spec
from .spec_log import DEFAULT_APPROVALS_LOG_PATH, append_approval_note, append_plan, append_spec
from .types import Approval, Plan, RoutingContext, SpecDocument

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
    identity_dir: Optional[str] = None,
) -> Optional[SpecDocument]:
    """Cross the approval gate for `plan`. If `approved` is `True`, builds
    and logs a `SpecDocument` and returns it. If `approved` is `False`,
    logs the rejection and returns `None` — never raises on a legitimate
    rejection (that is a normal, expected outcome of human review, not an
    error condition).

    Mints a genuinely gate-verifiable `Approval` via `gate_approval.
    sign_local_approval()` (HMAC-signed with this OS account's local
    identity, content-hash-bound to `plan`) rather than the old bare
    `approval.record_approval()` — `build_spec()`'s own codegen-boundary
    re-verification (see its module docstring) requires this; a caller
    that already has an independently-produced, real `Approval` object
    (e.g. from an `orchestrator.approval_gate.ApprovalGate` adapter)
    should call `finalize_spec_with_approval()` instead, so it is not
    silently re-signed under a possibly-different identity scope. Pass
    `identity_dir` to scope the local signing key (tests/CI sandboxing;
    see `gate_identity.default_identity_dir()`).

    `log_path` controls the SPECS log sink; `approvals_log_path` is a
    SEPARATE, independent sink for the approval/rejection record itself.
    If not given at all, it follows `log_path`: `log_path=False` (a dry
    run — "don't persist anything") skips the approval note too; any
    other `log_path` gets its OWN default approvals sink
    (`specs/approvals.jsonl`) rather than silently sharing `log_path`'s
    file — the two record shapes are never interleaved into one stream
    unless a caller explicitly points both at the same path itself."""
    approval = sign_local_approval(
        plan, approved_by=approved_by, approved=approved, notes=notes, identity_dir=identity_dir,
    )
    return finalize_spec_with_approval(
        plan, approval, spec_id=spec_id, log_path=log_path,
        approvals_log_path=approvals_log_path, identity_dir=identity_dir,
    )


def finalize_spec_with_approval(
    plan: Plan,
    approval: Approval,
    *,
    spec_id: Optional[str] = None,
    log_path: PathLikeOrFalse = None,
    approvals_log_path=_UNSET,
    identity_dir: Optional[str] = None,
) -> Optional[SpecDocument]:
    """Cross the approval gate for `plan` using an ALREADY-CONSTRUCTED
    `approval` — unlike `finalize_spec()`, this does NOT mint a new
    signature; `approval` is logged and passed straight to `build_spec()`,
    which independently RE-verifies it against `plan`'s current content
    (see `gate_approval.verify_gate_approval()`). This is the entry point
    for a caller that already has a real, authenticated `Approval` (e.g.
    `orchestrator.pipeline.run_pipeline()`, after its `ApprovalGate.
    request_approval()` + `.verify()` round-trip) — routing that SAME
    object through here (rather than re-deriving one via `finalize_spec()`)
    preserves its original `approval_id`/`approved_at`/signature exactly
    as signed, and avoids silently re-signing under the WRONG identity
    scope (this function's default `identity_dir=None` would otherwise
    resolve to a different directory than whatever a non-default
    `ApprovalGate` adapter actually used).

    Same return/logging contract as `finalize_spec()`: `None` on a
    rejection (never raises), a `SpecDocument` on approval, `log_path`/
    `approvals_log_path` control the two independent log sinks."""
    if approvals_log_path is _UNSET:
        approvals_log_path = False if log_path is False else None
    if approvals_log_path is not False:
        append_approval_note(approval, approvals_log_path or DEFAULT_APPROVALS_LOG_PATH)
    if not approval.approved:
        return None
    spec = build_spec(plan, approval, spec_id=spec_id, identity_dir=identity_dir)
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
    identity_dir: Optional[str] = None,
) -> Optional[SpecDocument]:
    """Convenience wrapper for tests/scripts/evals that already know the
    approval decision up front (e.g. a scripted eval harness, or a
    real integration where a human's decision has already been captured
    upstream and is just being relayed through in one call). A live,
    interactive integration should call `run_intake_and_plan()` and
    `finalize_spec()` separately, with a real human in between — collapsing
    them here does not mean the gate stopped mattering, only that this
    particular caller already has the approval in hand. `finalize_spec()`
    still mints a genuine, gate-verifiable, content-hash-bound approval
    under the hood (see its own docstring) — `approved_by` here is a
    caller-supplied label, not proof of identity, exactly as documented;
    pass `identity_dir` to scope the local signing key (tests/CI)."""
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
        identity_dir=identity_dir,
    )


__all__ = [
    "run_intake_and_plan",
    "finalize_spec",
    "finalize_spec_with_approval",
    "run_spec_engine",
    "SpecEngineError",
]
