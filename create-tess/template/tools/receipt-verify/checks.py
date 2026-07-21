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
from hmac_verify import parse_local_approval_auth, verify_hmac_signature, verify_local_approval_decision

RECEIPT_SCHEMA_VERSION = "tess-os.agent-receipt/1"
# 'local_approval' (wedge-loop epic addition) is SYSTEM A — local, symmetric
# HMAC-SHA256 trust (spec_engine.gate_identity) — DISTINCT FROM, and weaker
# than, 'verdict'/'signoff' (SYSTEM B — GPG, asymmetric, publicly
# verifiable). See core/contracts/agent-receipt.schema.json's own
# decision_kind description and docs/AGENT_RECEIPT_SPEC.md for the full
# trust-level disclosure this module enforces alongside the schema.
DECISION_KINDS = ("verdict", "signoff", "local_approval")
RULE_KINDS = ("path_rule", "hard_floor_rule", "pipeline_approval_gate")
HARD_FLOOR_CATEGORIES = ("credentials", "money_movement", "destructive_prod_data", "client_external_claims")

# TRUST-LEVEL PAIRING (tess-os #162, Cyra LOW-1) — mirrors
# core/contracts/agent-receipt.schema.json's top-level `allOf` rules
# EXPLICITLY, decision_kind -> the one legal receipt_signature.algorithm:
# 'verdict'/'signoff' (System B, GPG) can ONLY pair with
# 'gpg-detached-armor'; 'local_approval' (System A, local HMAC) can ONLY
# pair with 'local-hmac-sha256-v1'. Checked directly in
# `check_receipt_shape` below, rather than left to fall out of the
# fingerprint-length divergence between `hmac_verify.LOCAL_FINGERPRINT_RE`
# (16 hex) and `gpg_verify`'s 40-hex GPG requirement — that divergence
# still independently rejects a mismatched pairing at verification time
# (Cyra's ATTACK 5, #161 review), but this schema's own guarantee should
# never depend on a coincidence persisting; it belongs at the SAME cheap,
# explicit, "fail fast before any expensive gpg subprocess runs" shape
# stage as every other structural check in this module.
DECISION_KIND_SIGNATURE_ALGORITHM = {
    "verdict": "gpg-detached-armor",
    "signoff": "gpg-detached-armor",
    "local_approval": "local-hmac-sha256-v1",
}

REQUIRED_TOP_KEYS = (
    "receipt_schema", "receipt_id", "issued_at", "proposed_action",
    "policy_decision", "decision_kind", "decision", "chain", "receipt_signature",
)
SIGNOFF_REQUIRED_KEYS = ("rule_id", "category", "authorized_by", "rationale", "authorized_at", "signature")
VERDICT_REQUIRED_KEYS = (
    "verifier", "output_domain", "primary_artifacts_read", "findings",
    "severity_counts", "summary_line", "disposition",
)
# spec_engine.types.Approval's own five fields, verbatim — see
# core/contracts/agent-receipt.schema.json's $defs.LocalApprovalArtifact.
LOCAL_APPROVAL_REQUIRED_KEYS = ("approval_id", "plan_id", "approved", "approved_by", "approved_at", "notes")


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
    if not isinstance(sig, dict) or not {"algorithm", "signed_by", "signed_content_sha256"} <= sig.keys():
        errors.append("receipt_signature is missing a required field")
    else:
        algorithm = sig.get("algorithm")
        if algorithm == "gpg-detached-armor" and "signature_armored" not in sig:
            errors.append("receipt_signature is missing signature_armored (required for algorithm gpg-detached-armor)")
        elif algorithm == "local-hmac-sha256-v1" and "signature_hex" not in sig:
            errors.append("receipt_signature is missing signature_hex (required for algorithm local-hmac-sha256-v1)")
        # tess-os #162 (Cyra LOW-1) — explicit decision_kind <-> algorithm
        # pairing, independent of the field-presence check above (a
        # receipt can satisfy that check — e.g. a local_approval decision
        # wrapped in a gpg-detached-armor envelope that DOES carry
        # signature_armored — while still violating this pairing).
        expected_algorithm = DECISION_KIND_SIGNATURE_ALGORITHM.get(receipt["decision_kind"])
        if expected_algorithm is not None and algorithm != expected_algorithm:
            errors.append(
                f"decision_kind {receipt['decision_kind']!r} requires receipt_signature.algorithm "
                f"{expected_algorithm!r} (agent-receipt.schema.json's top-level allOf trust-level "
                f"pairing — a System A/System B decision can never be wrapped in the other "
                f"system's envelope algorithm), got {algorithm!r}"
            )
    return errors


def check_decision_shape(decision_kind: str, decision: dict) -> list[str]:
    if decision_kind == "local_approval":
        missing = [k for k in LOCAL_APPROVAL_REQUIRED_KEYS if k not in decision]
        if missing:
            return [f"decision (kind=local_approval) missing required field(s): {missing}"]
        errors = []
        if decision.get("approved") is not True:
            errors.append(
                f"decision.approved is {decision.get('approved')!r}, not True — a receipt "
                f"can only represent a GRANTED local approval, never a rejection"
            )
        _auth, auth_error = parse_local_approval_auth(decision.get("notes"))
        if auth_error:
            errors.append(auth_error)
        return errors
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
    if decision_kind == "local_approval":
        return decision.get("approved_by")
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
    """Verify the embedded decision's OWN signature/evidence (the AI
    verifier's verdict, the human operator's sign-off, or — wedge-loop
    epic addition — the locally HMAC-signed approval) against the
    caller-supplied, fingerprint-pinned trust map. `trust` is {identity:
    {"fingerprint": str, "key_bytes": bytes}} — for `verdict`/`signoff`
    identities `key_bytes` is a GPG PUBLIC key (safe to share); for a
    `local_approval` identity it is instead the SAME SECRET local
    approval-identity key that produced the signature (see
    `hmac_verify.py`'s own trust-level disclosure — this is NOT a
    lower-privilege verification-only credential the way a GPG public
    key is)."""
    if decision_kind == "local_approval":
        return _verify_local_approval_decision_signature(decision, trust)
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
        entry["key_bytes"], entry["fingerprint"],
    )
    return [] if ok else [f"decision signature invalid for {identity!r}: {reason}"]


def _verify_local_approval_decision_signature(decision: dict, trust: dict) -> list[str]:
    """The `local_approval` branch of `verify_decision_signature` above,
    split out for readability. No `_content_hash_check` step here — unlike
    a verdict/signoff, an embedded `Approval` carries no separate
    `signature.signed_content_sha256` field of its own; the HMAC
    comparison inside `hmac_verify.verify_local_approval_decision` already
    IS the tamper check (any single-bit change to the signed payload
    changes the required signature)."""
    identity = identity_for("local_approval", decision)
    if not identity:
        return ["decision has no identity field (approved_by)"]
    entry = trust.get(identity)
    if entry is None:
        return [f"no trusted local HMAC key supplied for decision identity {identity!r} (--trust)"]
    auth, auth_error = parse_local_approval_auth(decision.get("notes"))
    if auth_error:
        return [auth_error]
    ok, reason = verify_local_approval_decision(decision, auth, entry["key_bytes"], entry["fingerprint"])
    return [] if ok else [f"decision (local_approval) signature invalid for {identity!r}: {reason}"]


def verify_envelope_signature(receipt: dict, trust: dict) -> list[str]:
    """Verify the receipt's own envelope-level `receipt_signature` —
    GPG for `algorithm: "gpg-detached-armor"`, local HMAC for
    `algorithm: "local-hmac-sha256-v1"` (wedge-loop epic addition). Both
    branches share the SAME `signed_content_sha256` tamper check first
    (`_content_hash_check`, `receipt_signing_bytes` — the envelope's own
    canonicalization is algorithm-agnostic; only the signature scheme
    differs)."""
    errors = _content_hash_check(receipt, "receipt_signature", receipt_signing_bytes)
    if errors:
        return errors
    sig = receipt["receipt_signature"]
    signed_by = sig["signed_by"]
    entry = trust.get(signed_by)
    if sig.get("algorithm") == "local-hmac-sha256-v1":
        if entry is None:
            return [f"no trusted local HMAC key supplied for receipt_signature.signed_by {signed_by!r} (--trust)"]
        ok, reason = verify_hmac_signature(
            receipt_signing_bytes(receipt), sig.get("signature_hex"), entry["key_bytes"], entry["fingerprint"],
        )
        return [] if ok else [f"receipt_signature invalid for {signed_by!r}: {reason}"]
    if entry is None:
        return [f"no trusted public key supplied for receipt_signature.signed_by {signed_by!r} (--trust)"]
    ok, reason = verify_detached_signature(
        receipt_signing_bytes(receipt), sig["signature_armored"],
        entry["key_bytes"], entry["fingerprint"],
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
    verdict (or a local_approval) alone; a path_rule is covered by a
    verdict, never a sign-off or a local_approval. `pipeline_approval_gate`
    (wedge-loop epic addition) can ONLY pair with `local_approval` — a
    `run_pipeline()` Hop-3 approval-gate decision must never be misread as
    having satisfied a real core/policy/policy.yaml PathRule/HardFloorRule
    it never touched, and a GPG-backed verdict/signoff must never be
    (mis)used to clear a rule_kind it was never checked against either.
    These three `if` branches are exhaustive over the 3x3 rule_kind x
    decision_kind matrix (each `rule_kind` value fires exactly one branch,
    which pins its own single required `decision_kind`), so every one of
    the 6 invalid pairings is rejected, not just the 3 checked directly."""
    policy = receipt.get("policy_decision") or {}
    rule_kind = policy.get("rule_kind")
    decision_kind = receipt.get("decision_kind")
    if rule_kind == "hard_floor_rule" and decision_kind != "signoff":
        return ["policy_decision.rule_kind is hard_floor_rule but decision_kind is not 'signoff' (guardrails.md Rule 18: never verdict-satisfiable, never local_approval-satisfiable)"]
    if rule_kind == "path_rule" and decision_kind != "verdict":
        return ["policy_decision.rule_kind is path_rule but decision_kind is not 'verdict'"]
    if rule_kind == "pipeline_approval_gate" and decision_kind != "local_approval":
        return [
            "policy_decision.rule_kind is pipeline_approval_gate but decision_kind is not "
            "'local_approval' — a pipeline approval-gate decision is System A (local HMAC); "
            "it must never be paired with a System B (GPG verdict/signoff) decision_kind"
        ]
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
