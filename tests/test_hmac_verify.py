"""
tools/receipt-verify/hmac_verify.py — direct, low-level unit coverage.

The `local_approval` counterpart to how `gpg_verify.py`'s primitives are
exercised (indirectly, through `checks.py`/the CLI) — this file adds
DIRECT, dependency-free coverage of `hmac_verify.py`'s own functions in
isolation, since the wedge-loop epic that introduced this module is
required to prove "hmac_verify pass/fail" explicitly. Higher-level,
full-receipt coverage (a genuine round trip through `checks.verify_receipt`
and the CLI) lives in `tests/test_receipt_verify_semantics.py` and
`tests/test_receipt_verify_cli.py`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL_DIR = REPO_ROOT / "tools" / "receipt-verify"
sys.path.insert(0, str(TOOL_DIR))

import hmac_verify  # noqa: E402


def _key():
    key_bytes = secrets.token_bytes(32)
    fingerprint = hashlib.sha256(key_bytes).hexdigest()[:16]
    return key_bytes, fingerprint


# ---------------------------------------------------------------------------
# key_fingerprint / verify_hmac_signature — the generic counterpart to
# gpg_verify.verify_detached_signature.
# ---------------------------------------------------------------------------


def test_key_fingerprint_matches_spec_engine_convention():
    key_bytes = b"\x00" * 32
    assert hmac_verify.key_fingerprint(key_bytes) == hashlib.sha256(key_bytes).hexdigest()[:16]


def test_verify_hmac_signature_valid_signature_passes():
    key_bytes, fingerprint = _key()
    payload = b'{"a":1}'
    sig = hmac.new(key_bytes, payload, hashlib.sha256).hexdigest()
    ok, reason = hmac_verify.verify_hmac_signature(payload, sig, key_bytes, fingerprint)
    assert ok is True
    assert reason == ""


def test_verify_hmac_signature_wrong_key_fails():
    key_bytes, fingerprint = _key()
    other_key_bytes, _ = _key()
    payload = b'{"a":1}'
    sig = hmac.new(key_bytes, payload, hashlib.sha256).hexdigest()
    # Claim the signature was made under `fingerprint`, but hand over a
    # DIFFERENT key's bytes -- the key's own recomputed fingerprint won't
    # match what's pinned.
    ok, reason = hmac_verify.verify_hmac_signature(payload, sig, other_key_bytes, fingerprint)
    assert ok is False
    assert "does NOT match" in reason


def test_verify_hmac_signature_tampered_payload_fails():
    key_bytes, fingerprint = _key()
    payload = b'{"a":1}'
    sig = hmac.new(key_bytes, payload, hashlib.sha256).hexdigest()
    ok, reason = hmac_verify.verify_hmac_signature(b'{"a":2}', sig, key_bytes, fingerprint)
    assert ok is False
    assert "does not verify" in reason


def test_verify_hmac_signature_malformed_fingerprint_fails():
    key_bytes, _ = _key()
    ok, reason = hmac_verify.verify_hmac_signature(b"x", "deadbeef" * 8, key_bytes, "NOT-A-FINGERPRINT")
    assert ok is False
    assert "not a valid" in reason


def test_verify_hmac_signature_gpg_style_fingerprint_rejected():
    """A 40-hex GPG fingerprint must never be silently accepted where a
    16-hex local fingerprint is expected -- the two conventions are
    deliberately incompatible lengths so a copy-paste mistake fails loud."""
    key_bytes, _ = _key()
    gpg_style_fingerprint = "A" * 40
    ok, reason = hmac_verify.verify_hmac_signature(b"x", "0" * 64, key_bytes, gpg_style_fingerprint)
    assert ok is False
    assert "not a valid" in reason


def test_verify_hmac_signature_wrong_key_length_fails():
    fingerprint = hashlib.sha256(b"short").hexdigest()[:16]
    ok, reason = hmac_verify.verify_hmac_signature(b"x", "0" * 64, b"short", fingerprint)
    assert ok is False
    assert "32-byte" in reason


def test_verify_hmac_signature_missing_signature_fails():
    key_bytes, fingerprint = _key()
    ok, reason = hmac_verify.verify_hmac_signature(b"x", None, key_bytes, fingerprint)
    assert ok is False
    assert "no signature_hex" in reason


# ---------------------------------------------------------------------------
# parse_local_approval_auth
# ---------------------------------------------------------------------------


def test_parse_local_approval_auth_valid_notes():
    notes = json.dumps({
        "human_notes": "",
        "auth": {
            "mechanism": "local-hmac-sha256-v1", "identity_fingerprint": "0" * 16,
            "content_hash": "1" * 64, "nonce": "n", "signature": "2" * 64,
        },
    })
    auth, error = hmac_verify.parse_local_approval_auth(notes)
    assert error is None
    assert auth["mechanism"] == "local-hmac-sha256-v1"


def test_parse_local_approval_auth_not_json_fails():
    auth, error = hmac_verify.parse_local_approval_auth("not json at all")
    assert auth is None
    assert "no valid embedded local-HMAC auth evidence" in error


def test_parse_local_approval_auth_missing_auth_key_fails():
    auth, error = hmac_verify.parse_local_approval_auth(json.dumps({"human_notes": "x"}))
    assert auth is None
    assert "no valid embedded local-HMAC auth evidence" in error


def test_parse_local_approval_auth_missing_nested_field_fails():
    notes = json.dumps({"auth": {"mechanism": "local-hmac-sha256-v1"}})  # missing nonce/signature/etc
    auth, error = hmac_verify.parse_local_approval_auth(notes)
    assert auth is None
    assert error is not None


def test_parse_local_approval_auth_empty_string_fails():
    auth, error = hmac_verify.parse_local_approval_auth("")
    assert auth is None
    assert "missing or not a non-empty string" in error


# ---------------------------------------------------------------------------
# local_approval_signing_bytes / verify_local_approval_decision
# ---------------------------------------------------------------------------


def _signed_decision(key_bytes, fingerprint, *, approved=True):
    approval_id, plan_id, approved_by, approved_at = "appr-1", "plan-1", "local:x#" + fingerprint, "2026-07-19T00:00:00.000000Z"
    content_hash, nonce = "3" * 64, "nonce-1"
    payload = {
        "approval_id": approval_id, "plan_id": plan_id, "content_hash": content_hash,
        "approved": approved, "approved_by": approved_by, "approved_at": approved_at, "nonce": nonce,
    }
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(key_bytes, canon, hashlib.sha256).hexdigest()
    decision = {
        "approval_id": approval_id, "plan_id": plan_id, "approved": approved,
        "approved_by": approved_by, "approved_at": approved_at,
        "notes": json.dumps({
            "human_notes": "", "auth": {
                "mechanism": "local-hmac-sha256-v1", "identity_fingerprint": fingerprint,
                "content_hash": content_hash, "nonce": nonce, "signature": signature,
            },
        }),
    }
    auth, error = hmac_verify.parse_local_approval_auth(decision["notes"])
    assert error is None
    return decision, auth


def test_local_approval_signing_bytes_is_deterministic_and_key_sorted():
    key_bytes, fingerprint = _key()
    decision, auth = _signed_decision(key_bytes, fingerprint)
    b1 = hmac_verify.local_approval_signing_bytes(decision, auth)
    b2 = hmac_verify.local_approval_signing_bytes(decision, auth)
    assert b1 == b2
    parsed = json.loads(b1)
    assert list(parsed.keys()) == sorted(parsed.keys())


def test_verify_local_approval_decision_valid_passes():
    key_bytes, fingerprint = _key()
    decision, auth = _signed_decision(key_bytes, fingerprint)
    ok, reason = hmac_verify.verify_local_approval_decision(decision, auth, key_bytes, fingerprint)
    assert ok is True
    assert reason == ""


def test_verify_local_approval_decision_wrong_mechanism_fails():
    key_bytes, fingerprint = _key()
    decision, auth = _signed_decision(key_bytes, fingerprint)
    auth["mechanism"] = "some-future-mechanism-v2"
    ok, reason = hmac_verify.verify_local_approval_decision(decision, auth, key_bytes, fingerprint)
    assert ok is False
    assert "not the recognized" in reason


def test_verify_local_approval_decision_fingerprint_mismatch_fails():
    key_bytes, fingerprint = _key()
    decision, auth = _signed_decision(key_bytes, fingerprint)
    other_key_bytes, other_fingerprint = _key()
    ok, reason = hmac_verify.verify_local_approval_decision(decision, auth, other_key_bytes, other_fingerprint)
    assert ok is False
    assert "does not match the caller-pinned" in reason


def test_verify_local_approval_decision_tampered_field_fails():
    key_bytes, fingerprint = _key()
    decision, auth = _signed_decision(key_bytes, fingerprint)
    decision["approved_by"] = "someone-else"
    ok, reason = hmac_verify.verify_local_approval_decision(decision, auth, key_bytes, fingerprint)
    assert ok is False


def test_verify_local_approval_decision_rejected_approval_still_verifies_signature():
    """The HMAC math itself doesn't care whether `approved` is True or
    False -- it verifies whatever was actually signed. The schema-level
    'a receipt can only represent a GRANTED approval' rule is enforced
    elsewhere (checks.check_decision_shape / the JSON Schema's own
    `const: true`), not here -- this function's only job is signature
    authenticity."""
    key_bytes, fingerprint = _key()
    decision, auth = _signed_decision(key_bytes, fingerprint, approved=False)
    ok, reason = hmac_verify.verify_local_approval_decision(decision, auth, key_bytes, fingerprint)
    assert ok is True
