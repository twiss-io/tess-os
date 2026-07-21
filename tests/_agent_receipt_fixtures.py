"""Shared builders for the Agent Receipt test suite.

Not a test module itself (no `test_` prefix — pytest never collects it).
Shared by `test_receipt_verify_semantics.py` and `test_receipt_verify_cli.py`
so both stay focused and under this repository's file-length convention
rather than duplicating the same receipt-building boilerplate twice.

tools/receipt-verify/ deliberately does not import `.tess/bin/tessctl` (see
tools/receipt-verify/README.md "Why standalone"), so its modules are loaded
directly by path here rather than through the `engine` fixture. `engine`
itself is only used, via `tests/conftest.py`'s `sign_verdict_for_test` /
`sign_signoff_for_test`, to sign the EMBEDDED decision objects with
tessctl's own canonicalization — proving, as a side effect, that this tool's
independent `canonical.py` reimplementation produces byte-identical
canonical forms to `verdict_canonical_bytes`/`signoff_canonical_bytes` (a
signature made with one only verifies against the other because both hash
the exact same bytes).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL_DIR = REPO_ROOT / "tools" / "receipt-verify"
RECEIPT_VERIFY_CLI = TOOL_DIR / "receipt_verify.py"

sys.path.insert(0, str(TOOL_DIR))
import canonical  # noqa: E402
import checks  # noqa: E402


def now_iso() -> str:
    return "2026-07-19T00:00:00.000000Z"


def base_verdict(verifier="Reid"):
    return {
        "verifier": verifier,
        "output_domain": "Code diff / PR",
        "primary_artifacts_read": ["docs/AGENT_RECEIPT_SPEC.md"],
        "findings": [],
        "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "summary_line": "Reviewed. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Top priority: none.",
        "disposition": "APPROVE",
    }


def base_signoff(authorized_by="TestOperator"):
    return {
        "rule_id": "demo-money-movement",
        "category": "money_movement",
        "authorized_by": authorized_by,
        "rationale": "Test-only rationale, sandbox transfer.",
        "authorized_at": now_iso(),
    }


def build_envelope(*, decision_kind, decision, sequence=0, prev_hash="GENESIS",
                    rule_kind="path_rule"):
    if rule_kind == "path_rule":
        policy_decision = {
            "source": "core/policy/policy.yaml", "rule_id": "docs-review",
            "rule_kind": "path_rule", "classification": ["prod_touching"],
            "description": "Doc change requires review.",
        }
    elif rule_kind == "hard_floor_rule":
        policy_decision = {
            "source": "core/policy/policy.yaml", "rule_id": "money-movement",
            "rule_kind": "hard_floor_rule", "category": "money_movement",
            "description": "Hard floor: money movement requires sign-off.",
        }
    else:
        policy_decision = {
            "source": "orchestrator/approval_gate.py", "rule_id": "orchestrator-pipeline-hop3-approval-gate",
            "rule_kind": "pipeline_approval_gate",
            "description": "run_pipeline() Hop 3 requires an authenticated ApprovalGate decision.",
        }
    return {
        "receipt_schema": "tess-os.agent-receipt/1",
        "receipt_id": uuid.uuid4().hex,
        "issued_at": now_iso(),
        "proposed_action": {"actor": "Ada", "summary": "Test proposal"},
        "policy_decision": policy_decision,
        "decision_kind": decision_kind,
        "decision": decision,
        "chain": {"sequence": sequence, "prev_receipt_hash": prev_hash},
    }


def trust_entry(key):
    return {"fingerprint": key.fpr, "key_bytes": key.pubkey_armored.encode("utf-8")}


def gpg_sign_receipt(receipt, signer_name, key):
    """Sign a receipt envelope's own `receipt_signature` using OUR
    canonicalization (`canonical.receipt_signing_bytes` — a compact,
    key-sorted, minus-one-key JSON form exactly like
    `verdict_canonical_bytes`), and a plain `gpg --detach-sign`, the same
    primitive `tessctl verdict sign` and this repository's `conftest.py`
    helpers both already use."""
    canon = canonical.receipt_signing_bytes(receipt)
    content_hash = hashlib.sha256(canon).hexdigest()
    env = {**os.environ, "GNUPGHOME": str(key.home)}
    result = subprocess.run(
        ["gpg", "--homedir", str(key.home), "--batch", "--yes", "--local-user", key.fpr,
         "--detach-sign", "--armor", "--output", "-"],
        input=canon, capture_output=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    return {
        "algorithm": "gpg-detached-armor",
        "signed_by": signer_name,
        "signed_content_sha256": content_hash,
        "signature_armored": result.stdout.decode("utf-8"),
    }


def build_signed_receipt(decision_kind, decision, signer_name, signer_key,
                          sequence=0, prev_hash="GENESIS", rule_kind="path_rule"):
    receipt = build_envelope(decision_kind=decision_kind, decision=decision,
                              sequence=sequence, prev_hash=prev_hash, rule_kind=rule_kind)
    receipt["receipt_signature"] = gpg_sign_receipt(receipt, signer_name, signer_key)
    return receipt


def write_key(tmp_path, filename, key):
    p = tmp_path / filename
    p.write_text(key.pubkey_armored, encoding="utf-8")
    return p


def run_cli(*args):
    return subprocess.run([sys.executable, str(RECEIPT_VERIFY_CLI), *args], capture_output=True, text=True)


# ---------------------------------------------------------------------------
# decision_kind: local_approval (wedge-loop epic addition) — System A,
# local HMAC-SHA256, DELIBERATELY reimplemented here rather than importing
# spec_engine.gate_identity, mirroring how `conftest.py`'s `verifier_gpg_keys`
# generates REAL, independent GPG keys directly rather than importing
# tessctl's own signing helpers — genuine test data, built independently of
# the code under test, proves the real algorithm rather than a mock of it.
# See tools/receipt-verify/hmac_verify.py for the standalone VERIFIER this
# builds fixtures for.
# ---------------------------------------------------------------------------

LOCAL_HMAC_MECHANISM = "local-hmac-sha256-v1"


@dataclass(frozen=True)
class LocalHmacKey:
    """A throwaway local approval-identity key, mirroring
    `spec_engine.gate_identity.LocalIdentity` closely enough for test
    fixtures (`key_bytes` instead of a `key_path` — tests build this
    in-memory, never touching a real `~/.tess-os/approval-identity/`
    file)."""

    key_bytes: bytes
    fingerprint: str


def generate_local_hmac_key() -> LocalHmacKey:
    """A genuinely random 32-byte key + its `sha256(key)[:16]`
    fingerprint — the EXACT `spec_engine.gate_identity` convention,
    reimplemented here (not imported) for the same standalone-fixture
    independence `verifier_gpg_keys` already establishes for GPG."""
    key_bytes = secrets.token_bytes(32)
    fingerprint = hashlib.sha256(key_bytes).hexdigest()[:16]
    return LocalHmacKey(key_bytes=key_bytes, fingerprint=fingerprint)


def base_local_approval(*, approved_by, key: LocalHmacKey, approved=True,
                         plan_id="plan-test001", content_hash="d" * 64, human_notes=""):
    """A genuinely HMAC-signed `LocalApprovalArtifact` decision — the
    EXACT `spec_engine.gate_identity.canonical_payload()` /
    `sign_payload()` math (compact, key-sorted JSON, `ensure_ascii`
    default True), reimplemented here so `hmac_verify.
    verify_local_approval_decision()` can genuinely re-verify it, the
    same "independent re-implementation, real signature" discipline
    `sign_verdict_for_test`/`sign_signoff_for_test` already apply for
    GPG."""
    approval_id = "appr-" + uuid.uuid4().hex[:12]
    approved_at = now_iso()
    nonce = "nonce-" + uuid.uuid4().hex[:12]
    payload = {
        "approval_id": approval_id, "plan_id": plan_id, "content_hash": content_hash,
        "approved": approved, "approved_by": approved_by, "approved_at": approved_at, "nonce": nonce,
    }
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(key.key_bytes, canon, hashlib.sha256).hexdigest()
    notes = json.dumps({
        "human_notes": human_notes,
        "auth": {
            "mechanism": LOCAL_HMAC_MECHANISM, "identity_fingerprint": key.fingerprint,
            "content_hash": content_hash, "nonce": nonce, "signature": signature,
        },
    })
    return {
        "approval_id": approval_id, "plan_id": plan_id, "approved": approved,
        "approved_by": approved_by, "approved_at": approved_at, "notes": notes,
    }


def local_hmac_trust_entry(key: LocalHmacKey) -> dict:
    return {"fingerprint": key.fingerprint, "key_bytes": key.key_bytes}


def hmac_sign_receipt(receipt: dict, signer_name: str, key: LocalHmacKey) -> dict:
    """Sign a receipt envelope's own `receipt_signature` with
    `algorithm: "local-hmac-sha256-v1"`, using OUR canonicalization
    (`canonical.receipt_signing_bytes` — the SAME compact/key-sorted form
    a GPG-backed envelope already uses; only the crypto operation
    differs) and a genuine HMAC-SHA256 over it."""
    canon = canonical.receipt_signing_bytes(receipt)
    content_hash = hashlib.sha256(canon).hexdigest()
    signature_hex = hmac.new(key.key_bytes, canon, hashlib.sha256).hexdigest()
    return {
        "algorithm": "local-hmac-sha256-v1",
        "signed_by": signer_name,
        "signed_content_sha256": content_hash,
        "signature_hex": signature_hex,
    }


def build_local_approval_signed_receipt(decision, signer_name, key: LocalHmacKey,
                                         sequence=0, prev_hash="GENESIS",
                                         rule_kind="pipeline_approval_gate"):
    receipt = build_envelope(decision_kind="local_approval", decision=decision,
                              sequence=sequence, prev_hash=prev_hash, rule_kind=rule_kind)
    receipt["receipt_signature"] = hmac_sign_receipt(receipt, signer_name, key)
    return receipt
