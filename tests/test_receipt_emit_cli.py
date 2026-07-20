"""
tools/receipt-emit/receipt_emit.py — CLI round trip (subprocess, real GPG
keys, real self-verify subprocess into tools/receipt-verify).

Exercises the actual CLI entry point exactly the way an operator would: as
a subprocess, with genuine GPG signatures and a genuine
`tools/receipt-verify` self-verify call — never mocked. Unit-level
coverage of the underlying pipeline (policy lookup, decision-kind
inference, identity/pairing checks, atomic-append crash-safety) lives in
`tests/test_receipt_emit_semantics.py`.
"""

from __future__ import annotations

import hashlib
import json

from _agent_receipt_fixtures import base_signoff, base_verdict
from _receipt_emit_fixtures import (
    canonical,
    export_public_key,
    run_emit_cli,
    write_decision,
    write_test_policy,
)
from conftest import sign_signoff_for_test, sign_verdict_for_test


def _emit_args(*, decision_path, rule_id, policy_path, actor, summary, key, chain_path, extra_trust=None):
    args = [
        "--decision", str(decision_path),
        "--rule-id", rule_id,
        "--policy", str(policy_path),
        "--actor", actor,
        "--summary", summary,
        "--key-id", key.fpr,
        "--chain", str(chain_path),
        "--gnupg-home", str(key.home),
        "--json",
    ]
    for name, fingerprint, keyfile in extra_trust or []:
        args += ["--trust", name, fingerprint, str(keyfile)]
    return args


def test_happy_emit_reports_chain_intact_and_appends_genesis_receipt(tmp_path, engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    decision_path = write_decision(tmp_path, "verdict.json", verdict)
    policy_path = write_test_policy(tmp_path)
    chain_path = tmp_path / "chain.jsonl"

    result = run_emit_cli(*_emit_args(
        decision_path=decision_path, rule_id="demo-docs-review", policy_path=policy_path,
        actor="Ada", summary="Proposed a doc change", key=reid, chain_path=chain_path,
    ))

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["emitted"] is True
    assert payload["signed_by"] == "Reid"
    assert payload["sequence"] == 0
    assert payload["trust_status"] == "signed_not_trust_anchored"
    assert "NOT trust-anchored" in payload["honest_label"]

    lines = chain_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    receipt = json.loads(lines[0])
    assert receipt["receipt_id"] == payload["receipt_id"]
    assert receipt["chain"] == {"sequence": 0, "prev_receipt_hash": "GENESIS"}
    assert receipt["decision"] == verdict  # embedded VERBATIM


def test_non_approve_verdict_is_refused_and_writes_no_chain_file(tmp_path, engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    verdict = base_verdict("Reid")
    verdict["disposition"] = "BLOCK"
    verdict["findings"] = [{"severity": "CRITICAL", "location": "x:1", "finding": "f", "risk": "r", "fix": "fix"}]
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    decision_path = write_decision(tmp_path, "verdict.json", verdict)
    policy_path = write_test_policy(tmp_path)
    chain_path = tmp_path / "chain.jsonl"

    result = run_emit_cli(*_emit_args(
        decision_path=decision_path, rule_id="demo-docs-review", policy_path=policy_path,
        actor="Ada", summary="Proposed a doc change", key=reid, chain_path=chain_path,
    ))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["emitted"] is False
    assert any("APPROVE" in r for r in payload["reasons"])
    assert not chain_path.exists()


def test_rule_kind_pairing_mismatch_is_refused_and_writes_no_chain_file(tmp_path, engine, verifier_gpg_keys):
    """A hard_floor_rule (--rule-id money-movement) fired against a verdict
    decision — guardrails.md Rule 18 never allows this pairing."""
    reid = verifier_gpg_keys["Reid"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    decision_path = write_decision(tmp_path, "verdict.json", verdict)
    policy_path = write_test_policy(tmp_path)
    chain_path = tmp_path / "chain.jsonl"

    result = run_emit_cli(*_emit_args(
        decision_path=decision_path, rule_id="money-movement", policy_path=policy_path,
        actor="Ada", summary="Proposed a money movement", key=reid, chain_path=chain_path,
    ))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["emitted"] is False
    assert any("Rule 18" in r for r in payload["reasons"])
    assert not chain_path.exists()


def test_unknown_rule_id_is_refused_and_writes_no_chain_file(tmp_path, engine, verifier_gpg_keys):
    reid = verifier_gpg_keys["Reid"]
    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    decision_path = write_decision(tmp_path, "verdict.json", verdict)
    policy_path = write_test_policy(tmp_path)
    chain_path = tmp_path / "chain.jsonl"

    result = run_emit_cli(*_emit_args(
        decision_path=decision_path, rule_id="does-not-exist", policy_path=policy_path,
        actor="Ada", summary="s", key=reid, chain_path=chain_path,
    ))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["emitted"] is False
    assert any("no rule with id" in r for r in payload["reasons"])
    assert not chain_path.exists()


def test_two_emit_chain_continuity_verdict_then_signoff_different_identities(tmp_path, engine, verifier_gpg_keys):
    """Mirrors examples/receipt-demo/'s own scenario: an AI verdict
    (Reid) followed by a human hard-floor sign-off (here signed by the
    Cyra test identity, standing in for a human operator), chained onto
    the SAME --chain file across two separate `emit` invocations. Proves
    sequence/prev_hash continuity AND that --trust correctly extends
    self-verify to cover an identity earlier in the chain."""
    reid = verifier_gpg_keys["Reid"]
    cyra = verifier_gpg_keys["Cyra"]
    policy_path = write_test_policy(tmp_path)
    chain_path = tmp_path / "chain.jsonl"

    verdict = base_verdict("Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, reid)
    verdict_path = write_decision(tmp_path, "verdict.json", verdict)

    genesis_result = run_emit_cli(*_emit_args(
        decision_path=verdict_path, rule_id="demo-docs-review", policy_path=policy_path,
        actor="Ada", summary="Proposed a doc change", key=reid, chain_path=chain_path,
    ))
    assert genesis_result.returncode == 0, genesis_result.stdout + genesis_result.stderr
    genesis_payload = json.loads(genesis_result.stdout)
    assert genesis_payload["sequence"] == 0

    signoff = base_signoff("TestOperator")
    signoff["signature"] = sign_signoff_for_test(engine, signoff, cyra)
    signoff_path = write_decision(tmp_path, "signoff.json", signoff)
    reid_pub = export_public_key(reid, tmp_path, "reid-public.asc")

    second_result = run_emit_cli(*_emit_args(
        decision_path=signoff_path, rule_id="money-movement", policy_path=policy_path,
        actor="Ada", summary="Proposed a sandbox money movement", key=cyra, chain_path=chain_path,
        extra_trust=[("Reid", reid.fpr, reid_pub)],
    ))
    assert second_result.returncode == 0, second_result.stdout + second_result.stderr
    second_payload = json.loads(second_result.stdout)
    assert second_payload["sequence"] == 1
    assert second_payload["signed_by"] == "TestOperator"

    lines = chain_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    genesis_receipt = json.loads(lines[0])
    second_receipt = json.loads(lines[1])
    assert second_receipt["chain"]["sequence"] == 1
    assert second_receipt["chain"]["prev_receipt_hash"] == canonical.receipt_content_hash(genesis_receipt)
    assert second_receipt["decision_kind"] == "signoff"
    assert second_receipt["policy_decision"]["rule_kind"] == "hard_floor_rule"

    # Independently re-verify the WHOLE chain the same way an external
    # party would, using the standalone verifier directly (not this tool).
    import subprocess
    import sys
    from _receipt_emit_fixtures import RECEIPT_VERIFY_DIR

    verify_result = subprocess.run(
        [sys.executable, str(RECEIPT_VERIFY_DIR / "receipt_verify.py"), "verify-chain", str(chain_path),
         "--trust", "Reid", reid.fpr, str(reid_pub),
         "--trust", "TestOperator", cyra.fpr, str(export_public_key(cyra, tmp_path, "cyra-public.asc")),
         "--json"],
        capture_output=True, text=True,
    )
    assert verify_result.returncode == 0, verify_result.stdout + verify_result.stderr
    verify_payload = json.loads(verify_result.stdout)
    assert verify_payload["chain_intact"] is True
    assert verify_payload["receipt_count"] == 2


def test_emit_refuses_a_decision_shaped_like_neither_verdict_nor_signoff(tmp_path, verifier_gpg_keys):
    """A System-A-shaped (or otherwise unrecognized) decision object must
    be refused, never silently accepted as either kind — the
    'never wrap an HMAC approval in a receipt' guarantee at the tool
    boundary."""
    reid = verifier_gpg_keys["Reid"]
    not_a_decision = {"approval_type": "hmac", "approved": True, "run_id": "abc123"}
    decision_path = write_decision(tmp_path, "not-a-decision.json", not_a_decision)
    policy_path = write_test_policy(tmp_path)
    chain_path = tmp_path / "chain.jsonl"

    result = run_emit_cli(*_emit_args(
        decision_path=decision_path, rule_id="demo-docs-review", policy_path=policy_path,
        actor="Ada", summary="s", key=reid, chain_path=chain_path,
    ))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["emitted"] is False
    assert any("does not structurally match" in r for r in payload["reasons"])
    assert not chain_path.exists()
