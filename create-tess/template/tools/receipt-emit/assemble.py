# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Twiss
"""Decision-kind inference + receipt envelope assembly for tools/receipt-emit.

Reuses tools/receipt-verify/checks.py's OWN required-field sets and shape/
identity/pairing checks rather than re-deriving a second, possibly-drifting
definition of what a valid verdict, signoff, or policy/decision pairing
looks like — the same "do NOT re-implement" discipline the task brief
applies to canonical.py, extended here to the shape checks receipt-verify
already owns and already tests. `receipt_emit.py`'s bootstrap puts
tools/receipt-verify/ on `sys.path` before importing this module, exactly
the way it puts this directory on `sys.path` — see that file's own header.

Every function in this module either returns a value or raises
`EmitRefused` — nothing here ever writes to disk. `chain_atomic.py`'s
atomic append is the ONLY place this tool writes anything, so every
refusal from this module leaves disk exactly as it found it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import canonical  # tools/receipt-verify/canonical.py — reused, not reimplemented
import checks  # tools/receipt-verify/checks.py — reused shape/identity/pairing checks

from errors import EmitRefused


def utc_now_iso() -> str:
    """Same UTC ISO-8601-with-microseconds format tessctl's own
    `_trace_utc_now_iso()` / verdict `signed_at` already use."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def infer_decision_kind(decision: dict) -> str | None:
    """'verdict' | 'signoff' | None (neither, or ambiguous — matches
    both/neither key set). Derived from checks.py's OWN
    VERDICT_REQUIRED_KEYS / SIGNOFF_REQUIRED_KEYS constants, never a
    separately hand-maintained key list that could drift from what the
    verifier actually requires."""
    if not isinstance(decision, dict):
        return None
    is_verdict = all(k in decision for k in checks.VERDICT_REQUIRED_KEYS)
    is_signoff = all(k in decision for k in checks.SIGNOFF_REQUIRED_KEYS)
    if is_verdict and not is_signoff:
        return "verdict"
    if is_signoff and not is_verdict:
        return "signoff"
    return None


def validate_decision_or_refuse(decision_kind: str, decision: dict) -> str:
    """Runs checks.py's OWN `check_decision_shape` — the SAME structural +
    disposition:APPROVE check the verifier will run later — BEFORE any file
    is touched. This is where FAIL-CLOSED item 1 (non-APPROVE verdict /
    incomplete-or-unsigned "rejected" signoff) is enforced: a verdict whose
    `disposition` is not `APPROVE`, or a signoff missing any required field
    or its own `signature` block (i.e., not a completed, genuine
    authorization), fails this check and is refused here.

    Returns the decision's own identity (`verifier` for a verdict,
    `authorized_by` for a signoff), guaranteed non-empty."""
    errors = checks.check_decision_shape(decision_kind, decision)
    if errors:
        raise EmitRefused(errors)
    identity = checks.identity_for(decision_kind, decision)
    if not identity:
        raise EmitRefused([f"decision (kind={decision_kind}) has no identity field"])
    return identity


def validate_policy_pairing_or_refuse(policy_decision: dict, decision_kind: str) -> None:
    """guardrails.md Rule 18 pairing (checks.py's OWN
    `check_policy_pairing`, reused unmodified): a hard_floor_rule must be
    backed by a signoff, never a verdict; a path_rule must be backed by a
    verdict. Runs on the minimal {policy_decision, decision_kind} shape
    `check_policy_pairing` actually reads — the full receipt envelope does
    not need to exist yet for this check to run."""
    errors = checks.check_policy_pairing({
        "policy_decision": policy_decision, "decision_kind": decision_kind,
    })
    if errors:
        raise EmitRefused(errors)


def build_envelope(*, actor: str, summary: str, policy_decision: dict,
                    decision_kind: str, decision: dict,
                    sequence: int, prev_hash: str) -> dict:
    """Assembles the receipt envelope per
    core/contracts/agent-receipt.schema.json — every required top-level key
    except `receipt_signature` (added later by `sign_envelope`, once the
    rest of the envelope's bytes are final and there is something to sign).
    `decision` is embedded VERBATIM — never summarized, never re-derived —
    exactly as the schema requires."""
    return {
        "receipt_schema": "tess-os.agent-receipt/1",
        "receipt_id": uuid.uuid4().hex,
        "issued_at": utc_now_iso(),
        "proposed_action": {"actor": actor, "summary": summary},
        "policy_decision": policy_decision,
        "decision_kind": decision_kind,
        "decision": decision,
        "chain": {"sequence": sequence, "prev_receipt_hash": prev_hash},
    }


def sign_envelope(receipt: dict, *, signed_by: str, key_id: str,
                   gnupg_home: str | None, sign_fn) -> dict:
    """Attaches `receipt_signature`, using `sign_fn(canonical_bytes, key_id,
    gnupg_home) -> armored_signature` for the actual GPG call — injected so
    this stays unit-testable without a real GPG subprocess (semantics-level
    tests can pass a deterministic fake; CLI-level tests exercise the real
    `gpg_sign.detached_sign`).

    `signed_by` is ALWAYS the decision's own identity (never independently
    supplied by a caller) — by construction, this can never diverge from
    `decision`'s identity when called through `receipt_emit.py`'s normal
    flow. `identity_consistency_or_refuse` below is the defense-in-depth
    re-check that would catch it anyway if a future change ever broke that
    invariant (see FAIL-CLOSED item 2 — "signer identity != decision
    identity")."""
    canon = canonical.receipt_signing_bytes(receipt)
    content_hash = canonical.sha256_hex(canon)
    signature_armored = sign_fn(canon, key_id, gnupg_home)

    signed_receipt = dict(receipt)
    signed_receipt["receipt_signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_by": signed_by,
        "signed_content_sha256": content_hash,
        "signature_armored": signature_armored,
        "signed_at": utc_now_iso(),
    }
    identity_consistency_or_refuse(signed_receipt)
    return signed_receipt


def identity_consistency_or_refuse(receipt: dict) -> None:
    """FAIL-CLOSED item 2 — checks.py's OWN `check_identity_consistency`,
    run again here on the fully-assembled, signed receipt (schema
    identity-consistency: `receipt_signature.signed_by` must equal
    `decision`'s own identity field). Under `receipt_emit.py`'s normal
    flow this can only fire due to a bug (signed_by is always DERIVED from
    the decision, never independently supplied) — see
    tests/test_receipt_emit_semantics.py for a direct, synthetic proof this
    guard actually rejects a forced mismatch, exercising the exact code
    path a real divergence would hit."""
    errors = checks.check_identity_consistency(receipt)
    if errors:
        raise EmitRefused(errors)
