"""Tests for telemetry.consent -- the opt-in gate. Every test passes an
explicit telemetry_dir=tmp_path/... -- none of this suite ever touches
the real machine's own ~/.tess-os/telemetry/."""

from __future__ import annotations

import getpass
import json
import socket

import pytest

import _telemetry_paths  # noqa: F401 -- sys.path bootstrap

from telemetry import consent


def test_fresh_directory_is_disabled_by_default(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    assert consent.is_enabled(telemetry_dir) is False
    state = consent.status(telemetry_dir)
    assert state.enabled is False
    assert state.install_id is None
    assert state.consented_at is None
    # Checking status must not itself create the directory or any file --
    # the OFF/absent state is read-only.
    assert not telemetry_dir.exists()


def test_enable_writes_consent_file_and_generates_install_id(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    state = consent.enable(telemetry_dir)
    assert state.enabled is True
    assert state.install_id
    assert state.consented_at
    consent_path = telemetry_dir / "consent.json"
    assert consent_path.is_file()
    raw = json.loads(consent_path.read_text(encoding="utf-8"))
    assert raw == {"enabled": True, "install_id": state.install_id, "consented_at": state.consented_at}
    assert consent.is_enabled(telemetry_dir) is True


def test_install_id_is_a_random_uuid_not_derived_from_machine_identity(tmp_path):
    state = consent.enable(tmp_path / "telemetry")
    # Never leaks the OS username or hostname into the install id.
    assert getpass.getuser() not in state.install_id
    assert socket.gethostname() not in state.install_id
    # A valid uuid4 hex string: 32 lowercase hex characters.
    assert len(state.install_id) == 32
    int(state.install_id, 16)  # raises ValueError if not hex


def test_enable_is_idempotent_keeps_same_install_id(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    first = consent.enable(telemetry_dir)
    second = consent.enable(telemetry_dir)
    assert second.install_id == first.install_id
    assert second.consented_at == first.consented_at


def test_disable_keeps_install_id_but_flips_enabled_false(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    enabled_state = consent.enable(telemetry_dir)
    disabled_state = consent.disable(telemetry_dir)
    assert disabled_state.enabled is False
    assert disabled_state.install_id == enabled_state.install_id
    assert consent.is_enabled(telemetry_dir) is False


def test_re_enable_after_disable_keeps_the_same_install_id(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    first = consent.enable(telemetry_dir)
    consent.disable(telemetry_dir)
    second = consent.enable(telemetry_dir)
    assert second.install_id == first.install_id


def test_corrupt_consent_file_fails_loud_not_silently_treated_as_disabled(tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    telemetry_dir.mkdir(parents=True)
    (telemetry_dir / "consent.json").write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(consent.TelemetryError):
        consent.is_enabled(telemetry_dir)


def test_default_telemetry_dir_honors_env_override(monkeypatch, tmp_path):
    override = tmp_path / "custom-telemetry-dir"
    monkeypatch.setenv("TESS_OS_TELEMETRY_DIR", str(override))
    assert consent.default_telemetry_dir() == override
