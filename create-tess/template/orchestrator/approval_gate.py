"""`ApprovalGate` — the pluggable, authenticated-approval interface every
adapter (the shipped local default; a future Telegram-button, web, or
CLI-with-real-auth adapter) implements.

This is a PRODUCT-layer human-in-the-loop control, not the ship-gate
(`core/policy/**`, `.tess/bin/tessctl verdict`/`gate`). It sits in front
of `spec_engine.pipeline.finalize_spec_with_approval()` in the wired
pipeline (`orchestrator/pipeline.py`) and works ALONGSIDE — not instead
of — `spec_engine.spec_builder.build_spec()`'s own codegen-boundary gate
(an `Approval` whose `plan_id` matches, whose `approved` is `True`, AND
which independently re-verifies via `spec_engine.gate_approval.
verify_gate_approval()` is required to reach a `SpecDocument`; see that
module's docstring). What THIS interface adds is authentication of WHO
`Approval.approved_by` is attributed to, at the point of decision —
`spec_engine`'s own `record_approval()` never verified that on its own;
see `identity.py`'s module docstring for the full problem statement.

## The contract an adapter must satisfy

    class MyApprovalGate(ApprovalGate):
        def request_approval(self, plan: Plan) -> Approval:
            # Block until a REAL human decision is made. Authenticate that
            # human through YOUR OWN mechanism (a Telegram button bound to
            # a known chat/user id, a web session token, an SSO login,
            # a locally-signed key — whatever fits the adapter) BEFORE
            # constructing the Approval you return. Never forward an
            # untrusted, caller-suppliable string into approved_by
            # unexamined.
            ...

        def verify(self, approval: Approval, plan: Plan) -> bool:
            # Independently re-check that `approval` was genuinely
            # produced by THIS gate's authentication mechanism for THIS
            # EXACT `plan` (not merely structurally similar, not tampered
            # with, not a genuine approval for a DIFFERENT plan/spec) —
            # not hand-constructed. `plan` was added ([Cyra MEDIUM-2])
            # so a conforming adapter can bind its check to the plan's
            # actual CONTENT, not just an opaque, mutable plan_id slug —
            # see LocalIdentityApprovalGate.verify() for the shipped
            # example (content-hash comparison via spec_engine.content.
            # plan_content_hash()). The orchestrator's pipeline calls this
            # immediately after request_approval() and refuses to proceed
            # to finalize_spec_with_approval()/codegen if it returns False.
            ...

Two methods, not one, on purpose: `request_approval()` does the
authenticating; `verify()` is a SEPARATE, independent check the caller
(the orchestrator pipeline) runs on whatever `Approval` object it actually
has in hand — catching a bug in `request_approval()`, or an `Approval`
substituted by other code between the two calls, rather than trusting
`request_approval()`'s output blindly. See
`tests/orchestrator/test_pipeline_adversarial.py` for the required proof
that a forged/unverifiable `Approval` is rejected before codegen ever
runs, and `tests/spec_engine/test_gate_approval.py` for the SAME proof
one layer down, at the codegen boundary itself (`build_spec()`), which
does not depend on any particular `ApprovalGate` adapter having run this
check correctly first.

A Telegram-button, web, or CLI-with-real-auth adapter is a drop-in
`ApprovalGate` implementation satisfying this same contract — not built in
this PR (out of scope by design: "GENERALIZED/pluggable — do NOT hardcode
Telegram").
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from spec_engine.types import Approval, Plan


class ApprovalAuthenticationError(ValueError):
    """Fail loud: an `Approval` could not be authenticated by the gate
    that is supposed to own it. Never silently downgrade this to a
    warning or a best-effort continue — the whole point of this module is
    that an unauthenticated approval must not be able to reach codegen."""


class ApprovalGate(ABC):
    """See module docstring for the full contract."""

    @abstractmethod
    def request_approval(self, plan: Plan) -> Approval:
        """Block until a real, authenticated human decision is made on
        `plan`. Must not return an `Approval` whose `approved_by` came
        from an unauthenticated, caller-suppliable string."""
        raise NotImplementedError

    @abstractmethod
    def verify(self, approval: Approval, plan: Plan) -> bool:
        """Return True iff `approval` was genuinely produced by this
        gate's own authentication mechanism FOR `plan` specifically (bind
        to `plan`'s actual content, not just an opaque plan_id — [Cyra
        MEDIUM-2]) and has not been tampered with. Must not raise on a
        malformed/forged `approval` — a forged approval is an expected
        adversarial input this method has to handle by returning False,
        not a programming error."""
        raise NotImplementedError


__all__ = ["ApprovalGate", "ApprovalAuthenticationError"]
