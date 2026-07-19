# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Twiss
"""Builds the two illustrative Agent Receipts the demo signs and verifies.

Uses tools/receipt-verify/canonical.py directly (the same canonicalization
the standalone verifier itself checks against) so the demo can never drift
out of sync with what verification actually expects.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "receipt-verify"))

from canonical import decision_signing_bytes, receipt_content_hash, receipt_signing_bytes, sha256_hex  # noqa: E402
from demo_keys import DemoKey, sign_with_demo_key  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def build_signed_verdict(reid_key: DemoKey) -> dict:
    """A DEMO-ONLY, ephemeral-key-signed verdict — same shape as a real
    verdict.schema.json instance, never registered against the real
    core/policy/policy.yaml verifier_keys."""
    verdict = {
        "verifier": "Reid",
        "output_domain": "Code diff / PR",
        "primary_artifacts_read": ["docs/AGENT_RECEIPT_SPEC.md"],
        "findings": [],
        "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "summary_line": "Reviewed the demo doc change. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Top priority: none.",
        "disposition": "APPROVE",
    }
    canonical = decision_signing_bytes(verdict)
    verdict["signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": sha256_hex(canonical),
        "signature_armored": sign_with_demo_key(canonical, reid_key),
        "signed_at": _now_iso(),
    }
    return verdict


def build_signed_signoff(operator_key: DemoKey) -> dict:
    """A DEMO-ONLY, ephemeral-key-signed hard-floor sign-off — same shape as
    a real .tess/gate/signoffs/<rule-id>.signoff.json instance."""
    signoff = {
        "rule_id": "demo-money-movement",
        "category": "money_movement",
        "authorized_by": operator_key.name,
        "rationale": "Demo walkthrough: sandbox-to-sandbox transfer between two test accounts, no real funds involved.",
        "authorized_at": _now_iso(),
    }
    canonical = decision_signing_bytes(signoff)
    signoff["signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": sha256_hex(canonical),
        "signature_armored": sign_with_demo_key(canonical, operator_key),
        "signed_at": _now_iso(),
    }
    return signoff


def _envelope(*, sequence: int, prev_hash: str, actor: str, summary: str,
              policy_decision: dict, decision_kind: str, decision: dict) -> dict:
    return {
        "receipt_schema": "tess-os.agent-receipt/1",
        "receipt_id": uuid.uuid4().hex,
        "issued_at": _now_iso(),
        "proposed_action": {"actor": actor, "summary": summary},
        "policy_decision": policy_decision,
        "decision_kind": decision_kind,
        "decision": decision,
        "chain": {"sequence": sequence, "prev_receipt_hash": prev_hash},
    }


def sign_receipt_envelope(receipt: dict, signer: DemoKey) -> dict:
    canonical = receipt_signing_bytes(receipt)
    receipt["receipt_signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_by": signer.name,
        "signed_content_sha256": sha256_hex(canonical),
        "signature_armored": sign_with_demo_key(canonical, signer),
        "signed_at": _now_iso(),
    }
    return receipt


def build_genesis_receipt(reid_key: DemoKey) -> dict:
    verdict = build_signed_verdict(reid_key)
    receipt = _envelope(
        sequence=0,
        prev_hash="GENESIS",
        actor="Ada",
        summary="Proposed a documentation change to docs/AGENT_RECEIPT_SPEC.md",
        policy_decision={
            "source": "core/policy/policy.yaml",
            "rule_id": "demo-docs-review",
            "rule_kind": "path_rule",
            "classification": ["prod_touching"],
            "description": "Illustrative rule for this demo: a doctrine/spec doc change is treated as prod_touching and requires a covering signed verdict.",
        },
        decision_kind="verdict",
        decision=verdict,
    )
    return sign_receipt_envelope(receipt, reid_key)


def build_second_receipt(genesis_receipt: dict, operator_key: DemoKey) -> dict:
    signoff = build_signed_signoff(operator_key)
    receipt = _envelope(
        sequence=1,
        prev_hash=receipt_content_hash(genesis_receipt),
        actor="Ada",
        summary="Proposed a sandbox-to-sandbox test funds transfer",
        policy_decision={
            "source": "core/policy/policy.yaml",
            "rule_id": "demo-money-movement",
            "rule_kind": "hard_floor_rule",
            "category": "money_movement",
            "description": "guardrails.md Rule 18 hard floor #2 (money movement) — never satisfiable by a verdict alone; requires a signed human sign-off.",
        },
        decision_kind="signoff",
        decision=signoff,
    )
    return sign_receipt_envelope(receipt, operator_key)
