"""Unit tests for scripts/heartbeat/notify.py — pluggable notification
channel selection. No test in this file makes a real network call — the
"none" channel is a pure no-op, the "telegram"/"webhook" paths are exercised
only in their "env var not set" branch, and the one test that simulates a
live-token failure path monkeypatches `urlopen` to fail deterministically
rather than actually calling api.telegram.org.
"""

from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from heartbeat import config as config_mod  # noqa: E402
from heartbeat import notify  # noqa: E402


def test_dry_run_never_sends_regardless_of_channel():
    cfg = config_mod.HeartbeatConfig(notify=config_mod.NotifyConfig(channel="telegram"))
    result = notify.send("hello", dry_run=True, cfg=cfg)
    assert result.sent is False
    assert result.dry_run is True
    assert "would send" in result.detail


def test_none_channel_never_sends():
    cfg = config_mod.HeartbeatConfig(notify=config_mod.NotifyConfig(channel="none"))
    result = notify.send("hello", dry_run=False, cfg=cfg)
    assert result.sent is False
    assert result.channel == "none"


def test_telegram_channel_without_env_vars_reports_missing(monkeypatch):
    monkeypatch.delenv("TESS_MEMORY_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TESS_MEMORY_TELEGRAM_CHAT_ID", raising=False)
    cfg = config_mod.HeartbeatConfig(notify=config_mod.NotifyConfig(channel="telegram"))
    result = notify.send("hello", dry_run=False, cfg=cfg)
    assert result.sent is False
    assert "TESS_MEMORY_TELEGRAM_BOT_TOKEN" in result.detail
    assert "TESS_MEMORY_TELEGRAM_CHAT_ID" in result.detail


def test_webhook_channel_without_env_var_reports_missing(monkeypatch):
    monkeypatch.delenv("TESS_MEMORY_WEBHOOK_URL", raising=False)
    cfg = config_mod.HeartbeatConfig(notify=config_mod.NotifyConfig(channel="webhook"))
    result = notify.send("hello", dry_run=False, cfg=cfg)
    assert result.sent is False
    assert "TESS_MEMORY_WEBHOOK_URL" in result.detail


def test_unknown_channel_is_a_safe_noop():
    cfg = config_mod.HeartbeatConfig(notify=config_mod.NotifyConfig(channel="carrier-pigeon"))
    result = notify.send("hello", dry_run=False, cfg=cfg)
    assert result.sent is False
    assert "unknown notify.channel" in result.detail


def test_no_secret_value_ever_appears_in_repr(monkeypatch):
    """Even on a failure path with a real-looking token set, the returned
    result's own message/detail must never echo the raw secret — only this
    module's own control-flow text. `urlopen` is monkeypatched to fail
    deterministically so this test never makes a real network call."""
    monkeypatch.setenv("TESS_MEMORY_TELEGRAM_BOT_TOKEN", "super-secret-token-value")
    monkeypatch.setenv("TESS_MEMORY_TELEGRAM_CHAT_ID", "12345")

    def _fake_urlopen(*args, **kwargs):
        raise urllib.error.URLError("simulated network failure")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    cfg = config_mod.HeartbeatConfig(notify=config_mod.NotifyConfig(channel="telegram"))
    result = notify._send_telegram("hello", cfg.notify)
    assert result.sent is False
    assert "super-secret-token-value" not in repr(result)
    assert "super-secret-token-value" not in result.detail
    assert "simulated network failure" in result.detail
