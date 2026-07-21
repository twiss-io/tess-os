# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Twiss
"""Structural + semantic checks for an Agent Receipt.

Deliberately hand-written, explicit field checks rather than a bundled
generic JSON Schema engine — the same "explicit checks over generic
machinery" choice `.tess/bin/tessctl`'s own `_gate_validate_signoff` already
makes for the sign-off shape. core/contracts/agent-receipt.schema.json is the
authoritative, generically-checkable form (validate with `tessctl validate`
against a full Tess OS checkout); this module is the independent,
dependency-free twin used when only this tool is available. See
docs/AGENT_RECEIPT_SPEC.md "Verification algorithm" for the doctrine this
mirrors step for step.
"""

from __future__ import annotations

from canonical import decision_signing_bytes, receipt_content_hash, receipt_signing_bytes, sha256_hex
from gpg_verify import verify_detached_signature

RECEIPT_SCHEMA_VERSION = "tess-os.agent-receipt/1"
DECISION_KINDS = ("verdict", "signoff")
RULE_KINDS = ("path_rule", "hard_floor_rule")
HARD_FLOOR_CATEGORIES = ("credentials", "money_movement", "destructive_prod_data", "client_external_claims")

REQUIRED_TOP_KEYS = (
    "receipt_schema", "receipt_id", "issued_at", "proposed_action",
    "policy_decision", "decision_kind", "decision", "chain", "receipt_signature",
)
SIGNOFF_REQUIRED_KEYS = ("rule_id", "category", "authorized_by", "rationale", "authorized_at", "signature")
VERDICT_REQUIRED_KEYS = (
    "verifier", "output_domain", "primary_artifacts_read", "findings",
    "severity_counts", "summary_line", "disposition",
)


def check_receipt_shape(receipt: dict) -> list[str]:
    """Structural sanity only — the subset of agent-receipt.schema.json's
    shape this standalone tool checks without a generic schema engine."""
    errors = []
    if not isinstance(receipt, dict):
        return ["receipt is not a JSON object"]
    missing = [k for k in REQUIRED_TOP_KEYS if k not in receipt]
    if missing:
        errors.append(f"missing required top-level field(s): {missing}")
        return errors  # further checks would be misleading on a torn shape
    if receipt["receipt_schema"] != RECEIPT_SCHEMA_VERSION:
        errors.append(f"receipt_schema {receipt['receipt_schema']!r} != expected {RECEIPT_SCHEMA_VERSION!r}")
    if receipt["decision_kind"] not in DECISION_KINDS:
        errors.append(f"decision_kind {receipt['decision_kind']!r} is not one of {DECISION_KINDS}")
    if not isinstance(receipt.get("decision"), dict):
        errors.append("decision is not a JSON object")
    chain = receipt.get("chain")
    if not isinstance(chain, dict) or "sequence" not in chain or "prev_receipt_hash" not in chain:
        errors.append("chain is missing 'sequence' or 'prev_receipt_hash'")
    sig = receipt.get("receipt_signature")
    if not isinstance(sig, dict) or not {"algorithm", "signed_by", "signed_content_sha256", "signature_armored"} <= sig.keys():
        errors.append("receipt_signature is missing a required field")
    return errors


def check_decision_shape(decision_kind: str, decision: dict) -> list[str]:
    required = VERDICT_REQUIRED_KEYS if decision_kind == "verdict" else SIGNOFF_REQUIRED_KEYS
    missing = [k for k in required if k not in decision]
    errors = [f"decision (kind={decision_kind}) missing required field(s): {missing}"] if missing else []
    if not isinstance(decision.get("signature"), dict):
        errors.append("decision.signature is missing or not an object")
    elif not {"algorithm", "signed_content_sha256", "signature_armored"} <= decision["signature"].keys():
        errors.append("decision.signature is missing a required field")
    if decision_kind == "verdict" and decision.get("disposition") != "APPROVE":
        errors.append(
            f"decision.disposition is {decision.get('disposition')!r}, not 'APPROVE' — a receipt "
            f"can only represent a GRANTED approval, never a BLOCK or other disposition"
        )
    return errors


def identity_for(decision_kind: str, decision: dict) -> str | None:
    return decision.get("verifier") if decision_kind == "verdict" else decision.get("authorized_by")


def _content_hash_check(obj: dict, content_key: str, signing_bytes_fn) -> list[str]:
    """Shared tamper-detection step for both `decision.signature` and
    `receipt_signature`: the declared signed_content_sha256 must match the
    CURRENT canonical bytes, checked before the (more expensive) gpg call."""
    sig = obj["signature"] if content_key == "decision" else obj["receipt_signature"]
    declared = sig.get("signed_content_sha256", "")
    actual = sha256_hex(signing_bytes_fn(obj))
    if declared != actual:
        return [
            f"{content_key}.signature.signed_content_sha256 does not match the CURRENT canonical "
            f"content — {content_key} was edited/tampered with after signing (fail-closed)"
        ]
    return []


def verify_decision_signature(decision_kind: str, decision: dict, trust: dict) -> list[str]:
    """Verify the embedded decision's OWN signature (the AI verifier's
    verdict, or the human operator's sign-off) against the caller-supplied,
    fingerprint-pinned trust map. `trust` is {identity: {"fingerprint": str,
    "public_key_bytes": bytes}}."""
    errors = _content_hash_check(decision, "decision", decision_signing_bytes)
    if errors:
        return errors
    identity = identity_for(decision_kind, decision)
    if not identity:
        return [f"decision has no identity field ({'verifier' if decision_kind == 'verdict' else 'authorized_by'})"]
    entry = trust.get(identity)
    if entry is None:
        return [f"no trusted public key supplied for decision identity {identity!r} (--trust)"]
    ok, reason = verify_detached_signature(
        decision_signing_bytes(decision), decision["signature"]["signature_armored"],
        entry["public_key_bytes"], entry["fingerprint"],
    )
    return [] if ok else [f"decision signature invalid for {identity!r}: {reason}"]


def verify_envelope_signature(receipt: dict, trust: dict) -> list[str]:
    """Verify the receipt's own envelope-level `receipt_signature`."""
    errors = _content_hash_check(receipt, "receipt_signature", receipt_signing_bytes)
    if errors:
        return errors
    signed_by = receipt["receipt_signature"]["signed_by"]
    entry = trust.get(signed_by)
    if entry is None:
        return [f"no trusted public key supplied for receipt_signature.signed_by {signed_by!r} (--trust)"]
    ok, reason = verify_detached_signature(
        receipt_signing_bytes(receipt), receipt["receipt_signature"]["signature_armored"],
        entry["public_key_bytes"], entry["fingerprint"],
    )
    return [] if ok else [f"receipt_signature invalid for {signed_by!r}: {reason}"]


def check_identity_consistency(receipt: dict) -> list[str]:
    """`receipt_signature.signed_by` must equal the SAME identity that
    signed the embedded decision — a receipt cannot be co-signed by one
    party over another party's decision."""
    decision_identity = identity_for(receipt["decision_kind"], receipt["decision"])
    signed_by = receipt["receipt_signature"]["signed_by"]
    if decision_identity != signed_by:
        return [
            f"receipt_signature.signed_by ({signed_by!r}) does not match the embedded "
            f"decision's own identity ({decision_identity!r}) — an Agent Receipt's envelope "
            f"must be signed by the SAME party who signed the decision it wraps"
        ]
    return []


def check_policy_pairing(receipt: dict) -> list[str]:
    """guardrails.md Rule 18: a hard-floor category is NEVER satisfiable by a
    verdict alone; a path_rule is covered by a verdict, never a sign-off."""
    policy = receipt.get("policy_decision") or {}
    rule_kind = policy.get("rule_kind")
    decision_kind = receipt.get("decision_kind")
    if rule_kind == "hard_floor_rule" and decision_kind != "signoff":
        return ["policy_decision.rule_kind is hard_floor_rule but decision_kind is not 'signoff' (guardrails.md Rule 18: never verdict-satisfiable)"]
    if rule_kind == "path_rule" and decision_kind != "verdict":
        return ["policy_decision.rule_kind is path_rule but decision_kind is not 'verdict'"]
    return []


def check_chain_link(receipt: dict, prev_receipt: dict | None) -> list[str]:
    chain = receipt["chain"]
    sequence = chain.get("sequence")
    prev_hash = chain.get("prev_receipt_hash")
    if sequence == 0:
        if prev_hash != "GENESIS":
            return [f"chain.sequence is 0 but prev_receipt_hash is {prev_hash!r}, expected 'GENESIS'"]
        if prev_receipt is not None:
            return ["chain.sequence is 0 (genesis) but a previous receipt was supplied"]
        return []
    if prev_receipt is None:
        return [f"chain.sequence is {sequence}, but no previous receipt was supplied to verify the link against"]
    expected_hash = receipt_content_hash(prev_receipt)
    if prev_hash != expected_hash:
        return [
            f"chain.prev_receipt_hash {prev_hash!r} does not match the previous receipt's actual "
            f"content hash {expected_hash!r} — the chain is BROKEN (an earlier receipt was "
            f"altered, reordered, or a different receipt was substituted)"
        ]
    prev_sequence = (prev_receipt.get("chain") or {}).get("sequence")
    if prev_sequence != sequence - 1:
        return [f"chain.sequence {sequence} does not follow the previous receipt's sequence {prev_sequence}"]
    return []


def verify_receipt(receipt: dict, trust: dict, prev_receipt: dict | None = None) -> list[str]:
    """Run every check in order; returns the combined list of violations
    (empty == the receipt is valid). Order matters: shape checks fail fast
    before any expensive gpg subprocess runs, mirroring `.tess/bin/tessctl`'s
    own "cheap check first" discipline in `_gate_verify_verdict_signature`."""
    errors = check_receipt_shape(receipt)
    if errors:
        return errors
    errors += check_decision_shape(receipt["decision_kind"], receipt["decision"])
    if errors:
        return errors
    errors += check_policy_pairing(receipt)
    errors += check_identity_consistency(receipt)
    errors += verify_decision_signature(receipt["decision_kind"], receipt["decision"], trust)
    errors += verify_envelope_signature(receipt, trust)
    errors += check_chain_link(receipt, prev_receipt)
    return errors
