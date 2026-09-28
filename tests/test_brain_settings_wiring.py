"""Claude Code settings wiring for the brain (frozen spec section 9.6, as amended in v0.2.1).

Pins the exact hook command line, that .claude/settings.json is
byte-identical to .tess/core/settings-core.json, that auto memory is ON at
project level (v0.2.1 decision: a cache until automatic capture, #195,
ships), that agents are pre-approved only for read-only git, that the lock
pins the new settings bytes, and that the unshipped tessbrain.py is wired
nowhere (v0.2.1 security review: hooks must not run a file that does not
ship; the tool gets its own pinned entry when it ships).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CORE = REPO / ".tess" / "core" / "settings-core.json"
LIVE = REPO / ".claude" / "settings.json"

ONBOARD_START = ('python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/run-pinned.py" --on-fail warn '
                 '--closure scripts/brain -- scripts/brain/onboard.py hook session-start --runtime claude')
READ_ONLY_GIT = [
    "Bash(git status:*)",
    "Bash(git diff:*)",
    "Bash(git log:*)",
    "Bash(git show:*)",
    "Bash(git branch --list:*)",
]


@pytest.fixture(scope="module")
def settings():
    return json.loads(CORE.read_text())


def test_live_settings_byte_identical_to_core():
    assert LIVE.read_bytes() == CORE.read_bytes()


def test_auto_memory_on_and_permissions(settings):
    assert settings["autoMemoryEnabled"] is True
    allow = settings["permissions"]["allow"]
    assert "Bash(python3 scripts/brain/onboard.py:*)" in allow
    assert not any("tessbrain.py" in entry for entry in allow)
    assert allow[:5] == READ_ONLY_GIT, "read-only git first, in this order"
    git_rules = [e for e in allow if e.startswith("Bash(git")]
    assert git_rules == READ_ONLY_GIT, "no write git command may be pre-approved"
    assert "Bash(git*)" not in allow and "Bash(git:*)" not in allow


def test_session_start_runs_only_the_pinned_onboarding_hook(settings):
    groups = settings["hooks"]["SessionStart"]
    assert len(groups) == 1 and groups[0]["matcher"] == "startup|resume|clear|compact"
    assert groups[0]["hooks"] == [{"type": "command", "command": ONBOARD_START, "timeout": 5}]


def test_prompt_hook_is_only_the_pinned_utc_context(settings):
    hooks = settings["hooks"]["UserPromptSubmit"][0]["hooks"]
    assert [h["command"] for h in hooks] == [
        'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/run-pinned.py" --on-fail warn -- '
        '.claude/hooks/utc-local-context.sh']


def test_no_stop_hook_until_the_learning_tool_ships(settings):
    assert "Stop" not in settings["hooks"]
    assert "tessbrain" not in json.dumps(settings)


def test_brain_wiring_touches_only_session_start(settings):
    brain_events = {event for event, groups in settings["hooks"].items() for g in groups
                    for h in g.get("hooks", []) if "scripts/brain/" in h.get("command", "")}
    assert brain_events == {"SessionStart"}


def test_lock_pins_new_settings_bytes():
    lock = (REPO / ".tess" / "tess.lock").read_text()
    digest = "sha256:" + hashlib.sha256(CORE.read_bytes()).hexdigest()
    block = lock.split("  .tess/core/settings-core.json:\n", 1)[1].split("\n  .", 1)[0]
    assert "base_sha: %s" % digest in block
    assert "tier: security" in block
