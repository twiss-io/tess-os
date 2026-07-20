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


def _base_receipt(decision_kind, decision, *, rule_kind="path_rule", sequence=0, prev_hash="GENESIS"):
    if rule_kind == "path_rule":
        policy_decision = {
            "source": "core/policy/policy.yaml",
            "rule_id": "docs-review",
            "rule_kind": "path_rule",
            "classification": ["prod_touching"],
            "description": "Doc change requires review.",
        }
    else:
        policy_decision = {
            "source": "core/policy/policy.yaml",
            "rule_id": "money-movement",
            "rule_kind": "hard_floor_rule",
            "category": "money_movement",
            "description": "Hard floor: money movement requires sign-off.",
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
        "receipt_signature": {
            "algorithm": "gpg-detached-armor",
            "signed_by": "Reid" if decision_kind == "verdict" else "TestOperator",
            "signed_content_sha256": "c" * 64,
            "signature_armored": "-----BEGIN PGP SIGNATURE-----\n-----END PGP SIGNATURE-----\n",
        },
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
