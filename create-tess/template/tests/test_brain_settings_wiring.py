"""Claude Code settings wiring for the brain (frozen spec section 9.6, as amended in v0.2.1).

Pins the exact hook command line, that .claude/settings.json is
byte-identical to .tess/core/settings-core.json, that auto memory is ON at
project level (v0.2.1 decision: a cache until automatic capture, #195,
ships), that agents are pre-approved only for read-only git, that the lock
pins the new settings bytes, and (v1.0, the learning loop ships) that
tessbrain.py is wired only through the pinned launcher, on SessionStart,
UserPromptSubmit, Stop and SessionEnd.
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

LAUNCH = 'python3 -I -B "$CLAUDE_PROJECT_DIR/.claude/hooks/run-pinned.py" --on-fail warn --closure scripts/brain -- '
ONBOARD_START = LAUNCH + "scripts/brain/onboard.py hook session-start --runtime claude"
LEARN = LAUNCH + "scripts/brain/tessbrain.py hook %s --runtime claude"
LEARN_ALLOW = ["Bash(python3 scripts/brain/tessbrain.py %s:*)" % c
               for c in ("recall", "status", "review", "sync", "save", "index", "lint", "decide", "remember",
                         "inbox", "journal note")]
# v1.0 security review round 2 (H-A): git diff/log/show are no longer
# pre-approved; they take --output=<file>, which writes any file.
READ_ONLY_GIT = [
    "Bash(git status:*)",
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
    # v1.0 allow-list fix (2026-10-08): only onboarding's read-only status is pre-approved; answer,
    # add-mode, skip, apply and restore record the operator's words or change setup, so they ask.
    assert "Bash(python3 scripts/brain/onboard.py status:*)" in allow
    assert "Bash(python3 scripts/brain/onboard.py:*)" not in allow
    # v1.0 e2e review (S6, owner decision): `save` is pre-approved so saving does not
    # prompt every time. It is the one path-scoped commit of brain/; the git hooks and
    # the pre-push ship gate still run on it. Every other write verb stays unapproved.
    assert [e for e in allow if "tessbrain.py" in e] == LEARN_ALLOW
    assert allow[:len(READ_ONLY_GIT)] == READ_ONLY_GIT, "read-only git first, in this order"
    git_rules = [e for e in allow if e.startswith("Bash(git")]
    assert git_rules == READ_ONLY_GIT, "no write git command may be pre-approved"
    assert "Bash(git*)" not in allow and "Bash(git:*)" not in allow


def test_session_start_runs_onboarding_then_the_brain_snapshot(settings):
    groups = settings["hooks"]["SessionStart"]
    assert len(groups) == 1 and groups[0]["matcher"] == "startup|resume|clear|compact"
    assert groups[0]["hooks"] == [{"type": "command", "command": ONBOARD_START, "timeout": 5},
                                  {"type": "command", "command": LEARN % "session-start", "timeout": 5}]


def test_prompt_hooks_are_the_utc_context_then_capture(settings):
    hooks = settings["hooks"]["UserPromptSubmit"][0]["hooks"]
    assert [h["command"] for h in hooks] == [
        'python3 -I -B "$CLAUDE_PROJECT_DIR/.claude/hooks/run-pinned.py" --on-fail warn -- '
        '.claude/hooks/utc-local-context.sh', LEARN % "prompt"]


def test_stop_and_session_end_hand_the_transcript_to_the_pinned_sync(settings):
    assert settings["hooks"]["Stop"] == [{"hooks": [{"type": "command", "command": LEARN % "stop", "timeout": 30}]}]
    assert {"type": "command", "command": LEARN % "stop", "timeout": 30} in settings["hooks"]["SessionEnd"][0]["hooks"]


def test_every_brain_hook_goes_through_the_launcher(settings):
    brain = [(event, h["command"]) for event, groups in settings["hooks"].items() for g in groups
             for h in g.get("hooks", []) if "scripts/brain/" in h.get("command", "")]
    assert {e for e, _ in brain} == {"SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"}
    assert all(c.startswith(LAUNCH) for _, c in brain)


def test_lock_pins_new_settings_bytes():
    lock = (REPO / ".tess" / "tess.lock").read_text()
    digest = "sha256:" + hashlib.sha256(CORE.read_bytes()).hexdigest()
    block = lock.split("  .tess/core/settings-core.json:\n", 1)[1].split("\n  .", 1)[0]
    assert "base_sha: %s" % digest in block
    assert "tier: security" in block
