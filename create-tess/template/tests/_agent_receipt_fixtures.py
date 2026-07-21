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
import os
import subprocess
import sys
import uuid
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
    else:
        policy_decision = {
            "source": "core/policy/policy.yaml", "rule_id": "money-movement",
            "rule_kind": "hard_floor_rule", "category": "money_movement",
            "description": "Hard floor: money movement requires sign-off.",
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
    return {"fingerprint": key.fpr, "public_key_bytes": key.pubkey_armored.encode("utf-8")}


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
