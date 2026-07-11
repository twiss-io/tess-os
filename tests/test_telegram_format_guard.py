"""
`telegram-format-guard.sh` — contract test for its PreToolUse hookSpecificOutput
shape (Ada, framework reliability batch, 2026-07-11).

The hook previously emitted `modifiedToolInput` — NOT a real Claude Code hook
field (the correct field is `updatedInput`; verified against the official
Claude Code hooks reference, https://code.claude.com/docs/en/hooks: "PreToolUse:
`updatedInput` directly under `hookSpecificOutput` replaces a tool's arguments
before it runs"). Because the field name was wrong, the MarkdownV2-escape
strip this hook exists to perform NEVER actually applied to the live tool
call — Claude Code silently ignored the unrecognized field — while the
`systemMessage` unconditionally claimed the strip succeeded. Any operator
reading the systemMessage had no way to know the fix never landed.

`updatedInput` REPLACES the tool's entire input (not a merge), so the fix
also has to carry forward every OTHER tool_input field (chat_id, reply_to,
files, etc.) unchanged — only `text` may differ from the original call.

These tests exercise the REAL bash script via subprocess (the same
PreToolUse JSON-on-stdin protocol Claude Code uses), not a reimplementation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE_HOOK = REPO_ROOT / ".claude" / "hooks" / "telegram-format-guard.sh"
CORE_HOOK = REPO_ROOT / ".tess" / "core" / "hooks" / "telegram-format-guard.sh"

HAS_BASH = shutil.which("bash") is not None
HAS_JQ = shutil.which("jq") is not None
pytestmark = pytest.mark.skipif(
    not (HAS_BASH and HAS_JQ), reason="bash and jq required to exercise the real hook"
)


def _run_hook(tool_input: dict, *, hook_path: Path = LIVE_HOOK):
    """Invoke the real hook exactly as Claude Code's PreToolUse protocol
    does: the tool-call JSON on stdin."""
    payload = {"tool_name": "mcp__plugin_telegram_telegram__reply", "tool_input": tool_input}
    return subprocess.run(
        ["bash", str(hook_path)],
        input=json.dumps(payload),
        capture_output=True, text=True, env=dict(os.environ),
    )


# ---------------------------------------------------------------------------
# Contract: the emitted JSON shape uses `updatedInput`, never the old
# invalid `modifiedToolInput` field.
# ---------------------------------------------------------------------------

def test_emits_updated_input_not_modified_tool_input():
    r = _run_hook({"chat_id": "-1003855035139", "text": "Deploy done \\- all green\\."})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)

    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert "updatedInput" in hso, "must use the real hook field `updatedInput`"
    assert "modifiedToolInput" not in hso, "the old, invalid field must be gone"
    assert hso["updatedInput"]["text"] == "Deploy done - all green."


def test_system_message_no_longer_overclaims():
    """The systemMessage must not silently overclaim a strip that never
    applies — this is a light wording check, not a behavior check (the
    prior bug was field-shape, not message wording), but the message
    should describe what genuinely happened."""
    r = _run_hook({"chat_id": "1", "text": "escaped \\- text"})
    out = json.loads(r.stdout)
    msg = out["systemMessage"]
    assert "stripped" in msg.lower()
    assert "markdownv2" in msg.lower()


# ---------------------------------------------------------------------------
# updatedInput REPLACES the whole tool_input — every other field must
# survive untouched, only `text` may change.
# ---------------------------------------------------------------------------

def test_preserves_all_other_tool_input_fields():
    original = {
        "chat_id": "-1003855035139",
        "text": "Deploy done \\- all green\\.",
        "reply_to": 12345,
        "files": ["a.png", "b.png"],
        "format": "",
    }
    r = _run_hook(original)
    assert r.returncode == 0, r.stderr
    updated = json.loads(r.stdout)["hookSpecificOutput"]["updatedInput"]

    for key in ("chat_id", "reply_to", "files"):
        assert updated[key] == original[key], f"{key} must survive untouched"
    assert updated["text"] == "Deploy done - all green."


# ---------------------------------------------------------------------------
# Skip paths — unchanged behavior, no output, exit 0.
# ---------------------------------------------------------------------------

def test_no_output_when_format_is_markdownv2():
    r = _run_hook({"chat_id": "1", "text": "escaped \\- text", "format": "markdownv2"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


def test_no_output_when_no_mv2_escapes_present():
    r = _run_hook({"chat_id": "1", "text": "plain prose, no escapes here"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


def test_never_blocks_the_tool_call():
    """This hook only rewrites text — it must never deny/block."""
    r = _run_hook({"chat_id": "1", "text": "escaped \\- text"})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["hookSpecificOutput"].get("permissionDecision") != "deny"


# ---------------------------------------------------------------------------
# Both shipped copies (live mirror + core master) must be identical and
# individually exhibit the fixed behavior.
# ---------------------------------------------------------------------------

def test_live_and_core_copies_are_byte_identical():
    assert LIVE_HOOK.read_bytes() == CORE_HOOK.read_bytes(), (
        "the .claude/hooks/ live mirror and .tess/core/hooks/ core master "
        "have drifted — both must ship the updatedInput fix"
    )


def test_core_copy_also_emits_updated_input():
    r = _run_hook({"chat_id": "1", "text": "escaped \\- text"}, hook_path=CORE_HOOK)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert "updatedInput" in out["hookSpecificOutput"]
