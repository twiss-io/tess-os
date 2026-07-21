# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Twiss
"""Minimal, dependency-free local HMAC-SHA256 signature verification.

The `local-hmac-sha256-v1` counterpart to `gpg_verify.py`'s GPG verification
— the standalone re-implementation this tool's own "Why standalone" doctrine
requires (no `tessctl` import, no `spec_engine` import, no third-party
package; see tools/receipt-verify/README.md). Verifies:

  * the embedded `decision` of a `decision_kind: "local_approval"` Agent
    Receipt (a `spec_engine.types.Approval`, its HMAC evidence carried in
    `decision.notes` as a JSON string — see `local_approval_signing_bytes()`
    and `verify_local_approval_decision()` below), and
  * the receipt's own envelope-level `receipt_signature` when
    `algorithm: "local-hmac-sha256-v1"` (a generic HMAC-over-bytes check —
    see `verify_hmac_signature()`, the direct counterpart to
    `gpg_verify.verify_detached_signature()`).

★ TRUST LEVEL — READ BEFORE USING THIS AS IF IT WERE `gpg_verify.py`.
`gpg_verify.py` verifies an ASYMMETRIC signature: the caller supplies a
PUBLIC key, safe to hand to anyone, and a signature made by the matching
PRIVATE key verifies against it without that private key ever leaving its
owner. This module verifies a SYMMETRIC (HMAC) signature: the caller must
supply the SAME SECRET key material that produced the signature in the
first place (`spec_engine.gate_identity`'s local approval-identity key,
normally `~/.tess-os/approval-identity/<username>.key`) — there is no
"public half." Anyone who can supply that key to `--trust` can also FORGE
a new, equally-valid `local_approval` signature under that identity;
verifying is not a lower-privilege operation than signing the way it is
for GPG. Treat a `local_approval` trust entry's key file with the SAME
care as any other secret credential — never publish it, never commit it,
and never treat "I can verify this receipt" as evidence of anything beyond
"I hold (or was given, out of band, by someone who holds) this one local
key." See `docs/AGENT_RECEIPT_SPEC.md` and `core/contracts/
agent-receipt.schema.json`'s `$defs.LocalApprovalArtifact` for the full,
load-bearing trust-level disclosure this module implements.

★ DISCLOSED SCOPE — a PASS from either function below proves authenticity
+ integrity (this exact content was HMAC-signed by a holder of this exact
key) — the same scope `gpg_verify.verify_detached_signature()` has for
GPG. It does NOT prove the embedded approval was never replayed across two
separate process runs; `spec_engine.gate_approval`'s own nonce-consumption
tracker is disclosed, in that module's own docstring, as in-process/
in-memory only. This module is not, and does not claim to be, a
replay/freshness check.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re

# Mirrors spec_engine.gate_identity.KEY_BYTES / AUTH_MECHANISM exactly —
# duplicated (not imported) so this standalone verifier has zero
# dependency on spec_engine, the same independence gpg_verify.py already
# has from .tess/bin/tessctl. A drift between these literals and the real
# spec_engine constants would only ever make this tool MORE conservative
# (reject a genuine signature), never silently accept a forged one, since
# every check below still requires the actual HMAC math to match.
KEY_BYTES = 32
AUTH_MECHANISM = "local-hmac-sha256-v1"

# Local approval-identity fingerprints are sha256(key)[:16] hex — 16 lowercase
# hex characters. Deliberately a DIFFERENT length/case convention than GPG's
# 40-uppercase-hex fingerprints (gpg_verify.FULL_FINGERPRINT_RE) specifically
# so the two can never be silently confused or copy-pasted into the wrong
# --trust entry without immediately failing this pattern check.
LOCAL_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{16}$")


def key_fingerprint(key_bytes: bytes) -> str:
    """`sha256(key)[:16]` hex — the exact convention
    `spec_engine.gate_identity.LocalIdentity.fingerprint` already uses."""
    return hashlib.sha256(key_bytes).hexdigest()[:16]


def verify_hmac_signature(
    payload: bytes, signature_hex: str, key_bytes: bytes, expected_fingerprint: str,
) -> tuple[bool, str]:
    """Verify `signature_hex` (an HMAC-SHA256 hex digest) over `payload`,
    trusting ONLY `key_bytes`, and require `key_bytes`'s OWN fingerprint to
    equal `expected_fingerprint` EXACTLY (lowercase, 16 hex chars) — the
    direct counterpart to `gpg_verify.verify_detached_signature()`'s
    exact-fingerprint-pinning discipline, reimplemented for a symmetric
    scheme: here the "imported key's own fingerprint" check is what stops
    a caller from supplying an unrelated 32-byte blob under a fingerprint
    it does not actually own.

    Returns (ok, reason). reason is '' when ok is True; otherwise a
    human-readable explanation of exactly which check failed. Never
    raises on malformed input — every failure mode is a normal, expected
    verification result, not a programming error."""
    fingerprint = (expected_fingerprint or "").strip().lower()
    if not LOCAL_FINGERPRINT_RE.match(fingerprint):
        return False, (
            f"expected_fingerprint {expected_fingerprint!r} is not a valid "
            "16-hex-character local approval-identity fingerprint "
            "(sha256(key)[:16]) — do not confuse this with a 40-hex GPG fingerprint"
        )
    if not isinstance(key_bytes, (bytes, bytearray)) or len(key_bytes) != KEY_BYTES:
        return False, (
            f"supplied key material is not a {KEY_BYTES}-byte local "
            "approval-identity key (wrong file, or a GPG key mistakenly "
            "supplied where a local HMAC secret key was expected)"
        )
    actual_fingerprint = key_fingerprint(bytes(key_bytes))
    if actual_fingerprint != fingerprint:
        return False, (
            f"supplied key's own fingerprint {actual_fingerprint} does NOT match "
            f"the expected fingerprint {fingerprint} — wrong key, fail-closed "
            "(exact match required, no short/partial matching)"
        )
    if not isinstance(signature_hex, str) or not signature_hex:
        return False, "no signature_hex supplied to verify against"
    expected_sig = hmac.new(bytes(key_bytes), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, signature_hex):
        return False, "HMAC-SHA256 signature does not verify (bad signature, tampered content, or wrong key)"
    return True, ""


def parse_local_approval_auth(notes) -> tuple[dict | None, str | None]:
    """Parse a `LocalApprovalArtifact.notes` string into its embedded
    `auth` block — `spec_engine.gate_approval.sign_local_approval()`'s
    exact JSON shape: `{"human_notes": <str>, "auth": {"mechanism": ...,
    "identity_fingerprint": ..., "content_hash": ..., "nonce": ...,
    "signature": ...}}`. Returns `(auth_dict, None)` on success, or
    `(None, reason)` on any structural failure — never raises."""
    if not isinstance(notes, str) or not notes.strip():
        return None, "decision.notes is missing or not a non-empty string"
    try:
        parsed = json.loads(notes)
        auth = parsed["auth"]
        if not isinstance(auth, dict):
            raise ValueError("auth block is not a JSON object")
        for key in ("mechanism", "identity_fingerprint", "content_hash", "nonce", "signature"):
            if key not in auth:
                raise KeyError(key)
    except Exception as exc:  # noqa: BLE001 — every parse failure collapses to one reported reason
        return None, (
            f"decision.notes carries no valid embedded local-HMAC auth evidence "
            f"({type(exc).__name__}: {exc})"
        )
    return auth, None


def local_approval_signing_bytes(decision: dict, auth: dict) -> bytes:
    """Rebuild `spec_engine.gate_identity.canonical_payload()`'s EXACT
    dict shape from a `LocalApprovalArtifact` `decision` + its already-
    parsed `auth` block (see `parse_local_approval_auth()` above), then
    serialize with the EXACT SAME byte convention
    `spec_engine.gate_identity.sign_payload()` uses: compact, key-sorted
    JSON, `ensure_ascii` left at Python's default (True). Deliberately
    NOT this tool's own `canonical.py` convention (which sets
    `ensure_ascii=False` for the UNRELATED envelope-level
    canonicalization every Agent Receipt already uses for
    `receipt_signature` — see `checks.verify_envelope_signature`).
    Duplicated here (not imported) so this standalone verifier has zero
    dependency on spec_engine — the same "independent re-implementation"
    discipline `gpg_verify.py` already documents for itself."""
    payload = {
        "approval_id": decision.get("approval_id"),
        "plan_id": decision.get("plan_id"),
        "content_hash": auth.get("content_hash"),
        "approved": decision.get("approved"),
        "approved_by": decision.get("approved_by"),
        "approved_at": decision.get("approved_at"),
        "nonce": auth.get("nonce"),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_local_approval_decision(
    decision: dict, auth: dict, key_bytes: bytes, expected_fingerprint: str,
) -> tuple[bool, str]:
    """Verify an embedded `LocalApprovalArtifact` `decision`'s OWN HMAC
    evidence (`auth`, already parsed out of `decision["notes"]` by
    `parse_local_approval_auth()` — see `checks.py`). Independently
    re-derives `spec_engine.gate_identity`'s canonical signing payload and
    re-verifies with `verify_hmac_signature()` above — the SAME math
    `spec_engine.gate_approval.verify_gate_approval()` runs at the real
    codegen boundary, reimplemented standalone here.

    Checks, in order (cheap/structural before the HMAC comparison,
    mirroring this tool's own "fail fast" discipline): the declared
    `auth.mechanism` is the one recognized value; the declared
    `auth.identity_fingerprint` matches the caller-pinned
    `expected_fingerprint` EXACTLY; then the HMAC-SHA256 signature itself
    verifies against `key_bytes`. See this module's docstring for the
    disclosed non-replay-proof scope."""
    if auth.get("mechanism") != AUTH_MECHANISM:
        return False, (
            f"decision.notes auth.mechanism {auth.get('mechanism')!r} is not the "
            f"recognized {AUTH_MECHANISM!r}"
        )
    declared_fingerprint = str(auth.get("identity_fingerprint") or "").strip().lower()
    pinned_fingerprint = (expected_fingerprint or "").strip().lower()
    if declared_fingerprint != pinned_fingerprint:
        return False, (
            f"decision.notes auth.identity_fingerprint {declared_fingerprint!r} does "
            f"not match the caller-pinned expected fingerprint {pinned_fingerprint!r} "
            "— fail-closed"
        )
    payload = local_approval_signing_bytes(decision, auth)
    return verify_hmac_signature(payload, auth.get("signature"), key_bytes, expected_fingerprint)


__all__ = [
    "KEY_BYTES",
    "AUTH_MECHANISM",
    "LOCAL_FINGERPRINT_RE",
    "key_fingerprint",
    "verify_hmac_signature",
    "parse_local_approval_auth",
    "local_approval_signing_bytes",
    "verify_local_approval_decision",
]
