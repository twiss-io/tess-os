"""The daemon's own tiny bookkeeping file — NOT the registry, NOT a card.

Tracks two things the runner needs across invocations that don't belong in
git-tracked memory/: (1) when a card was last alarmed, so a still-stalled
card doesn't re-page an operator on every tick; (2) the date of the last
daily recompile, so the runner knows whether today's tick should also run
the recompile.

Lives under the runner's configured state dir (`config.resolved_state_dir()`,
default `~/.tess-os/memory-heartbeat/state.json`) — outside the repo, same
convention as the lockfile. This is disposable: deleting it just means
"re-alarm everything once, redo today's recompile" — never a data-loss risk
to the actual registry.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional

from . import config as config_mod


def _state_path(state_dir: Optional[Path] = None) -> Path:
    state_dir = state_dir or config_mod.load().resolved_state_dir()
    return state_dir / "state.json"


def load(state_dir: Optional[Path] = None) -> Dict[str, Any]:
    path = _state_path(state_dir)
    if not path.exists():
        return {"last_alarm": {}, "last_recompile_date": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"last_alarm": {}, "last_recompile_date": None}


def save(state: Dict[str, Any], state_dir: Optional[Path] = None) -> None:
    path = _state_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def last_alarm_for(state: Dict[str, Any], slug: str) -> Optional[datetime]:
    raw = state.get("last_alarm", {}).get(slug)
    if not raw:
        return None
    return datetime.fromisoformat(raw)


def record_alarm(state: Dict[str, Any], slug: str, when: datetime) -> None:
    state.setdefault("last_alarm", {})[slug] = when.isoformat()


def recompile_due_today(state: Dict[str, Any], today: date) -> bool:
    last = state.get("last_recompile_date")
    return last != today.isoformat()


def record_recompile(state: Dict[str, Any], today: date) -> None:
    state["last_recompile_date"] = today.isoformat()
