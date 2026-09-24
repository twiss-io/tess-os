"""Claude Code settings wiring for the brain (frozen spec section 9.6).

Pins the exact hook command lines both builders code against, that
.claude/settings.json is byte-identical to .tess/core/settings-core.json,
that auto memory is off at project level, that the lock pins the new
settings bytes, and that every hook line is a guarded no-op when its script
is absent (so ws-oobe can ship without ws-learn).
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


def line(script: str, event: str) -> str:
    return ("sh -c 'f=\"$CLAUDE_PROJECT_DIR/scripts/brain/%s\"; [ -f \"$f\" ] && exec python3 \"$f\" "
            "hook %s --runtime claude || exit 0'" % (script, event))


FROZEN = {
    "onboard_start": line("onboard.py", "session-start"),
    "learn_start": line("tessbrain.py", "session-start"),
    "prompt": line("tessbrain.py", "prompt"),
    "stop": line("tessbrain.py", "stop"),
}


@pytest.fixture(scope="module")
def settings():
    return json.loads(CORE.read_text())


def test_live_settings_byte_identical_to_core():
    assert LIVE.read_bytes() == CORE.read_bytes()


def test_auto_memory_off_and_permissions(settings):
    assert settings["autoMemoryEnabled"] is False
    allow = settings["permissions"]["allow"]
    assert "Bash(python3 scripts/brain/onboard.py:*)" in allow
    assert "Bash(python3 scripts/brain/tessbrain.py:*)" in allow
    assert allow[0] == "Bash(git*)", "pre-existing entries kept first"


def test_session_start_two_parallel_hooks(settings):
    groups = settings["hooks"]["SessionStart"]
    assert len(groups) == 1 and groups[0]["matcher"] == "startup|resume|clear|compact"
    hooks = groups[0]["hooks"]
    assert [x["command"] for x in hooks] == [FROZEN["onboard_start"], FROZEN["learn_start"]]
    assert all(x["type"] == "command" and x["timeout"] == 5 for x in hooks)


def test_prompt_hook_appended_after_utc_context(settings):
    hooks = settings["hooks"]["UserPromptSubmit"][0]["hooks"]
    assert hooks[0]["command"] == "$CLAUDE_PROJECT_DIR/.claude/hooks/utc-local-context.sh"
    assert hooks[1] == {"type": "command", "command": FROZEN["prompt"], "timeout": 3}


def test_stop_hook_is_async_write_only(settings):
    groups = settings["hooks"]["Stop"]
    assert groups == [{"hooks": [{"type": "command", "command": FROZEN["stop"], "async": True, "timeout": 30}]}]


def test_existing_hooks_untouched(settings):
    pre = settings["hooks"]["PreToolUse"]
    assert [g["matcher"] for g in pre] == ["mcp__plugin_telegram_telegram__reply",
                                           "mcp__plugin_telegram_telegram__edit_message",
                                           "^(Task|Agent)$", "^(Bash|Edit|Write)$"]
    assert "SessionEnd" in settings["hooks"] and "PostToolUse" in settings["hooks"]


def test_lock_pins_new_settings_bytes():
    lock = (REPO / ".tess" / "tess.lock").read_text()
    digest = "sha256:" + hashlib.sha256(CORE.read_bytes()).hexdigest()
    block = lock.split("  .tess/core/settings-core.json:\n", 1)[1].split("\n  .", 1)[0]
    assert "base_sha: %s" % digest in block


@pytest.mark.parametrize("key", sorted(FROZEN))
def test_hook_line_is_a_guarded_noop_without_its_script(tmp_path, key):
    done = subprocess.run(["sh", "-c", FROZEN[key].split("sh -c ", 1)[1].strip("'")],
                          env={"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True, timeout=10)
    assert done.returncode == 0 and done.stdout == "" and done.stderr == ""
