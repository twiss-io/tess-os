"""Tests for spec_engine.gate_approval -- sign_local_approval() and
verify_gate_approval()/consume_approval_nonce() directly (unit-level;
tests/spec_engine/test_spec_builder.py covers the SAME mechanism
integrated into build_spec(), the actual codegen boundary)."""

from __future__ import annotations

import dataclasses
import json

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.approval import record_approval
from spec_engine.content import plan_content_hash
from spec_engine.gate_approval import (
    ApprovalReplayError,
    ApprovalVerificationError,
    GateVerifiedApproval,
    consume_approval_nonce,
    sign_local_approval,
    verify_gate_approval,
)
from spec_engine.intake import harvest_intake
from spec_engine.plan_builder import build_plan
from spec_engine.types import Approval


def _plan(text="An app that tracks invoices."):
    return build_plan(harvest_intake(text, "fragment"))


# --------------------------------------------------------------------------
# Positive path
# --------------------------------------------------------------------------


def test_sign_local_approval_produces_a_verifiable_approval(tmp_path):
    plan = _plan()
    approval = sign_local_approval(plan, approved_by="Xavier", identity_dir=tmp_path)
    verified = verify_gate_approval(approval, plan, identity_dir=tmp_path)
    assert isinstance(verified, GateVerifiedApproval)
    assert verified.content_hash == plan_content_hash(plan)
    assert verified.approval is approval


def test_sign_local_approval_binds_content_hash_into_notes(tmp_path):
    plan = _plan()
    approval = sign_local_approval(plan, approved_by="Xavier", identity_dir=tmp_path)
    auth = json.loads(approval.notes)["auth"]
    assert auth["content_hash"] == plan_content_hash(plan)


def test_sign_local_approval_preserves_human_notes(tmp_path):
    plan = _plan()
    approval = sign_local_approval(
        plan, approved_by="Xavier", notes="Looks great, ship it.", identity_dir=tmp_path,
    )
    assert json.loads(approval.notes)["human_notes"] == "Looks great, ship it."


def test_sign_local_approval_supports_rejection(tmp_path):
    plan = _plan()
    approval = sign_local_approval(plan, approved_by="Xavier", approved=False, identity_dir=tmp_path)
    assert approval.approved is False
    # A rejection is STILL genuinely verifiable -- rejecting is not the
    # same thing as being unauthenticated.
    verify_gate_approval(approval, plan, identity_dir=tmp_path)


def test_verify_gate_approval_is_non_consuming_safe_to_call_repeatedly(tmp_path):
    """verify_gate_approval() (unlike consume_approval_nonce()) does not
    spend the nonce -- calling it more than once on the same still-unspent
    approval must succeed every time."""
    plan = _plan()
    approval = sign_local_approval(plan, approved_by="Xavier", identity_dir=tmp_path)
    for _ in range(3):
        verify_gate_approval(approval, plan, identity_dir=tmp_path)


# --------------------------------------------------------------------------
# Adversarial path
# --------------------------------------------------------------------------


def test_verify_gate_approval_rejects_a_bare_approval(tmp_path):
    """[MEDIUM-1] the exact forgery the epic names."""
    plan = _plan()
    bare = record_approval(plan, approved_by="Xavier", approved=True)
    with pytest.raises(ApprovalVerificationError):
        verify_gate_approval(bare, plan, identity_dir=tmp_path)


def test_verify_gate_approval_rejects_mismatched_plan_id(tmp_path):
    plan_a = _plan("An app that tracks invoices.")
    plan_b = _plan("A different app entirely.")
    approval_a = sign_local_approval(plan_a, approved_by="Xavier", identity_dir=tmp_path)
    with pytest.raises(ApprovalVerificationError):
        verify_gate_approval(approval_a, plan_b, identity_dir=tmp_path)


def test_verify_gate_approval_rejects_content_hash_mismatch_same_plan_id(tmp_path):
    """[MEDIUM-2] spec-substitution: same plan_id, different content."""
    plan_a = _plan("An app that tracks invoices.")
    approval_a = sign_local_approval(plan_a, approved_by="Xavier", identity_dir=tmp_path)

    plan_b = _plan("A completely different, unrelated app idea.")
    plan_b_same_id = dataclasses.replace(plan_b, plan_id=plan_a.plan_id)

    with pytest.raises(ApprovalVerificationError, match="content-hash"):
        verify_gate_approval(approval_a, plan_b_same_id, identity_dir=tmp_path)


def test_verify_gate_approval_rejects_a_tampered_signature(tmp_path):
    plan = _plan()
    approval = sign_local_approval(plan, approved_by="Xavier", identity_dir=tmp_path)
    parsed = json.loads(approval.notes)
    parsed["auth"]["signature"] = "0" * 64
    tampered = dataclasses.replace(approval, notes=json.dumps(parsed))

    with pytest.raises(ApprovalVerificationError, match="signature"):
        verify_gate_approval(tampered, plan, identity_dir=tmp_path)


def test_verify_gate_approval_rejects_unknown_mechanism(tmp_path):
    plan = _plan()
    approval = sign_local_approval(plan, approved_by="Xavier", identity_dir=tmp_path)
    parsed = json.loads(approval.notes)
    parsed["auth"]["mechanism"] = "some-other-mechanism-v9"
    tampered = dataclasses.replace(approval, notes=json.dumps(parsed))

    with pytest.raises(ApprovalVerificationError, match="mechanism"):
        verify_gate_approval(tampered, plan, identity_dir=tmp_path)


def test_verify_gate_approval_rejects_signature_from_a_different_identity(tmp_path):
    plan = _plan()
    attacker_dir = tmp_path / "attacker"
    victim_dir = tmp_path / "victim"
    attacker_approval = sign_local_approval(plan, approved_by="Xavier", identity_dir=attacker_dir)

    with pytest.raises(ApprovalVerificationError):
        verify_gate_approval(attacker_approval, plan, identity_dir=victim_dir)


@pytest.mark.parametrize("bad_notes", [
    "",
    "not json at all",
    "{}",
    '{"auth": "not-a-dict"}',
    '{"auth": {}}',
    "null",
    "42",
    '["a", "list"]',
])
def test_verify_gate_approval_fails_closed_on_malformed_notes(tmp_path, bad_notes):
    plan = _plan()
    forged = Approval(
        approval_id="appr-fuzz0000001",
        plan_id=plan.plan_id,
        approved=True,
        approved_by="Xavier",
        approved_at="2026-01-01T00:00:00.000Z",
        notes=bad_notes,
    )
    with pytest.raises(ApprovalVerificationError):
        verify_gate_approval(forged, plan, identity_dir=tmp_path)


# --------------------------------------------------------------------------
# Replay / nonce consumption
# --------------------------------------------------------------------------


def test_consume_approval_nonce_succeeds_once(tmp_path):
    plan = _plan()
    approval = sign_local_approval(plan, approved_by="Xavier", identity_dir=tmp_path)
    verified = verify_gate_approval(approval, plan, identity_dir=tmp_path)
    consume_approval_nonce(verified)  # first spend -- succeeds


def test_consume_approval_nonce_rejects_replay(tmp_path):
    plan = _plan()
    approval = sign_local_approval(plan, approved_by="Xavier", identity_dir=tmp_path)
    verified = verify_gate_approval(approval, plan, identity_dir=tmp_path)
    consume_approval_nonce(verified)
    with pytest.raises(ApprovalReplayError):
        consume_approval_nonce(verified)


def test_two_distinct_approvals_for_the_same_plan_can_each_be_consumed_once(tmp_path):
    """Two INDEPENDENTLY signed approvals (distinct nonces) for the same
    plan content must each be individually spendable -- nonce tracking is
    per-approval, not per-plan-content."""
    plan = _plan()
    approval_1 = sign_local_approval(plan, approved_by="Xavier", identity_dir=tmp_path)
    approval_2 = sign_local_approval(plan, approved_by="Xavier", identity_dir=tmp_path)
    assert json.loads(approval_1.notes)["auth"]["nonce"] != json.loads(approval_2.notes)["auth"]["nonce"]

    consume_approval_nonce(verify_gate_approval(approval_1, plan, identity_dir=tmp_path))
    consume_approval_nonce(verify_gate_approval(approval_2, plan, identity_dir=tmp_path))
