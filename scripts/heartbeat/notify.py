"""Outbound-only notification dispatch for the heartbeat daemon.

Generalized from a single-operator implementation into a pluggable channel
selected by `notify.channel` in `heartbeat.config.json`:

  - "none"     — default. No-op; always reports as not-sent so callers can
                 still log/inspect what *would* have been sent.
  - "webhook"  — generic HTTPS POST of `{"text": message}` to the URL in the
                 env var named by `notify.webhook_url_env` (Slack incoming
                 webhooks and most generic chat-ops webhooks accept this
                 shape as-is).

The base harness itself reports in the active session and needs no external
channel; this heartbeat notification is an opt-in operator add-on. Any other
`notify.channel` value (including a chat-service name from an older config)
is a safe no-op.

A notification failure must never crash the caller — the daemon's per-card
loop and daily recompile continue regardless; a failed send is logged in the
returned result, not raised.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

from . import config as config_mod


class NotifyResult:
    def __init__(self, sent: bool, dry_run: bool, channel: str, message: str, detail: str = ""):
        self.sent = sent
        self.dry_run = dry_run
        self.channel = channel
        self.message = message
        self.detail = detail

    def __repr__(self) -> str:
        if self.dry_run:
            tag = "DRY-RUN (not sent)"
        elif self.sent:
            tag = "sent"
        else:
            tag = "FAILED"
        return f"<NotifyResult channel={self.channel!r} {tag}: {self.detail or self.message[:60]!r}>"


def _send_webhook(message: str, cfg: config_mod.NotifyConfig) -> NotifyResult:
    url = os.environ.get(cfg.webhook_url_env)
    if not url:
        return NotifyResult(
            sent=False, dry_run=False, channel="webhook", message=message,
            detail=f"webhook channel selected but env var {cfg.webhook_url_env} not set",
        )
    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = 200 <= resp.status < 300
            return NotifyResult(sent=ok, dry_run=False, channel="webhook", message=message, detail=f"HTTP {resp.status}")
    except urllib.error.URLError as exc:
        return NotifyResult(
            sent=False, dry_run=False, channel="webhook", message=message,
            detail=f"webhook POST failed: {exc}",
        )


def send(message: str, dry_run: bool, cfg: Optional[config_mod.HeartbeatConfig] = None) -> NotifyResult:
    cfg = cfg or config_mod.load()
    channel = cfg.notify.channel

    if dry_run:
        return NotifyResult(
            sent=False, dry_run=True, channel=channel, message=message,
            detail=f"would send via channel={channel!r}: {message[:120]}",
        )

    if channel == "none":
        return NotifyResult(
            sent=False, dry_run=False, channel="none", message=message,
            detail="notify.channel is 'none' — no channel configured, message not sent",
        )
    if channel == "webhook":
        return _send_webhook(message, cfg.notify)

    return NotifyResult(
        sent=False, dry_run=False, channel=channel, message=message,
        detail=f"unknown notify.channel {channel!r} — no-op",
    )
