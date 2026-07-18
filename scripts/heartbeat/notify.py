"""Outbound-only notification dispatch for the heartbeat daemon.

Generalized from a Telegram-only, single-operator implementation into a
pluggable channel selected by `notify.channel` in `heartbeat.config.json`:

  - "none"     — default. No-op; always reports as not-sent so callers can
                 still log/inspect what *would* have been sent.
  - "telegram" — calls Bot API `sendMessage` ONLY, never `getUpdates` or any
                 long-poll/webhook-registering endpoint (an interactive
                 Telegram integration may already hold that session's single
                 getUpdates slot for the same token; a second consumer would
                 409 and starve it). Bot token is read fresh from the env var
                 named by `notify.telegram_bot_token_env` on every call
                 (never cached, never committed) — chat id likewise from
                 `notify.telegram_chat_id_env`.
  - "webhook"  — generic HTTPS POST of `{"text": message}` to the URL in the
                 env var named by `notify.webhook_url_env` (Slack incoming
                 webhooks and most generic chat-ops webhooks accept this
                 shape as-is).

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


def _send_telegram(message: str, cfg: config_mod.NotifyConfig) -> NotifyResult:
    token = os.environ.get(cfg.telegram_bot_token_env)
    chat_id = os.environ.get(cfg.telegram_chat_id_env)
    if not token or not chat_id:
        missing = [
            name
            for name, val in (
                (cfg.telegram_bot_token_env, token),
                (cfg.telegram_chat_id_env, chat_id),
            )
            if not val
        ]
        return NotifyResult(
            sent=False, dry_run=False, channel="telegram", message=message,
            detail=f"telegram channel selected but env var(s) not set: {', '.join(missing)}",
        )
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            ok = 200 <= resp.status < 300
            return NotifyResult(sent=ok, dry_run=False, channel="telegram", message=message, detail=body[:200])
    except urllib.error.URLError as exc:
        return NotifyResult(
            sent=False, dry_run=False, channel="telegram", message=message,
            detail=f"Telegram sendMessage failed: {exc}",
        )


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
    if channel == "telegram":
        return _send_telegram(message, cfg.notify)
    if channel == "webhook":
        return _send_webhook(message, cfg.notify)

    return NotifyResult(
        sent=False, dry_run=False, channel=channel, message=message,
        detail=f"unknown notify.channel {channel!r} — no-op",
    )
