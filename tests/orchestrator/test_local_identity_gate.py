"""Tests for orchestrator.adapters.local_identity.LocalIdentityApprovalGate
-- including the REQUIRED adversarial proof that a forged/tampered
Approval is rejected by verify(), not just that a genuine one passes."""

from __future__ import annotations

import dataclasses
import json

import pytest

import _orchestrator_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.approval import record_approval
from spec_engine.intake import harvest_intake
from spec_engine.plan_builder import build_plan
from spec_engine.types import Approval

from orchestrator.adapters.local_identity import LocalIdentityApprovalGate
from orchestrator.approval_gate import ApprovalAuthenticationError


def _plan():
    return build_plan(harvest_intake("An app that tracks invoices.", "fragment"))


def _approving_gate(tmp_path, notes=""):
    return LocalIdentityApprovalGate(
        identity_dir=tmp_path / "identity",
        confirm_fn=lambda plan, identity: (True, notes),
    )


def _rejecting_gate(tmp_path, notes="not the right idea"):
    return LocalIdentityApprovalGate(
        identity_dir=tmp_path / "identity",
        confirm_fn=lambda plan, identity: (False, notes),
    )


# --------------------------------------------------------------------------
# Positive path
# --------------------------------------------------------------------------


def test_request_approval_returns_an_approval_this_gate_verifies(tmp_path):
    gate = _approving_gate(tmp_path)
    plan = _plan()
    approval = gate.request_approval(plan)
    assert approval.approved is True
    assert approval.plan_id == plan.plan_id
    assert gate.verify(approval) is True


def test_approved_by_is_bound_to_the_local_os_identity_not_a_caller_string(tmp_path):
    gate = _approving_gate(tmp_path)
    approval = gate.request_approval(_plan())
    assert approval.approved_by.startswith("local:")
    assert gate.identity.fingerprint in approval.approved_by
    assert gate.identity.username in approval.approved_by


def test_rejection_is_also_authenticated(tmp_path):
    gate = _rejecting_gate(tmp_path)
    plan = _plan()
    approval = gate.request_approval(plan)
    assert approval.approved is False
    assert gate.verify(approval) is True


def test_interactive_confirm_aborts_on_an_unrecognized_answer(tmp_path):
    gate = LocalIdentityApprovalGate(
        identity_dir=tmp_path / "identity",
        input_fn=lambda prompt: "maybe",
        print_fn=lambda *_: None,
    )
    with pytest.raises(ApprovalAuthenticationError):
        gate.request_approval(_plan())


def test_interactive_confirm_approves_on_the_exact_token(tmp_path):
    answers = iter(["APPROVE"])
    gate = LocalIdentityApprovalGate(
        identity_dir=tmp_path / "identity",
        input_fn=lambda prompt: next(answers),
        print_fn=lambda *_: None,
    )
    approval = gate.request_approval(_plan())
    assert approval.approved is True


# --------------------------------------------------------------------------
# Adversarial path -- REQUIRED: forged/unauthenticated approvals are
# rejected. verify() must return False, never raise, on all of these.
# --------------------------------------------------------------------------


def test_verify_rejects_an_approval_never_produced_by_any_gate(tmp_path):
    """The exact forgery the epic names: a caller directly calls
    spec_engine.approval.record_approval() with an arbitrary approved_by
    string -- no signature, no gate involvement at all."""
    gate = LocalIdentityApprovalGate(identity_dir=tmp_path / "identity")
    plan = _plan()
    forged = record_approval(plan, approved_by="Xavier", approved=True)
    assert forged.notes == ""
    assert gate.verify(forged) is False


def test_verify_rejects_a_hand_constructed_approval_with_fake_auth_json(tmp_path):
    gate = LocalIdentityApprovalGate(identity_dir=tmp_path / "identity")
    plan = _plan()
    fake_notes = json.dumps({
        "human_notes": "",
        "auth": {
            "mechanism": "local-hmac-sha256-v1",
            "identity_fingerprint": gate.identity.fingerprint,
            "nonce": "attacker-chosen-nonce",
            "signature": "0" * 64,  # not a real HMAC -- attacker cannot compute one
        },
    })
    forged = Approval(
        approval_id="appr-attacker0001",
        plan_id=plan.plan_id,
        approved=True,
        approved_by=f"local:{gate.identity.username}#{gate.identity.fingerprint}",
        approved_at="2026-01-01T00:00:00.000Z",
        notes=fake_notes,
    )
    assert gate.verify(forged) is False


def test_verify_rejects_a_genuine_approval_with_approved_by_tampered_after_signing(tmp_path):
    gate = _approving_gate(tmp_path)
    real = gate.request_approval(_plan())
    tampered = dataclasses.replace(real, approved_by="Xavier")
    assert gate.verify(tampered) is False


def test_verify_rejects_a_genuine_approval_with_approved_flag_flipped_after_signing(tmp_path):
    gate = _approving_gate(tmp_path)
    real = gate.request_approval(_plan())
    tampered = dataclasses.replace(real, approved=not real.approved)
    assert gate.verify(tampered) is False


def test_verify_rejects_a_genuine_approval_replayed_onto_a_different_plan(tmp_path):
    gate = _approving_gate(tmp_path)
    real = gate.request_approval(_plan())
    tampered = dataclasses.replace(real, plan_id="plan-different000")
    assert gate.verify(tampered) is False


def test_verify_rejects_a_signature_from_a_different_identity(tmp_path):
    attacker_gate = _approving_gate(tmp_path / "attacker-scope")
    plan = _plan()
    attacker_approval = attacker_gate.request_approval(plan)

    victim_gate = LocalIdentityApprovalGate(identity_dir=tmp_path / "victim-scope")
    # The attacker's approval carries the attacker's own identity
    # fingerprint -- the victim gate must not vouch for it.
    assert victim_gate.verify(attacker_approval) is False


@pytest.mark.parametrize("bad_notes", [
    "",
    "not json at all",
    "{}",
    '{"auth": "not-a-dict"}',
    '{"auth": {}}',
    '{"auth": {"mechanism": "some-other-mechanism-v9"}}',
    "null",
    "42",
    '["a", "list", "not", "a", "dict"]',
])
def test_verify_never_raises_on_arbitrary_notes(tmp_path, bad_notes):
    gate = LocalIdentityApprovalGate(identity_dir=tmp_path / "identity")
    plan = _plan()
    forged = Approval(
        approval_id="appr-fuzz0000001",
        plan_id=plan.plan_id,
        approved=True,
        approved_by="Xavier",
        approved_at="2026-01-01T00:00:00.000Z",
        notes=bad_notes,
    )
    # Must not raise -- a forged/malformed approval is expected
    # adversarial input, not a programming error.
    assert gate.verify(forged) is False


def test_request_approval_self_verifies_before_returning(tmp_path, monkeypatch):
    """Defense in depth: if signing ever produced something this gate's
    own verify() would reject, request_approval() must fail loud rather
    than hand back a bad Approval -- proven here by forcing sign_payload()
    to return a wrong signature and asserting the gate refuses to return
    the result instead of silently handing back an unverifiable approval."""
    import orchestrator.adapters.local_identity as local_identity_module

    monkeypatch.setattr(local_identity_module, "sign_payload", lambda key, payload: "0" * 64)
    gate = _approving_gate(tmp_path)
    with pytest.raises(ApprovalAuthenticationError):
        gate.request_approval(_plan())
