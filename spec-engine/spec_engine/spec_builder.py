"""Promote an approved `Plan` into a `SpecDocument` — the source of truth.
Deliverable (3), final step: "... -> complete spec generation."

This is THE codegen boundary — the sole gateway to a `SpecDocument`,
which is the sole input `spec_engine.codegen.generate_app()` accepts.
`build_spec()` refuses to run — raises `SpecEngineError`, fails loud —
unless it is handed an `Approval` that is BOTH:

  1. structurally valid (its `plan_id` matches the plan being built and
     `approved` is `True` — the original, pre-existing check); AND
  2. a GATE-VERIFIABLE approval — independently re-verified via
     `gate_approval.verify_gate_approval()` against `plan`'s CURRENT
     content, using the same HMAC mechanism `orchestrator.adapters.
     local_identity.LocalIdentityApprovalGate` signs with. A bare
     `approval.record_approval(approved_by="Xavier")` call (no signature,
     no gate involvement at all) fails step 2 and is rejected here —
     closing [Cyra MEDIUM-1]: before this hardening,
     `record_approval(...) -> build_spec(...) -> generate_app(...)`
     produced a real, running app with zero authentication.

There is no code path in this package that reaches a `SpecDocument`
without both of those being true, and without that approval's
content-hash matching `plan`'s CURRENT content (closing [Cyra MEDIUM-2]:
a `plan_id` match alone is not proof the content an approver reviewed is
the content actually being built — see `content.plan_content_hash()`).

**Connectors v1** (`docs/design/connectors-architecture.md`): `plan.
resolved_connectors` — the plan-time resolution of `how_it_works.
integrations` against the connector registry (`connector_resolver.py`) —
is copied verbatim into the built `SpecDocument` here, the same way every
other content dimension is, and is one of the dimensions
`content.plan_content_hash()` covers. No new trust machinery: a registry
swap, a connector version bump, or a side-effect-class change made to
`plan.resolved_connectors` after an approval was signed is caught by the
SAME content-hash re-verification this module already enforces.
"""

from __future__ import annotations

from typing import Optional

from .content import SpecEngineError, new_id, utc_now_iso
from .gate_approval import consume_approval_nonce, verify_gate_approval
from .types import Plan, Approval, Provenance, SpecDocument


def build_spec(
    plan: Plan,
    approval: Approval,
    *,
    spec_id: Optional[str] = None,
    spec_version: int = 1,
    identity_dir: Optional[str] = None,
) -> SpecDocument:
    """Build a `SpecDocument` from `plan`, gated on `approval`.

    Raises `SpecEngineError` (or the more specific `gate_approval.
    ApprovalVerificationError` / `ApprovalReplayError`, both subclasses)
    if:
      - `approval.plan_id != plan.plan_id` (approval for a different plan);
      - `approval.approved is not True` (rejected or not yet decided);
      - `approval` does not independently re-verify against `plan`'s
        current content via `gate_approval.verify_gate_approval()` — a
        bare/forged/tampered approval, or one signed for DIFFERENT
        content than `plan` currently carries (spec-substitution);
      - `approval`'s nonce has already been consumed by a prior
        `build_spec()` call (replay — see `gate_approval.
        consume_approval_nonce()`'s disclosed, in-process-only scope).

    `identity_dir` is forwarded to `gate_approval.verify_gate_approval()`
    — only meaningful for the shipped local-HMAC mechanism; pass it when
    the approval being verified was signed under a non-default identity
    directory (tests scope this to `tmp_path`; a caller integrating a
    non-default `LocalIdentityApprovalGate` should thread its own
    `identity_dir` through here the same way `orchestrator.pipeline.
    run_pipeline()` does).

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

    verified = verify_gate_approval(approval, plan, identity_dir=identity_dir)
    consume_approval_nonce(verified)

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
        resolved_connectors=list(plan.resolved_connectors),
    )
