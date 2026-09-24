"""Unit tests for scripts/heartbeat/notify.py — pluggable notification
channel selection. No test in this file makes a real network call — the
"none" channel is a pure no-op, the "webhook" path is exercised only in its
"env var not set" branch, and the one test that simulates a live failure
path monkeypatches `urlopen` to fail deterministically.

The base harness reports in the active session; this heartbeat notification
is an opt-in operator add-on with exactly two channels: "none" (default) and
a generic "webhook". Every other channel name is a safe no-op.
"""

from __future__ import annotations

import dataclasses
import sys
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from heartbeat import config as config_mod  # noqa: E402
from heartbeat import notify  # noqa: E402


def test_dry_run_never_sends_regardless_of_channel():
    cfg = config_mod.HeartbeatConfig(notify=config_mod.NotifyConfig(channel="webhook"))
    result = notify.send("hello", dry_run=True, cfg=cfg)
    assert result.sent is False
    assert result.dry_run is True
    assert "would send" in result.detail


def test_none_channel_never_sends():
    cfg = config_mod.HeartbeatConfig(notify=config_mod.NotifyConfig(channel="none"))
    result = notify.send("hello", dry_run=False, cfg=cfg)
    assert result.sent is False
    assert result.channel == "none"


def test_shipped_default_channel_is_none():
    assert config_mod.NotifyConfig().channel == "none"
    assert config_mod.load().notify.channel == "none"


def test_notify_config_carries_no_chat_service_fields():
    """Only the generic webhook is configurable: no bot-token or chat-id
    env-var names ship in the default config."""
    names = {f.name for f in dataclasses.fields(config_mod.NotifyConfig)}
    assert names == {"channel", "webhook_url_env"}


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
    assert "'webhook'" in result.detail, "the no-op detail must name the supported replacement"


def test_no_secret_value_ever_appears_in_repr(monkeypatch):
    """Even on a failure path with a real-looking secret URL set, the returned
    result's own message/detail must never echo the raw secret — only this
    module's own control-flow text. `urlopen` is monkeypatched to fail
    deterministically so this test never makes a real network call."""
    monkeypatch.setenv("TESS_MEMORY_WEBHOOK_URL", "https://hooks.example.invalid/super-secret-token-value")

    def _fake_urlopen(*args, **kwargs):
        raise urllib.error.URLError("simulated network failure")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    cfg = config_mod.HeartbeatConfig(notify=config_mod.NotifyConfig(channel="webhook"))
    result = notify.send("hello", dry_run=False, cfg=cfg)
    assert result.sent is False
    assert "super-secret-token-value" not in repr(result)
    assert "super-secret-token-value" not in result.detail
    assert "simulated network failure" in result.detail
