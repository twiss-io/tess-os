"""v1.0 release integration (#216 over #212-#215): the Claude Code in-session
gate enforces the same rules as the Codex gate.

#216 wired `.claude/hooks/tess-gate.py --runtime claude` as a Claude Code
PreToolUse hook. The #213 hardening (GIT_CONFIG_* assignments, git
include/alias config writes, inline interpreter writes to protected paths),
the #212 parse fallback and the operator-only block (an agent must not fake a
terminal or type `accept v<N>` for `tessctl update`/`approve`) were tested only
through the Codex payload shape. These cases run the real rendered hook
command from `.claude/settings.json` with a Claude payload (no `turn_id`):
hard blocks are denied, approval cases ask in the default mode and are denied
in modes that cannot ask, and the hook launcher is isolated (`python3 -I -B`).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _gate_hook() -> dict:
    data = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    for entry in data["hooks"]["PreToolUse"]:
        for hook in entry["hooks"]:
            if "tess-gate.py" in hook["command"]:
                return hook
    raise AssertionError("no tess-gate.py PreToolUse hook in .claude/settings.json")


def _run(command: str, mode: str = "default"):
    payload = {"session_id": "s", "hook_event_name": "PreToolUse", "cwd": str(REPO),
               "permission_mode": mode, "tool_name": "Bash",
               "tool_input": {"command": command}}
    r = subprocess.run(["sh", "-c", _gate_hook()["command"]], input=json.dumps(payload),
                       capture_output=True, text=True, cwd=str(REPO),
                       env={**os.environ, "CLAUDE_PROJECT_DIR": str(REPO),
                            "TESS_GATE_LOG": os.devnull})
    assert r.returncode == 0, r.stderr
    if not r.stdout.strip():
        return None, ""
    out = json.loads(r.stdout)["hookSpecificOutput"]
    return out["permissionDecision"], out["permissionDecisionReason"]


def test_claude_gate_hook_runs_the_launcher_isolated():
    cmd = _gate_hook()["command"]
    assert 'exec python3 -I -B "$CLAUDE_PROJECT_DIR/.claude/hooks/run-pinned.py" --on-fail block' in cmd
    assert cmd.endswith(".claude/hooks/tess-gate.py --runtime claude")


@pytest.mark.parametrize("cmd", [
    # operator-only prompts (release integration item a)
    "script -q /dev/null ./tessctl update --ref v1.0.1",
    "printf 'accept v1.0.1\\n' | ./tessctl update --ref v1.0.1",
    "unbuffer ./tessctl approve conductor/guardrails.md --rationale x",
    "python3 -c 'import pty; pty.spawn([\"./tessctl\", \"update\"])'",
])
def test_claude_agent_cannot_answer_the_operator_prompts(cmd):
    dec, why = _run(cmd)
    assert dec == "deny", (cmd, dec, why)
    assert "only the operator" in why


@pytest.mark.parametrize("cmd", [
    # #213 gate hardening
    "GIT_CONFIG_GLOBAL=/tmp/evil.gitconfig git commit -m x",
    "git config alias.ci 'commit --no-verify'",
    "git -c include.path=/tmp/evil commit -m x",
    "python3 -c \"open('.tess/tess.lock','w').write('x')\"",
    # #212 parse fallback: a quote in a comment must not fail open
    "rm .claude/hooks/tess-gate.py # it's",
])
def test_claude_gate_denies_the_hardened_bypasses(cmd):
    dec, why = _run(cmd)
    assert dec == "deny", (cmd, dec, why)
    assert why.startswith("TESS GATE:")


@pytest.mark.parametrize("cmd", [
    "git push --force origin main",
    "git remote set-url origin https://example.invalid/x.git",
])
def test_claude_approval_cases_ask_and_are_denied_where_nobody_can_answer(cmd):
    assert _run(cmd)[0] == "ask", cmd
    for mode in ("bypassPermissions", "dontAsk"):
        dec, why = _run(cmd, mode)
        assert dec == "deny" and "cannot pause" in why, (cmd, mode, dec, why)


def test_claude_gate_leaves_ordinary_commands_alone():
    for cmd in ("ls -la", "git status", "./tessctl doctor", "./tessctl update --ref v1.0.1"):
        dec, why = _run(cmd)
        assert dec is None or "only the operator" not in why, (cmd, dec, why)


# CodeQL py/clear-text-logging-sensitive-data on _log: every field the decision
# log writes is redacted at write time, including a path from the tool input
# that a deny reason quotes (edit target, MCP path argument).

_TOKEN = "ghp_" + "Q7" * 20  # token-shaped, built at run time so no scanner sees a literal


@pytest.mark.parametrize("tool,tool_input", [
    ("Bash", {"command": f"curl -H 'Authorization: token {_TOKEN}' https://api.github.com/user"}),
    ("Write", {"file_path": f".claude/hooks/{_TOKEN}.py", "content": "x"}),
    ("Edit", {"file_path": f"conductor/{_TOKEN}/../guardrails.md", "old_string": "a", "new_string": "b"}),
    ("mcp__fs__write_file", {"path": f".claude/hooks/{_TOKEN}.py", "content": "x"}),
])
def test_decision_log_never_holds_a_token_shaped_value(tmp_path, tool, tool_input):
    log = tmp_path / "gate.log"
    payload = {"session_id": "s", "hook_event_name": "PreToolUse", "cwd": str(REPO),
               "permission_mode": "default", "tool_name": tool, "tool_input": tool_input}
    r = subprocess.run(["sh", "-c", _gate_hook()["command"]], input=json.dumps(payload),
                       capture_output=True, text=True, cwd=str(REPO),
                       env={**os.environ, "CLAUDE_PROJECT_DIR": str(REPO), "TESS_GATE_LOG": str(log)})
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    text = log.read_text(encoding="utf-8")
    entry = json.loads(text.splitlines()[-1])
    assert entry["decision"] == "deny" and entry["session_id"] == "s" and entry["turn_id"] is None
    assert _TOKEN not in text and "Q7Q7Q7Q7Q7Q7Q7Q7" not in text, text
    assert "[REDACTED]" in text, text
