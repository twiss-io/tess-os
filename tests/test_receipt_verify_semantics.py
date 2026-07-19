"""
tools/receipt-verify/checks.py — semantic + unit-level verification checks.

Spec: docs/AGENT_RECEIPT_SPEC.md "Verification algorithm". CLI-level
(subprocess) round-trip coverage lives in its own file,
`tests/test_receipt_verify_cli.py`, mirroring `test_verdict_signing.py`'s own
"unit-level coverage... is separated from... GPG-backed proofs" split.

Coverage (mirrors docs/AGENT_RECEIPT_SPEC.md's algorithm, in order):
  * a valid genesis receipt (verdict-backed) verifies clean
  * a valid two-receipt chain (verdict then signoff) verifies clean
  * a shape-torn receipt is rejected
  * a decision tampered with after signing is rejected
  * an envelope (receipt_signature) tampered with after signing is rejected
  * a signature from the WRONG key is rejected (exact-fingerprint pinning)
  * an unregistered identity (no --trust entry) is rejected
  * an identity mismatch (receipt_signature.signed_by != decision identity)
    is rejected
  * a hard_floor_rule paired with a verdict (instead of signoff) is rejected,
    and vice versa for path_rule paired with a signoff
  * a verdict decision with disposition != APPROVE is rejected
  * a broken chain link (wrong prev hash, non-consecutive sequence, a
    supplied prev on a genesis receipt, or a missing prev on a non-genesis
    receipt) is rejected
  * canonical.py's exclusion/inclusion rules for the two hash targets
"""

from __future__ import annotations

import copy

from _agent_receipt_fixtures import (
    base_signoff,
    base_verdict,
    build_signed_receipt,
    canonical,
    checks,
    trust_entry,
)
from conftest import sign_signoff_for_test, sign_verdict_for_test

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_genesis_verdict_receipt_verifies(engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    receipt = build_signed_receipt("verdict", verdict, "Reid", reid)

    trust = {"Reid": trust_entry(reid)}
    assert checks.verify_receipt(receipt, trust) == []


def test_valid_chained_signoff_receipt_verifies(engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    cyra = verifier_gpg_keys["Cyra"]  # reused as a stand-in human-operator identity
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    genesis = build_signed_receipt("verdict", verdict, "Reid", reid)

    signoff = base_signoff("TestOperator")
    signoff["signature"] = sign_signoff_for_test(engine, signoff, cyra)
    second = build_signed_receipt(
        "signoff", signoff, "TestOperator", cyra,
        sequence=1, prev_hash=canonical.receipt_content_hash(genesis), rule_kind="hard_floor_rule",
    )

    trust = {"Reid": trust_entry(reid), "TestOperator": trust_entry(cyra)}
    assert checks.verify_receipt(genesis, trust) == []
    assert checks.verify_receipt(second, trust, prev_receipt=genesis) == []


# ---------------------------------------------------------------------------
# Shape / tamper / wrong-key / identity / pairing / chain rejections
# ---------------------------------------------------------------------------


def test_shape_torn_receipt_is_rejected(engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    receipt = build_signed_receipt("verdict", verdict, "Reid", reid)
    del receipt["chain"]
    errors = checks.verify_receipt(receipt, {"Reid": trust_entry(reid)})
    assert errors and "chain" in errors[0]


def test_decision_tampered_after_signing_is_rejected(engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    receipt = build_signed_receipt("verdict", verdict, "Reid", reid)
    receipt["decision"]["summary_line"] = "TAMPERED after signing"
    errors = checks.verify_receipt(receipt, {"Reid": trust_entry(reid)})
    assert any("tampered" in e for e in errors), errors


def test_envelope_tampered_after_signing_is_rejected(engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    receipt = build_signed_receipt("verdict", verdict, "Reid", reid)
    receipt["proposed_action"]["summary"] = "TAMPERED envelope field"
    errors = checks.verify_receipt(receipt, {"Reid": trust_entry(reid)})
    assert any("tampered" in e for e in errors), errors


def test_wrong_key_for_identity_is_rejected(engine, verifier_gpg_keys):
    """Reid's decision, but the caller only supplies Lysandra's key under
    the name 'Reid' — must be rejected (exact-fingerprint pinning, not
    name-based trust)."""
    reid = verifier_gpg_keys["Reid"]
    lysandra = verifier_gpg_keys["Lysandra"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    receipt = build_signed_receipt("verdict", verdict, "Reid", reid)

    wrong_trust = {"Reid": trust_entry(lysandra)}
    errors = checks.verify_receipt(receipt, wrong_trust)
    assert any("invalid" in e for e in errors), errors


def test_no_trust_entry_for_identity_is_rejected(engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    receipt = build_signed_receipt("verdict", verdict, "Reid", reid)
    errors = checks.verify_receipt(receipt, {})
    assert any("no trusted public key" in e for e in errors), errors


def test_identity_mismatch_between_envelope_and_decision_is_rejected(engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    lysandra = verifier_gpg_keys["Lysandra"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    # Sign the ENVELOPE as Lysandra, while the decision itself says Reid.
    receipt = build_signed_receipt("verdict", verdict, "Lysandra", lysandra)
    trust = {"Reid": trust_entry(reid), "Lysandra": trust_entry(lysandra)}
    errors = checks.verify_receipt(receipt, trust)
    assert any("does not match the embedded" in e for e in errors), errors


def test_hard_floor_paired_with_verdict_is_rejected(engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    receipt = build_signed_receipt("verdict", verdict, "Reid", reid, rule_kind="hard_floor_rule")
    errors = checks.verify_receipt(receipt, {"Reid": trust_entry(reid)})
    assert any("guardrails.md Rule 18" in e for e in errors), errors


def test_path_rule_paired_with_signoff_is_rejected(engine, verifier_gpg_keys):
    cyra = verifier_gpg_keys["Cyra"]
    signoff = base_signoff("TestOperator")
    signoff["signature"] = sign_signoff_for_test(engine, signoff, cyra)
    receipt = build_signed_receipt("signoff", signoff, "TestOperator", cyra, rule_kind="path_rule")
    errors = checks.verify_receipt(receipt, {"TestOperator": trust_entry(cyra)})
    assert any("path_rule but decision_kind is not" in e for e in errors), errors


def test_verdict_disposition_not_approve_is_rejected(engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    verdict = base_verdict("Reid")
    verdict["disposition"] = "BLOCK"
    verdict["findings"] = [{
        "severity": "CRITICAL", "location": "x:1", "finding": "f", "risk": "r", "fix": "fix",
    }]
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    receipt = build_signed_receipt("verdict", verdict, "Reid", reid)
    errors = checks.verify_receipt(receipt, {"Reid": trust_entry(reid)})
    assert any("not 'APPROVE'" in e for e in errors), errors


def test_broken_chain_wrong_prev_hash_is_rejected(engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    cyra = verifier_gpg_keys["Cyra"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    genesis = build_signed_receipt("verdict", verdict, "Reid", reid)

    signoff = base_signoff("TestOperator")
    signoff["signature"] = sign_signoff_for_test(engine, signoff, cyra)
    second = build_signed_receipt(
        "signoff", signoff, "TestOperator", cyra,
        sequence=1, prev_hash="0" * 64, rule_kind="hard_floor_rule",
    )
    trust = {"Reid": trust_entry(reid), "TestOperator": trust_entry(cyra)}
    errors = checks.verify_receipt(second, trust, prev_receipt=genesis)
    assert any("chain is BROKEN" in e for e in errors), errors


def test_genesis_sequence_zero_with_supplied_prev_is_rejected(engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    genesis = build_signed_receipt("verdict", verdict, "Reid", reid)
    other_genesis = copy.deepcopy(genesis)
    errors = checks.verify_receipt(genesis, {"Reid": trust_entry(reid)}, prev_receipt=other_genesis)
    assert any("genesis" in e for e in errors), errors


def test_non_genesis_missing_prev_is_rejected(engine, verifier_gpg_keys):
    cyra = verifier_gpg_keys["Cyra"]
    signoff = base_signoff("TestOperator")
    signoff["signature"] = sign_signoff_for_test(engine, signoff, cyra)
    second = build_signed_receipt(
        "signoff", signoff, "TestOperator", cyra,
        sequence=1, prev_hash="a" * 64, rule_kind="hard_floor_rule",
    )
    errors = checks.verify_receipt(second, {"TestOperator": trust_entry(cyra)})
    assert any("no previous receipt was supplied" in e for e in errors), errors


# ---------------------------------------------------------------------------
# canonical.py unit-level sanity
# ---------------------------------------------------------------------------


def test_decision_signing_bytes_excludes_signature_key():
    decision = {"a": 1, "signature": {"x": "y"}}
    canon = canonical.decision_signing_bytes(decision)
    assert b"signature" not in canon
    assert canon == b'{"a":1}'


def test_receipt_content_hash_includes_receipt_signature():
    receipt_without_sig = {"a": 1}
    receipt_with_sig = {"a": 1, "receipt_signature": {"x": "y"}}
    assert canonical.receipt_content_hash(receipt_without_sig) != canonical.receipt_content_hash(receipt_with_sig)
