"""Tests for telemetry.cli -- exercised via main() directly (real
argparse + the real consent/store/summary functions, scoped to a
per-test tmp_path via TESS_OS_TELEMETRY_DIR), not via subprocess."""

from __future__ import annotations

import _telemetry_paths  # noqa: F401 -- sys.path bootstrap

from telemetry import cli, consent


def test_status_reports_disabled_by_default(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TESS_OS_TELEMETRY_DIR", str(tmp_path / "telemetry"))
    exit_code = cli.main(["status"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "enabled:      False" in out


def test_enable_then_status_reports_enabled(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TESS_OS_TELEMETRY_DIR", str(tmp_path / "telemetry"))
    assert cli.main(["enable"]) == 0
    capsys.readouterr()
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "enabled:      True" in out


def test_summary_with_no_events_reports_none_recorded(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TESS_OS_TELEMETRY_DIR", str(tmp_path / "telemetry"))
    assert cli.main(["summary"]) == 0
    out = capsys.readouterr().out
    assert "No local telemetry events recorded yet." in out


def test_delete_removes_local_state(monkeypatch, tmp_path):
    telemetry_dir = tmp_path / "telemetry"
    monkeypatch.setenv("TESS_OS_TELEMETRY_DIR", str(telemetry_dir))
    cli.main(["enable"])
    assert telemetry_dir.is_dir()
    cli.main(["delete"])
    assert not telemetry_dir.exists()


def test_disable_after_enable_flips_state(monkeypatch, tmp_path):
    monkeypatch.setenv("TESS_OS_TELEMETRY_DIR", str(tmp_path / "telemetry"))
    cli.main(["enable"])
    cli.main(["disable"])
    assert consent.is_enabled() is False
