"""Golden bytes for the signing canonicalisation.

Verdict and sign-off signatures, and the audit pack's receipt tamper check,
are computed over these exact bytes: compact, key-sorted JSON with
ensure_ascii=False, minus one key. Any change to the bytes invalidates every
signature already issued, so the digests below are pinned (recorded on
84be01c, before the three functions were unified)."""

from __future__ import annotations

import hashlib

OBJ = {
    "z": [3, {"b": "é", "a": None}],
    "signature": {"x": 1},
    "receipt_signature": "rs",
    "a": "ünïcode ✓",
    "n": 1.5,
    "t": True,
    "m": {"k2": 2, "k1": [1, "2"]},
}
WITHOUT_SIGNATURE = "dcf4247fde1a7af07bf49eb5f88c518533fdfc1cc2dcd7e41f76845f6f4bc95f"
WITHOUT_RECEIPT_SIGNATURE = "34a54773c5c60d48993ef316fee0fdba787029bfe663a6d8c635fa5bf88517ec"


def _digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_verdict_and_signoff_canonical_bytes_are_pinned(engine):
    assert _digest(engine.verdict_canonical_bytes(OBJ)) == WITHOUT_SIGNATURE
    assert _digest(engine.signoff_canonical_bytes(OBJ)) == WITHOUT_SIGNATURE


def test_audit_canonical_bytes_are_pinned_for_either_excluded_key(engine):
    assert _digest(engine._audit_canonical_bytes(OBJ, "signature")) == WITHOUT_SIGNATURE
    assert _digest(engine._audit_canonical_bytes(OBJ, "receipt_signature")) == WITHOUT_RECEIPT_SIGNATURE


def test_canonical_bytes_keep_non_ascii_and_never_mutate_the_input(engine):
    before = repr(OBJ)
    raw = engine.verdict_canonical_bytes(OBJ)
    assert "ünïcode ✓".encode("utf-8") in raw and b"\\u" not in raw
    assert b'"signature"' not in raw and b" " not in raw.replace("ünïcode ✓".encode("utf-8"), b"")
    assert repr(OBJ) == before
