"""orchestrator.identity is a backward-compatible re-export shim over
spec_engine.gate_identity. The signing primitives themselves are tested in
tests/spec_engine/test_gate_identity.py; this file only proves the shim
hands out the very same objects, so `from orchestrator.identity import ...`
can never drift to a second implementation."""

from __future__ import annotations

import _orchestrator_paths  # noqa: F401 -- sys.path bootstrap

import orchestrator.identity as shim
import spec_engine.gate_identity as primitives

NAMES = (
    "AUTH_MECHANISM", "KEY_BYTES", "IdentityError", "LocalIdentity",
    "canonical_payload", "default_identity_dir", "load_or_create_local_identity",
    "read_current_key", "sign_payload", "verify_signature",
)


def test_shim_re_exports_the_gate_identity_objects_themselves():
    assert sorted(shim.__all__) == sorted(NAMES)
    for name in NAMES:
        assert getattr(shim, name) is getattr(primitives, name), name
