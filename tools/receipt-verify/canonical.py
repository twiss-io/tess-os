"""Canonicalization + hashing helpers for Agent Receipt verification.

Deliberately the SAME scheme `.tess/bin/tessctl` already uses and tests for
verdict/sign-off signing (`verdict_canonical_bytes` / `signoff_canonical_bytes`):
compact, key-sorted JSON with a named key excluded, sha256'd for tamper
detection. No new canonicalization invented here — see
docs/AGENT_RECEIPT_SPEC.md "Canonicalization" for the doctrine citation.

This module has ZERO dependency on the rest of this repository (no `tessctl`
import, no network, no third-party package) — see tools/receipt-verify/README.md
"Why standalone" for why that independence is the point of this tool.
"""

from __future__ import annotations

import hashlib
import json


def canonical_bytes(obj: dict, exclude_key: str | None = None) -> bytes:
    """Compact, key-sorted JSON bytes of `obj`, optionally omitting one
    top-level key (the signature field being computed/verified against its
    own content can never sign over itself)."""
    payload = obj if exclude_key is None else {k: v for k, v in obj.items() if k != exclude_key}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decision_signing_bytes(decision: dict) -> bytes:
    """Canonical bytes an embedded verdict/sign-off's OWN `signature` was
    produced over — the decision object minus its `signature` key. Matches
    `verdict_canonical_bytes` / `signoff_canonical_bytes` in .tess/bin/tessctl
    exactly (both already use this identical compact/key-sorted/minus-
    signature scheme, so one helper covers both decision kinds here)."""
    return canonical_bytes(decision, exclude_key="signature")


def receipt_signing_bytes(receipt: dict) -> bytes:
    """Canonical bytes the receipt's OWN envelope-level `receipt_signature`
    is produced over — the full receipt minus `receipt_signature` itself."""
    return canonical_bytes(receipt, exclude_key="receipt_signature")


def receipt_content_hash(receipt: dict) -> str:
    """sha256 hex digest of the FULL, already-signed receipt (every key,
    including `receipt_signature`) — the value a LATER receipt in the same
    chain must record as its own `chain.prev_receipt_hash`. Deliberately a
    SEPARATE hash from `receipt_signing_bytes`'s target: that one excludes
    the signature (so it isn't self-referential at signing time); this one
    is computed AFTER signing, over the finished, persisted record, so a
    later receipt's chain link binds the exact bytes that were published —
    including their signature — not just the pre-signature content."""
    return sha256_hex(canonical_bytes(receipt))
