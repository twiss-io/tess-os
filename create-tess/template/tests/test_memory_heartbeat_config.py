"""Unit tests for scripts/heartbeat/config.py — the generalized configuration
loader (org/repo scan, notify channel, activation gate, state dir, timezone).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from heartbeat import config as config_mod  # noqa: E402


def test_shipped_config_defaults_are_inert():
    cfg = config_mod.load()
    assert cfg.is_activated() is False
    assert cfg.notify.channel == "none"
    assert cfg.daily_recompile.org_repo_scan == []
    assert cfg.daily_recompile.memory_project_glob is None


def test_load_missing_file_falls_back_to_safe_defaults(tmp_path):
    cfg = config_mod.load(tmp_path / "does-not-exist.json")
    assert cfg.activated is False
    assert cfg.notify.channel == "none"
    assert cfg.model == "sonnet"
    assert cfg.timezone == "UTC"


def test_load_reads_real_config_values(tmp_path):
    path = tmp_path / "heartbeat.config.json"
    path.write_text(json.dumps({
        "activated": True,
        "model": "opus",
        "timezone": "Asia/Singapore",
        "notify": {"channel": "webhook", "webhook_url_env": "MY_WEBHOOK_URL"},
        "daily_recompile": {"org_repo_scan": ["acme"], "wiki_log_path": None},
    }), encoding="utf-8")
    cfg = config_mod.load(path)
    assert cfg.activated is True
    assert cfg.model == "opus"
    assert cfg.notify.channel == "webhook"
    assert cfg.notify.webhook_url_env == "MY_WEBHOOK_URL"
    assert cfg.daily_recompile.org_repo_scan == ["acme"]
    assert cfg.daily_recompile.wiki_log_path is None


def test_is_activated_env_override_true(monkeypatch, tmp_path):
    cfg = config_mod.load(tmp_path / "missing.json")
    assert cfg.activated is False
    monkeypatch.setenv("TESS_MEMORY_HEARTBEAT_ACTIVATED", "1")
    assert cfg.is_activated() is True


def test_is_activated_env_override_false_wins_over_config_true(monkeypatch, tmp_path):
    path = tmp_path / "heartbeat.config.json"
    path.write_text(json.dumps({"activated": True}), encoding="utf-8")
    cfg = config_mod.load(path)
    assert cfg.activated is True
    monkeypatch.setenv("TESS_MEMORY_HEARTBEAT_ACTIVATED", "0")
    # Explicit false override always wins — fail-closed on ambiguity.
    assert cfg.is_activated() is False


def test_resolved_state_dir_default(tmp_path, monkeypatch):
    monkeypatch.delenv("TESS_MEMORY_STATE_DIR", raising=False)
    cfg = config_mod.load(tmp_path / "missing.json")
    assert cfg.resolved_state_dir() == Path.home() / ".tess-os" / "memory-heartbeat"


def test_resolved_state_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_MEMORY_STATE_DIR", str(tmp_path / "custom-state"))
    cfg = config_mod.load(tmp_path / "missing.json")
    assert cfg.resolved_state_dir() == tmp_path / "custom-state"


def test_resolved_tzinfo_default_utc(tmp_path):
    cfg = config_mod.load(tmp_path / "missing.json")
    assert str(cfg.resolved_tzinfo()) == "UTC"


def test_committed_config_file_has_no_secret_looking_values():
    """The shipped heartbeat.config.json must only ever contain env-var
    *names*, never a value that looks like a live secret."""
    raw = json.loads(config_mod.DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    flat = json.dumps(raw)
    for banned in ("ghp_", "xox", "sk-", "AIza", "-----BEGIN"):
        assert banned not in flat
