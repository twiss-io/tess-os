"""Tests for spec_engine.gate_identity -- the local, non-forgeable signing
primitives spec_engine.gate_approval (the codegen boundary's own
re-verification) and orchestrator.adapters.local_identity.
LocalIdentityApprovalGate are both built on. Mirrors
tests/orchestrator/test_identity.py's own coverage of the SAME primitives
via the orchestrator.identity re-export shim -- this file exercises them
at their real, canonical import path."""

from __future__ import annotations

import os
import stat

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.gate_identity import (
    IdentityError,
    canonical_payload,
    default_identity_dir,
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


def test_default_identity_dir_honors_the_env_var_override(monkeypatch, tmp_path):
    override = tmp_path / "custom-identity-dir"
    monkeypatch.setenv("TESS_OS_APPROVAL_IDENTITY_DIR", str(override))
    assert default_identity_dir() == override


def test_default_identity_dir_falls_back_to_home_when_unset(monkeypatch):
    monkeypatch.delenv("TESS_OS_APPROVAL_IDENTITY_DIR", raising=False)
    assert str(default_identity_dir()).endswith(str(os.path.join(".tess-os", "approval-identity")))


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

    for field, new_value in (
        ("approved_by", "Xavier"),
        ("approved", not payload["approved"]),
        ("plan_id", "plan-different000"),
        ("content_hash", "b" * 64),
        ("nonce", "nonce-attacker-chosen"),
    ):
        tampered = dict(payload)
        tampered[field] = new_value
        assert verify_signature(key, tampered, signature) is False, field


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
