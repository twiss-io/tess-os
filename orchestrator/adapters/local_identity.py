"""`LocalIdentityApprovalGate` — the DEFAULT `ApprovalGate` adapter shipped
by this PR. See `spec_engine.gate_identity`'s module docstring for exactly
what it proves and its honest limitation (a single-OS-account trust
boundary, not a production IdP), and `orchestrator/approval_gate.py`'s
`ApprovalGate` docstring for the interface contract this implements.

    from orchestrator.adapters.local_identity import LocalIdentityApprovalGate

    gate = LocalIdentityApprovalGate()
    approval = gate.request_approval(plan)   # blocks on a real terminal prompt
    assert gate.verify(approval, plan)       # independently re-checked

## Signing/verification now delegates to `spec_engine.gate_approval`

Before the codegen-boundary hardening epic, this class implemented its
own HMAC-signing and verification logic directly. It now delegates BOTH
to `spec_engine.gate_approval.sign_local_approval()` /
`verify_gate_approval()` — the SAME functions `spec_engine.spec_builder.
build_spec()` itself calls to independently re-verify an approval at the
codegen boundary. This is deliberate, not incidental: it means there is
exactly ONE implementation of "what does a genuinely gate-verified
approval look like" in this repo, not two that could silently drift
apart (a real risk when two components sign/verify against the same
canonical payload shape — any field-order or field-set divergence would
silently break cross-verification). This class's own job, unchanged, is
purely the INTERACTIVE UX layer: get a real human's decision at a real
terminal, then hand it to `sign_local_approval()`.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, Tuple

from spec_engine.gate_approval import sign_local_approval, verify_gate_approval
from spec_engine.types import Approval, Plan

from ..approval_gate import ApprovalAuthenticationError, ApprovalGate
from ..identity import LocalIdentity, load_or_create_local_identity

_LOG = logging.getLogger(__name__)

ConfirmFn = Callable[[Plan, LocalIdentity], Tuple[bool, str]]


class LocalIdentityApprovalGate(ApprovalGate):
    """Binds `Approval.approved_by` to this OS account's local,
    HMAC-signed approval identity (see `spec_engine.gate_identity`)
    instead of trusting a caller-supplied string. `request_approval()`
    blocks on a real terminal confirmation by default; pass `confirm_fn`
    to inject a different (still-human-driven) confirmation surface, or a
    test double — the identity/signing logic underneath is identical
    either way, so a test exercising a fake confirm still exercises the
    real authentication mechanism."""

    def __init__(
        self,
        *,
        identity_dir: Optional[str] = None,
        confirm_fn: Optional[ConfirmFn] = None,
        input_fn: Optional[Callable[[str], str]] = None,
        print_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._identity_dir = identity_dir
        self._identity = load_or_create_local_identity(identity_dir)
        # `input`/`print` are resolved HERE, at call time (via the normal
        # LEGB/builtins lookup), rather than bound as function-signature
        # DEFAULT values — a default value is evaluated exactly once, at
        # class-definition/import time, which would permanently capture
        # the ORIGINAL `input`/`print` builtin and make
        # `monkeypatch.setattr("builtins.input", ...)` silently ineffective
        # against it (a real gotcha caught by
        # tests/orchestrator/test_cli.py's own CLI smoke tests).
        self._input_fn = input_fn if input_fn is not None else input
        self._print_fn = print_fn if print_fn is not None else print
        self._confirm_fn = confirm_fn or self._interactive_confirm

    @property
    def identity(self) -> LocalIdentity:
        return self._identity

    def _interactive_confirm(self, plan: Plan, identity: LocalIdentity) -> Tuple[bool, str]:
        self._print_fn(plan.summary_for_approval)
        self._print_fn(
            f"\nApprover identity: local OS account {identity.username!r} "
            f"(key fingerprint {identity.fingerprint})."
        )
        answer = self._input_fn(
            f"Type APPROVE to approve as {identity.username}, REJECT to reject, "
            "anything else to abort: "
        ).strip()
        if answer == "APPROVE":
            return True, ""
        if answer == "REJECT":
            notes = self._input_fn("Rejection notes (optional): ").strip()
            return False, notes
        raise ApprovalAuthenticationError(
            f"approval aborted for plan {plan.plan_id!r} — {answer!r} was neither "
            "APPROVE nor REJECT"
        )

    def request_approval(self, plan: Plan) -> Approval:
        approved, human_notes = self._confirm_fn(plan, self._identity)
        approved_by = f"local:{self._identity.username}#{self._identity.fingerprint}"
        approval = sign_local_approval(
            plan, approved_by=approved_by, approved=approved, notes=human_notes,
            identity_dir=self._identity_dir,
        )
        if not self.verify(approval, plan):
            # Should be unreachable if signing above is correct — fail
            # loud rather than ever hand back an approval this gate
            # itself could not re-verify.
            raise ApprovalAuthenticationError(
                f"internal error: just-signed approval for plan {plan.plan_id!r} "
                "failed this gate's own verification"
            )
        return approval

    def verify(self, approval: Approval, plan: Plan) -> bool:
        try:
            verify_gate_approval(approval, plan, identity_dir=self._identity_dir)
            return True
        except Exception as exc:
            # A forged/malformed/tampered/spec-substituted approval is an
            # EXPECTED adversarial input, not a bug — every failure mode
            # (bad JSON, missing key, wrong signature, content-hash
            # mismatch, missing key file...) collapses to "not verified",
            # never an exception escaping to the caller. See
            # test_local_identity_gate.py's
            # test_verify_never_raises_on_arbitrary_notes for the
            # fuzz-style proof of this.
            #
            # [Reid MEDIUM] Log a WARNING before returning False — a
            # forged-approval attempt reaching this point is exactly the
            # kind of event that should leave a trace an operator can
            # find later, not vanish silently into a bare `False`. The
            # never-raise contract above is unchanged; this only adds an
            # audit-trail breadcrumb.
            _LOG.warning("approval verification failed: %s", type(exc).__name__)
            return False


__all__ = ["LocalIdentityApprovalGate", "ConfirmFn"]
