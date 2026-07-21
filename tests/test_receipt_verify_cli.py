"""
tools/receipt-verify/receipt_verify.py — CLI round trip (subprocess).

Exercises the actual CLI entry point exactly the way an external caller
would: as a subprocess, with real GPG signatures, checking exit codes and
`--json` output shape. Semantic/unit-level coverage of the underlying checks
lives in `tests/test_receipt_verify_semantics.py`.
"""

from __future__ import annotations

import json

from _agent_receipt_fixtures import (
    base_local_approval,
    base_signoff,
    base_verdict,
    build_local_approval_signed_receipt,
    build_signed_receipt,
    canonical,
    generate_local_hmac_key,
    run_cli,
    write_key,
)
from conftest import sign_signoff_for_test, sign_verdict_for_test


def test_cli_verify_valid_receipt_exits_zero(tmp_path, engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    receipt = build_signed_receipt("verdict", verdict, "Reid", reid)

    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    key_path = write_key(tmp_path, "reid.asc", reid)

    result = run_cli("verify", str(receipt_path), "--trust", "Reid", reid.fpr, str(key_path), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["reasons"] == []


def test_cli_verify_tampered_receipt_exits_nonzero(tmp_path, engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    receipt = build_signed_receipt("verdict", verdict, "Reid", reid)
    receipt["decision"]["summary_line"] = "TAMPERED"

    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    key_path = write_key(tmp_path, "reid.asc", reid)

    result = run_cli("verify", str(receipt_path), "--trust", "Reid", reid.fpr, str(key_path), "--json")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert payload["reasons"]


def test_cli_verify_chain_reports_chain_intact(tmp_path, engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    cyra = verifier_gpg_keys["Cyra"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    genesis = build_signed_receipt("verdict", verdict, "Reid", reid)

    signoff = base_signoff("TestOperator")
    signoff["signature"] = sign_signoff_for_test(engine, signoff, cyra)
    second = build_signed_receipt(
        "signoff", signoff, "TestOperator", cyra,
        sequence=1, prev_hash=canonical.receipt_content_hash(genesis), rule_kind="hard_floor_rule",
    )

    chain_path = tmp_path / "chain.jsonl"
    chain_path.write_text(json.dumps(genesis) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
    reid_key_path = write_key(tmp_path, "reid.asc", reid)
    cyra_key_path = write_key(tmp_path, "cyra.asc", cyra)

    result = run_cli(
        "verify-chain", str(chain_path),
        "--trust", "Reid", reid.fpr, str(reid_key_path),
        "--trust", "TestOperator", cyra.fpr, str(cyra_key_path),
        "--json",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["chain_intact"] is True
    assert payload["receipt_count"] == 2
    assert payload["failures"] == []


def test_cli_verify_chain_reports_chain_broken(tmp_path, engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    cyra = verifier_gpg_keys["Cyra"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    genesis = build_signed_receipt("verdict", verdict, "Reid", reid)

    signoff = base_signoff("TestOperator")
    signoff["signature"] = sign_signoff_for_test(engine, signoff, cyra)
    second = build_signed_receipt(
        "signoff", signoff, "TestOperator", cyra,
        sequence=1, prev_hash="f" * 64, rule_kind="hard_floor_rule",  # WRONG on purpose
    )

    chain_path = tmp_path / "chain.jsonl"
    chain_path.write_text(json.dumps(genesis) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
    reid_key_path = write_key(tmp_path, "reid.asc", reid)
    cyra_key_path = write_key(tmp_path, "cyra.asc", cyra)

    result = run_cli(
        "verify-chain", str(chain_path),
        "--trust", "Reid", reid.fpr, str(reid_key_path),
        "--trust", "TestOperator", cyra.fpr, str(cyra_key_path),
        "--json",
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["chain_intact"] is False
    assert len(payload["failures"]) == 1
    assert payload["failures"][0]["index"] == 1


# ---------------------------------------------------------------------------
# decision_kind: local_approval (wedge-loop epic addition) — CLI round trip,
# System A (local HMAC), --trust KEYFILE is a raw SECRET key here, not a
# GPG public key — see receipt_verify.py's own module docstring "★" note.
# ---------------------------------------------------------------------------


def test_cli_verify_valid_local_approval_receipt_exits_zero(tmp_path):
    key = generate_local_hmac_key()
    identity = "local:tester#" + key.fingerprint
    decision = base_local_approval(approved_by=identity, key=key)
    receipt = build_local_approval_signed_receipt(decision, identity, key)

    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    key_path = tmp_path / "local-approval.key"
    key_path.write_bytes(key.key_bytes)

    result = run_cli("verify", str(receipt_path), "--trust", identity, key.fingerprint, str(key_path), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["reasons"] == []


def test_cli_verify_local_approval_receipt_wrong_key_exits_nonzero(tmp_path):
    key = generate_local_hmac_key()
    identity = "local:tester#" + key.fingerprint
    decision = base_local_approval(approved_by=identity, key=key)
    receipt = build_local_approval_signed_receipt(decision, identity, key)

    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    wrong_key = generate_local_hmac_key()
    key_path = tmp_path / "wrong.key"
    key_path.write_bytes(wrong_key.key_bytes)

    result = run_cli("verify", str(receipt_path), "--trust", identity, key.fingerprint, str(key_path), "--json")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert payload["reasons"]
