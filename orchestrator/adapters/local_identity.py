"""`LocalIdentityApprovalGate` — the DEFAULT `ApprovalGate` adapter shipped
by this PR. See `orchestrator/identity.py`'s module docstring for exactly
what it proves and its honest limitation (a single-OS-account trust
boundary, not a production IdP), and `orchestrator/approval_gate.py`'s
`ApprovalGate` docstring for the interface contract this implements.

    from orchestrator.adapters.local_identity import LocalIdentityApprovalGate

    gate = LocalIdentityApprovalGate()
    approval = gate.request_approval(plan)   # blocks on a real terminal prompt
    assert gate.verify(approval)             # independently re-checked
"""

from __future__ import annotations

import json
from typing import Callable, Optional, Tuple

from spec_engine.content import new_id, utc_now_iso
from spec_engine.types import Approval, Plan

from ..approval_gate import ApprovalAuthenticationError, ApprovalGate
from ..identity import (
    AUTH_MECHANISM,
    LocalIdentity,
    canonical_payload,
    load_or_create_local_identity,
    read_current_key,
    sign_payload,
    verify_signature,
)

# The marker embedded in Approval.notes carrying the signed evidence. A
# future adapter following this same "evidence lives in notes" pattern
# (see approval_gate.py's ApprovalGate docstring) would use its own
# distinct marker so the two never collide inside one JSONL audit log.
_NOTES_AUTH_KEY = "auth"
_NOTES_HUMAN_KEY = "human_notes"

ConfirmFn = Callable[[Plan, LocalIdentity], Tuple[bool, str]]


class LocalIdentityApprovalGate(ApprovalGate):
    """Binds `Approval.approved_by` to this OS account's local,
    HMAC-signed approval identity (see `identity.py`) instead of trusting
    a caller-supplied string. `request_approval()` blocks on a real
    terminal confirmation by default; pass `confirm_fn` to inject a
    different (still-human-driven) confirmation surface, or a test
    double — the identity/signing logic underneath is identical either
    way, so a test exercising a fake confirm still exercises the real
    authentication mechanism."""

    def __init__(
        self,
        *,
        identity_dir: Optional[str] = None,
        confirm_fn: Optional[ConfirmFn] = None,
        input_fn: Optional[Callable[[str], str]] = None,
        print_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
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
        approval = self._sign_new_approval(plan, approved=approved, human_notes=human_notes)
        if not self.verify(approval):
            # Should be unreachable if signing above is correct — fail
            # loud rather than ever hand back an approval this gate
            # itself could not re-verify.
            raise ApprovalAuthenticationError(
                f"internal error: just-signed approval for plan {plan.plan_id!r} "
                "failed this gate's own verification"
            )
        return approval

    def _sign_new_approval(self, plan: Plan, *, approved: bool, human_notes: str) -> Approval:
        key = read_current_key(self._identity.key_path)
        approved_by = f"local:{self._identity.username}#{self._identity.fingerprint}"
        payload = canonical_payload(
            approval_id=new_id("appr"),
            plan_id=plan.plan_id,
            approved=approved,
            approved_by=approved_by,
            approved_at=utc_now_iso(),
            nonce=new_id("nonce"),
        )
        signature = sign_payload(key, payload)
        notes = json.dumps({
            _NOTES_HUMAN_KEY: human_notes,
            _NOTES_AUTH_KEY: {
                "mechanism": AUTH_MECHANISM,
                "identity_fingerprint": self._identity.fingerprint,
                "nonce": payload["nonce"],
                "signature": signature,
            },
        })
        # Built directly (not via spec_engine.approval.record_approval())
        # so THIS approval_id is the one signed above — record_approval()
        # generates its own internally, which would desync payload from
        # object. Approval.__post_init__ still enforces the same
        # invariants record_approval() relies on (non-empty approved_by,
        # a safe-slug plan_id).
        return Approval(
            approval_id=payload["approval_id"],
            plan_id=plan.plan_id,
            approved=approved,
            approved_by=approved_by,
            approved_at=payload["approved_at"],
            notes=notes,
        )

    def verify(self, approval: Approval) -> bool:
        try:
            parsed = json.loads(approval.notes)
            auth = parsed[_NOTES_AUTH_KEY]
            if auth["mechanism"] != AUTH_MECHANISM:
                return False
            if auth["identity_fingerprint"] != self._identity.fingerprint:
                return False
            payload = canonical_payload(
                approval_id=approval.approval_id,
                plan_id=approval.plan_id,
                approved=approval.approved,
                approved_by=approval.approved_by,
                approved_at=approval.approved_at,
                nonce=auth["nonce"],
            )
            key = read_current_key(self._identity.key_path)
            return verify_signature(key, payload, auth["signature"])
        except Exception:
            # A forged/malformed/tampered approval is an EXPECTED
            # adversarial input, not a bug — every parse/lookup failure
            # (bad JSON, missing key, wrong type, missing key file...)
            # collapses to "not verified", never an exception escaping
            # to the caller. See test_local_identity_gate.py's
            # test_verify_never_raises_on_arbitrary_notes for the
            # fuzz-style proof of this.
            return False


__all__ = ["LocalIdentityApprovalGate", "ConfirmFn"]
