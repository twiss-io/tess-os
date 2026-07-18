"""Tests for orchestrator.identity — a backward-compatible re-export shim
over spec_engine.gate_identity, the local, non-forgeable signing
primitives `LocalIdentityApprovalGate` (and spec_engine.spec_builder.
build_spec()'s own codegen-boundary re-verification) are built on. These
tests exercise the primitives through `orchestrator.identity`'s import
path specifically, proving the re-export shim genuinely works, not just
that spec_engine.gate_identity itself does."""

from __future__ import annotations

import os
import stat

import pytest

import _orchestrator_paths  # noqa: F401 -- sys.path bootstrap

from orchestrator.identity import (
    IdentityError,
    canonical_payload,
    load_or_create_local_identity,
    read_current_key,
    sign_payload,
    verify_signature,
)


def _payload(**overrides):
    base = dict(
        approval_id="appr-000000000000",
        plan_id="plan-000000000000",
        content_hash="a" * 64,
        approved=True,
        approved_by="local:tester#abcdef0123456789",
        approved_at="2026-01-01T00:00:00.000Z",
        nonce="nonce-000000000000",
    )
    base.update(overrides)
    return canonical_payload(**base)


def test_load_or_create_local_identity_creates_a_key_on_first_use(tmp_path):
    identity_dir = tmp_path / "identity"
    identity = load_or_create_local_identity(identity_dir)
    assert identity.key_path.is_file()
    assert identity.key_path.parent == identity_dir
    assert len(identity.fingerprint) == 16  # sha256(key)[:16] hex


def test_load_or_create_local_identity_is_idempotent(tmp_path):
    identity_dir = tmp_path / "identity"
    first = load_or_create_local_identity(identity_dir)
    second = load_or_create_local_identity(identity_dir)
    assert first.key_path == second.key_path
    assert first.fingerprint == second.fingerprint  # same underlying key


def test_key_file_is_created_with_owner_only_permissions(tmp_path):
    identity_dir = tmp_path / "identity"
    identity = load_or_create_local_identity(identity_dir)
    mode = stat.S_IMODE(os.stat(identity.key_path).st_mode)
    assert mode == 0o600


def test_read_current_key_refuses_a_group_readable_key(tmp_path):
    identity_dir = tmp_path / "identity"
    identity = load_or_create_local_identity(identity_dir)
    os.chmod(identity.key_path, 0o640)  # loosen permissions after creation
    with pytest.raises(IdentityError):
        read_current_key(identity.key_path)


def test_read_current_key_refuses_a_corrupt_key(tmp_path):
    identity_dir = tmp_path / "identity"
    identity = load_or_create_local_identity(identity_dir)
    identity.key_path.write_bytes(b"too-short")
    os.chmod(identity.key_path, 0o600)
    with pytest.raises(IdentityError):
        read_current_key(identity.key_path)


def test_read_current_key_raises_when_key_missing(tmp_path):
    with pytest.raises(IdentityError):
        read_current_key(tmp_path / "does-not-exist.key")


def test_sign_then_verify_round_trips(tmp_path):
    identity = load_or_create_local_identity(tmp_path / "identity")
    key = read_current_key(identity.key_path)
    payload = _payload()
    signature = sign_payload(key, payload)
    assert verify_signature(key, payload, signature) is True


def test_verify_fails_if_any_signed_field_changes(tmp_path):
    identity = load_or_create_local_identity(tmp_path / "identity")
    key = read_current_key(identity.key_path)
    payload = _payload()
    signature = sign_payload(key, payload)

    tampered = dict(payload)
    tampered["approved_by"] = "Xavier"
    assert verify_signature(key, tampered, signature) is False

    tampered_approved = dict(payload)
    tampered_approved["approved"] = not payload["approved"]
    assert verify_signature(key, tampered_approved, signature) is False


def test_verify_fails_if_content_hash_changes(tmp_path):
    """[Cyra MEDIUM-2] canonical_payload()'s content_hash field is signed
    like every other field — swapping in a DIFFERENT content_hash after
    signing (simulating a spec-substitution attempt: the same approval_id/
    plan_id/nonce, but for different underlying plan content) must fail
    verification exactly the same way tampering with approved_by/approved
    does."""
    identity = load_or_create_local_identity(tmp_path / "identity")
    key = read_current_key(identity.key_path)
    payload = _payload()
    signature = sign_payload(key, payload)

    tampered = dict(payload)
    tampered["content_hash"] = "b" * 64
    assert verify_signature(key, tampered, signature) is False


def test_verify_fails_with_wrong_key(tmp_path):
    real_identity = load_or_create_local_identity(tmp_path / "real")
    attacker_identity = load_or_create_local_identity(tmp_path / "attacker")
    real_key = read_current_key(real_identity.key_path)
    attacker_key = read_current_key(attacker_identity.key_path)

    payload = _payload()
    signature = sign_payload(real_key, payload)
    assert verify_signature(attacker_key, payload, signature) is False


def test_different_identity_dirs_get_independent_keys(tmp_path):
    a = load_or_create_local_identity(tmp_path / "dir-a")
    b = load_or_create_local_identity(tmp_path / "dir-b")
    assert a.fingerprint != b.fingerprint
    key_a = read_current_key(a.key_path)
    key_b = read_current_key(b.key_path)
    assert key_a != key_b
