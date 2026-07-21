"""Configuration loader for the memory-continuity heartbeat runner.

Every value that was hardcoded to a single operator's machine/org/chat in the
reference implementation this module was ported from now lives here, loaded
from a single committed JSON file (`scripts/heartbeat/heartbeat.config.json`)
with environment-variable overrides for anything secret or deployment-local.
No secret VALUE is ever read from this file or committed to git — only the
name of the environment variable that holds it (e.g. `bot_token_env`), per
this project's "never hardcode credentials" rule.

Shipped defaults are deliberately inert:
  - `activated: false` — see `is_activated()`. This is a second, independent
    off switch on top of "the launchd plist is staged, not loaded" (see
    scripts/launchd/README in this same directory tree) — added specifically
    because this code now ships to every `create-tess` instance rather than
    running on one operator's own machine, so the blast radius of an
    accidental invocation is larger and deserves a second gate.
  - `notify.channel: "none"` — no notification channel wired until an
    operator picks one and supplies its secret via env var.
  - `daily_recompile.org_repo_scan: []` and `memory_project_glob: null` —
    the "unregistered work" scan does nothing until an operator opts a real
    org/path in; it never assumes any particular org or directory layout.

See scripts/heartbeat/README.md for the full field reference.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "heartbeat.config.json"

_TRUTHY = {"1", "true", "yes", "on"}


def _env_flag(name: str) -> Optional[bool]:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip().lower() in _TRUTHY


@dataclass
class NotifyConfig:
    channel: str = "none"  # "none" | "telegram" | "webhook"
    telegram_bot_token_env: str = "TESS_MEMORY_TELEGRAM_BOT_TOKEN"
    telegram_chat_id_env: str = "TESS_MEMORY_TELEGRAM_CHAT_ID"
    webhook_url_env: str = "TESS_MEMORY_WEBHOOK_URL"


@dataclass
class DailyRecompileConfig:
    org_repo_scan: List[str] = field(default_factory=list)
    memory_project_glob: Optional[str] = None
    wiki_log_path: Optional[str] = "kb/wiki/log.md"
    wiki_log_tail_lines: int = 150


@dataclass
class HeartbeatConfig:
    activated: bool = False
    model: str = "sonnet"
    state_dir: Optional[str] = None
    timezone: str = "UTC"
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    daily_recompile: DailyRecompileConfig = field(default_factory=DailyRecompileConfig)
    raw: Dict[str, Any] = field(default_factory=dict)

    def resolved_tzinfo(self) -> ZoneInfo:
        """The timezone the daily-recompile-due check is computed in (IANA
        name, e.g. "UTC", "Asia/Singapore", "America/New_York"). Defaults to
        UTC — the only timezone-neutral default a framework shipping to
        operators in any region can safely assume."""
        return ZoneInfo(self.timezone)

    def is_activated(self) -> bool:
        """Two independent signals must agree for this to return True:
        the committed config's `activated` field, OR an explicit env var
        override (`TESS_MEMORY_HEARTBEAT_ACTIVATED=1`) for CI/ephemeral
        testing where editing the committed file isn't desired. Either
        being explicitly false always wins over the other being true —
        this function is a gate, not a convenience toggle, so it fails
        closed on any ambiguity.
        """
        env_override = _env_flag("TESS_MEMORY_HEARTBEAT_ACTIVATED")
        if env_override is False:
            return False
        if env_override is True:
            return True
        return bool(self.activated)

    def resolved_state_dir(self) -> Path:
        override = os.environ.get("TESS_MEMORY_STATE_DIR")
        if override:
            return Path(override).expanduser()
        if self.state_dir:
            return Path(self.state_dir).expanduser()
        return Path.home() / ".tess-os" / "memory-heartbeat"


def load(config_path: Optional[Path] = None) -> HeartbeatConfig:
    path = config_path or DEFAULT_CONFIG_PATH
    raw: Dict[str, Any] = {}
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))

    notify_raw = raw.get("notify", {}) or {}
    notify = NotifyConfig(
        channel=notify_raw.get("channel", "none"),
        telegram_bot_token_env=notify_raw.get(
            "telegram_bot_token_env", "TESS_MEMORY_TELEGRAM_BOT_TOKEN"
        ),
        telegram_chat_id_env=notify_raw.get(
            "telegram_chat_id_env", "TESS_MEMORY_TELEGRAM_CHAT_ID"
        ),
        webhook_url_env=notify_raw.get("webhook_url_env", "TESS_MEMORY_WEBHOOK_URL"),
    )

    dr_raw = raw.get("daily_recompile", {}) or {}
    daily_recompile = DailyRecompileConfig(
        org_repo_scan=list(dr_raw.get("org_repo_scan", [])),
        memory_project_glob=dr_raw.get("memory_project_glob"),
        wiki_log_path=dr_raw.get("wiki_log_path", "kb/wiki/log.md"),
        wiki_log_tail_lines=int(dr_raw.get("wiki_log_tail_lines", 150)),
    )

    return HeartbeatConfig(
        activated=bool(raw.get("activated", False)),
        model=raw.get("model", "sonnet"),
        state_dir=raw.get("state_dir"),
        timezone=raw.get("timezone", "UTC"),
        notify=notify,
        daily_recompile=daily_recompile,
        raw=raw,
    )
