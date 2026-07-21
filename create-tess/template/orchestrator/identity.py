"""Backward-compatible re-export shim.

The local approval-identity signing/verification primitives that used to
live here now live in `spec_engine.gate_identity` — the codegen boundary
(`spec_engine.spec_builder.build_spec()`) needs to independently
re-verify a signed approval (see `spec_engine.gate_approval`'s module
docstring for the [Cyra MEDIUM-1]/[MEDIUM-2] hardening this made
necessary), and `orchestrator` already has a one-way import dependency on
`spec_engine` (never the reverse) — so the primitives moved to the lower
layer rather than being duplicated in two places that would need to stay
byte-for-byte identical to keep signatures cross-verifiable.

This module re-exports the exact same public names so existing
`from orchestrator.identity import ...` imports keep working unchanged.
New code should import from `spec_engine.gate_identity` directly.
"""

from __future__ import annotations

from spec_engine.gate_identity import (
    AUTH_MECHANISM,
    KEY_BYTES,
    IdentityError,
    LocalIdentity,
    canonical_payload,
    default_identity_dir,
    load_or_create_local_identity,
    read_current_key,
    sign_payload,
    verify_signature,
)

__all__ = [
    "AUTH_MECHANISM",
    "default_identity_dir",
    "KEY_BYTES",
    "IdentityError",
    "LocalIdentity",
    "load_or_create_local_identity",
    "read_current_key",
    "canonical_payload",
    "sign_payload",
    "verify_signature",
]
