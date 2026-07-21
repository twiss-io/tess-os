"""The wired spine: freeform input -> intent-router classify/route ->
spec-engine intake -> Plan -> REAL authenticated approval gate ->
spec-engine finalize -> spec_engine.codegen.generate_app() -> OPT-IN
activation/retention telemetry (see `docs/TELEMETRY.md`) -> OPTIONAL,
opt-in Agent Receipt emission (see `mission_receipt.py`, and
`docs/AGENT_RECEIPT_SPEC.md`).

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

The final REQUIRED hop, `telemetry.events.record_mission_completion()`, is
the ONE call site in this repo for local, OPT-IN activation/retention
instrumentation — OFF by default, no-op unless a human has run
`python -m telemetry.cli enable`. See `telemetry/README.md` and
`docs/TELEMETRY.md` for the full privacy contract.

Hop 7 (OPTIONAL, opt-in, wedge-loop epic addition), right after Hop 6,
`_emit_governed_mission_receipt()` writes one locally HMAC-signed
`decision_kind: "local_approval"` Agent Receipt for this mission when the
caller supplies `receipt_path` — the ONE call site in this repo where a
codegen run itself (not only a GPG verdict/sign-off, see `tools/
receipt-emit/`) produces a receipt. Off by default (`receipt_path=None`);
see `mission_receipt.py`'s module docstring for the full trust-level
disclosure and its disclosed genesis-only scope.

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

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

from intent_router.pipeline import continue_with_clarification, run_intent_router
from intent_router.types import RoutingDecision

from spec_engine.codegen import DEFAULT_TARGET_STACK, CodegenResult, generate_app
from spec_engine.integrations.from_intent_router import routing_context_from_decision
from spec_engine.pipeline import finalize_spec_with_approval, run_intake_and_plan
from spec_engine.types import Approval, Plan, SpecDocument

from telemetry.consent import TelemetryError
from telemetry.events import MissionCompletionEvent, record_mission_completion

from . import mission_receipt
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

    `telemetry` is populated ONLY on `"generated"` — see `_record_
    governed_mission_telemetry()`'s own docstring below for exactly what
    it records (OPT-IN, OFF by default; see `docs/TELEMETRY.md`).
    `MissionCompletionEvent(recorded=False)` (the default when telemetry
    is disabled, which it is for every caller that has not explicitly
    run `python -m telemetry.cli enable`) is NOT an error — most callers
    of this function will see exactly that, forever, and that is the
    correct, private-by-default outcome.

    `receipt` is populated ONLY on `"generated"`, and ONLY when the caller
    supplied `receipt_path` (see `_emit_governed_mission_receipt()`'s own
    docstring below — OPT-IN, OFF by default; `None` in every other case,
    including a receipt-emission failure, which is downgraded to a
    non-fatal warning rather than raised).
    """

    status: str
    decision: Optional[RoutingDecision] = None
    plan: Optional[Plan] = None
    approval: Optional[Approval] = None
    spec: Optional[SpecDocument] = None
    codegen: Optional[CodegenResult] = None
    clarifying_question: Optional[str] = None
    telemetry: Optional[MissionCompletionEvent] = None
    receipt: Optional[Dict[str, Any]] = None


def _identity_dir_hint(approval_gate: ApprovalGate) -> Optional[Path]:
    """Best-effort, DUCK-TYPED extraction of the local identity directory
    an approval was actually signed under, IF `approval_gate` exposes one
    (the shipped `LocalIdentityApprovalGate` does, via its `.identity`
    property). This is threaded into `finalize_spec_with_approval()`'s
    `identity_dir` so `build_spec()`'s own codegen-boundary
    re-verification (`spec_engine.gate_approval.verify_gate_approval()`)
    resolves the SAME key the approval was signed with — not silently
    falling back to this process's DEFAULT `~/.tess-os/approval-identity`
    (wrong for any gate scoped to a non-default `identity_dir`, e.g.
    every test in this suite, or a real deployment intentionally isolating
    key material outside the default location).

    Returns `None` for any adapter that doesn't expose this (a future
    non-local-HMAC mechanism — Telegram/web/SSO — has no such concept);
    `build_spec()`'s own re-verification falls back to ITS OWN default in
    that case, exactly as it does for any direct `spec_engine` caller
    that doesn't pass `identity_dir` either. Not an `isinstance` check —
    mirrors this repo's existing duck-typed-adapter discipline (see
    `spec_engine.integrations.from_intent_router`'s module docstring)."""
    identity = getattr(approval_gate, "identity", None)
    key_path = getattr(identity, "key_path", None)
    return key_path.parent if key_path is not None else None


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


def _record_governed_mission_telemetry() -> Optional[MissionCompletionEvent]:
    """Fire the OPT-IN activation/retention event for this `run_pipeline()`
    call reaching `"generated"` — the ONE integration point in this repo
    for `telemetry.events.record_mission_completion()`. This is called
    AFTER `generate_app()` has already succeeded, i.e. AFTER the full
    accountability chain (a human approval, independently re-verified,
    -> a finalized spec -> a generated app) has already, fully,
    completed — telemetry observes that fact; it never gates it.

    `record_mission_completion()` self-gates on `telemetry.consent.
    is_enabled()` and is a complete, instant no-op — nothing counted,
    timestamped, or written — when the user has not explicitly opted in
    (see that function's own docstring and `docs/TELEMETRY.md`). A
    `TelemetryError` (a corrupt local consent/events file — the only
    exception this call can raise) is caught here and downgraded to a
    non-fatal stderr warning, mirroring `docs/OBSERVABILITY.md`'s own
    tessctl-trace precedent: "a trace-log write failure must never flip
    the exit code of the security-critical command it is merely
    observing." An optional telemetry sidecar failing must never
    retroactively un-complete a governed mission that already, genuinely,
    finished."""
    try:
        return record_mission_completion()
    except TelemetryError as exc:
        print(f"WARNING: telemetry not recorded (non-fatal): {exc}", file=sys.stderr)
        return None


def _emit_governed_mission_receipt(
    plan: Plan, approval: Approval, spec: SpecDocument, target_dir: PathLike,
    approval_gate: ApprovalGate, receipt_path: PathLikeOrFalse,
) -> Optional[Dict[str, Any]]:
    """OPTIONAL, opt-in Hop 7: emit one locally HMAC-signed `decision_kind:
    "local_approval"` Agent Receipt (`core/contracts/agent-receipt.schema.
    json`, `docs/AGENT_RECEIPT_SPEC.md`) for this `run_pipeline()` call
    reaching `"generated"` — self-gated on `receipt_path` being supplied
    (falsy/`None` by default, mirroring `route_log_path`/`spec_log_path`'s
    own `PathLikeOrFalse` convention): most callers never pass
    `receipt_path`, and for them this is a complete, instant no-op, the
    same way Hop 6's telemetry is a no-op unless a human has explicitly
    opted in.

    Embeds the SAME `approval` object Hop 3/4 already authenticated and
    independently re-verified TWICE (`ApprovalGate.verify()`, then AGAIN
    at `spec_builder.build_spec()`'s codegen boundary) — this hop never
    re-decides or re-derives anything; it only RECORDS, mirroring Hop 6's
    own "telemetry observes that fact; it never gates it" discipline.
    `mission_receipt.MissionReceiptError` (an unusable local
    approval-identity key, or a filesystem error writing the receipt file
    — the only exception this call can raise) is caught here and
    downgraded to a non-fatal stderr warning, the exact same
    `docs/OBSERVABILITY.md` precedent `_record_governed_mission_telemetry()`
    already applies for Hop 6: an optional receipt failing must NEVER
    retroactively un-complete a governed mission that already, genuinely,
    finished."""
    if not receipt_path:
        return None
    try:
        receipt = mission_receipt.build_local_approval_receipt(
            plan=plan, approval=approval, spec=spec, target_dir=target_dir,
            identity_dir=_identity_dir_hint(approval_gate),
        )
        mission_receipt.write_receipt(receipt, receipt_path)
        return receipt
    except mission_receipt.MissionReceiptError as exc:
        print(f"WARNING: agent receipt not emitted (non-fatal): {exc}", file=sys.stderr)
        return None


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
    receipt_path: PathLikeOrFalse = None,
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
    decision; `approval_gate.verify(approval, plan)` independently
    re-checks the result — bound to `plan`'s actual content, not just its
    `plan_id` ([Cyra MEDIUM-2]) — BEFORE anything downstream runs. This
    is an ADDITIONAL control in front of `finalize_spec_with_approval()`
    — it does not replace `spec_builder.build_spec()`'s OWN
    codegen-boundary re-verification (an `Approval` matching `plan_id`,
    `approved=True`, AND independently gate-verified via `spec_engine.
    gate_approval.verify_gate_approval()` is required — see that
    module's docstring for [Cyra MEDIUM-1]). The SAME real, verified
    `approval` object is routed straight into
    `finalize_spec_with_approval()` below — never re-derived from its
    individual fields — so its original signature/content-hash survives
    intact to the codegen boundary's own re-check.

    Hop 4 (REAL): `spec_engine.pipeline.finalize_spec_with_approval()`
    builds the `SpecDocument` — only reachable past BOTH a verified Hop 3
    AND `build_spec()`'s own independent re-verification.

    Hop 5 (REAL codegen — with per-module honesty already labeled by
    `spec_engine.codegen` itself, see its manifest): `generate_app()`
    writes the running app to `target_dir`.

    Hop 6 (OPT-IN, OFF by default — see `docs/TELEMETRY.md`): once Hop 5
    succeeds, `_record_governed_mission_telemetry()` fires this install's
    activation (first-ever) or retention (repeat) event — a no-op unless
    a human has explicitly run `python -m telemetry.cli enable`.

    Hop 7 (OPTIONAL, opt-in, off unless `receipt_path` is given —
    wedge-loop epic addition, see `mission_receipt.py` and
    `docs/AGENT_RECEIPT_SPEC.md`): once Hop 5 succeeds,
    `_emit_governed_mission_receipt()` assembles and locally HMAC-signs a
    `decision_kind: "local_approval"` Agent Receipt embedding the SAME
    `approval` Hop 3/4 already authenticated and independently
    re-verified twice, and writes it to `receipt_path`. A receipt-emission
    failure is caught and downgraded to a non-fatal warning — it can
    never un-complete an already-finished mission.
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
    if not approval_gate.verify(approval, plan):
        raise ApprovalAuthenticationError(
            f"approval {getattr(approval, 'approval_id', '?')!r} for plan "
            f"{plan.plan_id!r} failed authentication — refusing to build a spec "
            "or generate code from it"
        )

    spec = finalize_spec_with_approval(
        plan, approval, log_path=spec_log_path, identity_dir=_identity_dir_hint(approval_gate),
    )
    if spec is None:
        return PipelineResult(status="rejected", decision=decision, plan=plan, approval=approval)

    codegen_result = generate_app(spec, target_dir, target_stack=codegen_target_stack)
    telemetry_event = _record_governed_mission_telemetry()
    receipt = _emit_governed_mission_receipt(plan, approval, spec, target_dir, approval_gate, receipt_path)
    return PipelineResult(
        status="generated", decision=decision, plan=plan, approval=approval,
        spec=spec, codegen=codegen_result, telemetry=telemetry_event, receipt=receipt,
    )


__all__ = ["run_pipeline", "PipelineResult", "PipelineError", "DEFAULT_SOURCE_TYPE"]
