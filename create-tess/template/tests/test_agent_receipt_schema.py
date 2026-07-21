"""
Agent Receipt — core/contracts/agent-receipt.schema.json.

Spec: docs/AGENT_RECEIPT_SPEC.md. This schema is deliberately NOT wired into
`.tess/bin/tessctl`'s CONTRACT_SCHEMAS registry (see the PR description /
docs/AGENT_RECEIPT_SPEC.md "What this is not" — no change to tessctl, the
gate, or policy.yaml ships in this change), so these tests validate directly
against the engine's own `schema_validate()` (the same minimal draft-07
subset every other contract in this repository is checked with), rather than
through the `tessctl validate <type> <file>` CLI surface.

Coverage:
  * A valid instance of both decision kinds (verdict, signoff) passes with [].
  * Cross-file $ref resolution works: decision_kind: verdict requires
    `decision` to independently satisfy the REAL verdict.schema.json, not a
    duplicated copy.
  * $defs.SignoffArtifact requires every field _gate_validate_signoff already
    checks at runtime, plus its embedded VerdictSignature-shaped signature.
  * policy_decision's path_rule/hard_floor_rule conditional requires
    classification/category respectively.
  * chain's sequence:0 <-> prev_receipt_hash:"GENESIS" conditional.
  * additionalProperties: false rejects an unexpected top-level field.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "core" / "contracts" / "agent-receipt.schema.json"
CONTRACTS_DIR = REPO_ROOT / "core" / "contracts"


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _base_verdict():
    return {
        "verifier": "Reid",
        "output_domain": "Code diff / PR",
        "primary_artifacts_read": ["docs/AGENT_RECEIPT_SPEC.md"],
        "findings": [],
        "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "summary_line": "Reviewed. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Top priority: none.",
        "disposition": "APPROVE",
        "signature": {
            "algorithm": "gpg-detached-armor",
            "signed_content_sha256": "a" * 64,
            "signature_armored": "-----BEGIN PGP SIGNATURE-----\n-----END PGP SIGNATURE-----\n",
        },
    }


def _base_signoff():
    return {
        "rule_id": "demo-money-movement",
        "category": "money_movement",
        "authorized_by": "TestOperator",
        "rationale": "Test-only rationale.",
        "authorized_at": "2026-07-19T00:00:00.000000Z",
        "signature": {
            "algorithm": "gpg-detached-armor",
            "signed_content_sha256": "b" * 64,
            "signature_armored": "-----BEGIN PGP SIGNATURE-----\n-----END PGP SIGNATURE-----\n",
        },
    }


def _base_local_approval(approved_by="local:tester#0123456789abcdef"):
    """A schema-shaped `LocalApprovalArtifact` — mirrors the real
    `spec_engine.types.Approval` shape `spec_engine.gate_approval.
    sign_local_approval()` produces (System A, local HMAC — see
    tests/test_receipt_verify_semantics.py for a genuine, real-key round
    trip; this file only proves the SCHEMA's own shape/structural rules)."""
    return {
        "approval_id": "appr-000000000000",
        "plan_id": "plan-test001",
        "approved": True,
        "approved_by": approved_by,
        "approved_at": "2026-07-19T00:00:00.000000Z",
        "notes": (
            '{"human_notes": "", "auth": {"mechanism": "local-hmac-sha256-v1", '
            '"identity_fingerprint": "0123456789abcdef", "content_hash": "' + "d" * 64 + '", '
            '"nonce": "nonce-000000000000", "signature": "' + "e" * 64 + '"}}'
        ),
    }


def _base_receipt(decision_kind, decision, *, rule_kind="path_rule", sequence=0, prev_hash="GENESIS"):
    if rule_kind == "path_rule":
        policy_decision = {
            "source": "core/policy/policy.yaml",
            "rule_id": "docs-review",
            "rule_kind": "path_rule",
            "classification": ["prod_touching"],
            "description": "Doc change requires review.",
        }
    elif rule_kind == "hard_floor_rule":
        policy_decision = {
            "source": "core/policy/policy.yaml",
            "rule_id": "money-movement",
            "rule_kind": "hard_floor_rule",
            "category": "money_movement",
            "description": "Hard floor: money movement requires sign-off.",
        }
    else:
        policy_decision = {
            "source": "orchestrator/approval_gate.py",
            "rule_id": "orchestrator-pipeline-hop3-approval-gate",
            "rule_kind": "pipeline_approval_gate",
            "description": "run_pipeline() Hop 3 requires an authenticated ApprovalGate decision.",
        }
    if decision_kind == "local_approval":
        signed_by = decision.get("approved_by", "local:tester#0123456789abcdef")
        receipt_signature = {
            "algorithm": "local-hmac-sha256-v1",
            "signed_by": signed_by,
            "signed_content_sha256": "c" * 64,
            "signature_hex": "f" * 64,
        }
    else:
        receipt_signature = {
            "algorithm": "gpg-detached-armor",
            "signed_by": "Reid" if decision_kind == "verdict" else "TestOperator",
            "signed_content_sha256": "c" * 64,
            "signature_armored": "-----BEGIN PGP SIGNATURE-----\n-----END PGP SIGNATURE-----\n",
        }
    return {
        "receipt_schema": "tess-os.agent-receipt/1",
        "receipt_id": "0" * 32,
        "issued_at": "2026-07-19T00:00:00.000000Z",
        "proposed_action": {"actor": "Ada", "summary": "Test proposal"},
        "policy_decision": policy_decision,
        "decision_kind": decision_kind,
        "decision": decision,
        "chain": {"sequence": sequence, "prev_receipt_hash": prev_hash},
        "receipt_signature": receipt_signature,
    }


def test_valid_verdict_receipt_passes(engine, schema):
    receipt = _base_receipt("verdict", _base_verdict())
    assert engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR) == []


def test_valid_signoff_receipt_passes(engine, schema):
    receipt = _base_receipt("signoff", _base_signoff(), rule_kind="hard_floor_rule")
    assert engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR) == []


def test_embedded_verdict_must_satisfy_real_verdict_schema(engine, schema):
    """Cross-file $ref: decision_kind: verdict's `decision` is checked
    against the REAL verdict.schema.json, not a duplicated shape — deleting
    a verdict-required field (`findings`) must fail."""
    verdict = _base_verdict()
    del verdict["findings"]
    receipt = _base_receipt("verdict", verdict)
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert any("findings" in e for e in errors), errors


def test_signoff_decision_missing_authorized_by_fails(engine, schema):
    signoff = _base_signoff()
    del signoff["authorized_by"]
    receipt = _base_receipt("signoff", signoff, rule_kind="hard_floor_rule")
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert any("authorized_by" in e for e in errors), errors


def test_path_rule_requires_classification(engine, schema):
    receipt = _base_receipt("verdict", _base_verdict())
    del receipt["policy_decision"]["classification"]
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert any("classification" in e for e in errors), errors


def test_hard_floor_rule_requires_category(engine, schema):
    receipt = _base_receipt("signoff", _base_signoff(), rule_kind="hard_floor_rule")
    del receipt["policy_decision"]["category"]
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert any("category" in e for e in errors), errors


def test_genesis_requires_literal_genesis_hash(engine, schema):
    receipt = _base_receipt("verdict", _base_verdict(), sequence=0, prev_hash="x" * 64)
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert any("GENESIS" in e or "does not match pattern" in e for e in errors), errors


def test_non_genesis_requires_sha256_hex_hash(engine, schema):
    receipt = _base_receipt("verdict", _base_verdict(), sequence=1, prev_hash="GENESIS")
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert errors, "sequence:1 with prev_receipt_hash 'GENESIS' should fail the pattern check"


def test_unexpected_top_level_field_rejected(engine, schema):
    receipt = _base_receipt("verdict", _base_verdict())
    receipt["not_a_real_field"] = True
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert any("not_a_real_field" in e for e in errors), errors


def test_missing_receipt_signature_rejected(engine, schema):
    receipt = _base_receipt("verdict", _base_verdict())
    del receipt["receipt_signature"]
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert any("receipt_signature" in e for e in errors), errors


def test_wrong_receipt_schema_version_rejected(engine, schema):
    receipt = _base_receipt("verdict", _base_verdict())
    receipt["receipt_schema"] = "proposed-v1"
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert any("receipt_schema" in e for e in errors), errors


# ---------------------------------------------------------------------------
# decision_kind: local_approval (wedge-loop epic addition) — System A,
# local HMAC, structurally distinct from the two System B (GPG) kinds
# above. See core/contracts/agent-receipt.schema.json's
# $defs.LocalApprovalArtifact and docs/AGENT_RECEIPT_SPEC.md.
# ---------------------------------------------------------------------------


def test_valid_local_approval_receipt_passes(engine, schema):
    receipt = _base_receipt("local_approval", _base_local_approval(), rule_kind="pipeline_approval_gate")
    assert engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR) == []


def test_local_approval_decision_missing_notes_fails(engine, schema):
    decision = _base_local_approval()
    del decision["notes"]
    receipt = _base_receipt("local_approval", decision, rule_kind="pipeline_approval_gate")
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert any("notes" in e for e in errors), errors


def test_local_approval_decision_approved_false_rejected(engine, schema):
    """A receipt can only represent a GRANTED local approval — mirrors
    the verdict disposition:APPROVE structural rule above."""
    decision = _base_local_approval()
    decision["approved"] = False
    receipt = _base_receipt("local_approval", decision, rule_kind="pipeline_approval_gate")
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert any("approved" in e for e in errors), errors


def test_local_approval_decision_cannot_smuggle_gpg_signature_field(engine, schema):
    """additionalProperties: false on LocalApprovalArtifact — a `decision`
    cannot blend a GPG-shaped `signature` field into a local_approval
    decision (the two trust levels can never be structurally mixed)."""
    decision = _base_local_approval()
    decision["signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": "a" * 64,
        "signature_armored": "-----BEGIN PGP SIGNATURE-----\n-----END PGP SIGNATURE-----\n",
    }
    receipt = _base_receipt("local_approval", decision, rule_kind="pipeline_approval_gate")
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert any("signature" in e for e in errors), errors


def test_local_approval_decision_cannot_satisfy_verdict_shaped_decision_ref(engine, schema):
    """decision_kind: verdict's decision must fail against
    $defs.LocalApprovalArtifact's fields — a local_approval-shaped
    decision cannot be smuggled in under decision_kind: verdict."""
    receipt = _base_receipt("verdict", _base_local_approval())
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert errors, "an Approval-shaped decision must fail verdict.schema.json"


def test_local_approval_receipt_signature_algorithm_must_be_hmac(engine, schema):
    """TRUST-LEVEL PAIRING (structural): a local_approval decision's
    envelope cannot be GPG-signed."""
    receipt = _base_receipt("local_approval", _base_local_approval(), rule_kind="pipeline_approval_gate")
    receipt["receipt_signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_by": receipt["decision"]["approved_by"],
        "signed_content_sha256": "c" * 64,
        "signature_armored": "-----BEGIN PGP SIGNATURE-----\n-----END PGP SIGNATURE-----\n",
    }
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert any("algorithm" in e or "signature_hex" in e for e in errors), errors


def test_verdict_receipt_signature_algorithm_cannot_be_hmac(engine, schema):
    """TRUST-LEVEL PAIRING (structural), the reverse direction: a
    verdict-backed decision's envelope cannot be HMAC-signed — a GPG-
    backed decision can never be wrapped in a symmetric-key envelope."""
    receipt = _base_receipt("verdict", _base_verdict())
    receipt["receipt_signature"] = {
        "algorithm": "local-hmac-sha256-v1",
        "signed_by": "Reid",
        "signed_content_sha256": "c" * 64,
        "signature_hex": "f" * 64,
    }
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert any("algorithm" in e for e in errors), errors


def test_receipt_signature_hmac_requires_signature_hex(engine, schema):
    receipt = _base_receipt("local_approval", _base_local_approval(), rule_kind="pipeline_approval_gate")
    del receipt["receipt_signature"]["signature_hex"]
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert any("signature_hex" in e for e in errors), errors


def test_pipeline_approval_gate_requires_no_classification_or_category(engine, schema):
    """pipeline_approval_gate is not a policy.yaml PathRule/HardFloorRule
    instance — only the shared source/rule_id/rule_kind/description are
    required, never classification or category."""
    receipt = _base_receipt("local_approval", _base_local_approval(), rule_kind="pipeline_approval_gate")
    assert "classification" not in receipt["policy_decision"]
    assert "category" not in receipt["policy_decision"]
    assert engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR) == []


# ---------------------------------------------------------------------------
# tess-os #162 (Cyra LOW-2): signature_armored / signature_hex must be
# mutually exclusive — additionalProperties: false alone only blocks
# UNDEFINED keys, it never stopped the off-algorithm field ALSO being
# present alongside the required one.
# ---------------------------------------------------------------------------


def test_gpg_receipt_signature_cannot_also_carry_signature_hex(engine, schema):
    receipt = _base_receipt("verdict", _base_verdict())
    assert receipt["receipt_signature"]["algorithm"] == "gpg-detached-armor"
    receipt["receipt_signature"]["signature_hex"] = "f" * 64  # stray off-algorithm field
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert errors, "a gpg-detached-armor receipt_signature must never also carry signature_hex"


def test_hmac_receipt_signature_cannot_also_carry_signature_armored(engine, schema):
    receipt = _base_receipt("local_approval", _base_local_approval(), rule_kind="pipeline_approval_gate")
    assert receipt["receipt_signature"]["algorithm"] == "local-hmac-sha256-v1"
    receipt["receipt_signature"]["signature_armored"] = (
        "-----BEGIN PGP SIGNATURE-----\n-----END PGP SIGNATURE-----\n"
    )  # stray off-algorithm field
    errors = engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR)
    assert errors, "a local-hmac-sha256-v1 receipt_signature must never also carry signature_armored"


def test_valid_verdict_receipt_with_only_signature_armored_still_passes(engine, schema):
    """Sanity check the oneOf mutual-exclusion rule doesn't reject a
    genuinely valid, single-field receipt_signature — only a receipt that
    carries BOTH fields."""
    receipt = _base_receipt("verdict", _base_verdict())
    assert "signature_hex" not in receipt["receipt_signature"]
    assert engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR) == []


def test_valid_local_approval_receipt_with_only_signature_hex_still_passes(engine, schema):
    receipt = _base_receipt("local_approval", _base_local_approval(), rule_kind="pipeline_approval_gate")
    assert "signature_armored" not in receipt["receipt_signature"]
    assert engine.schema_validate(receipt, schema, schema, CONTRACTS_DIR) == []
