"""Safety-critical tests for scripts/heartbeat/tier2_classify.py.

This is the one place the heartbeat daemon spawns a model call, and the one
place a regression would be dangerous (a daemon spawning `claude -p` with a
real tool surface, reasoning over untrusted commit/PR/wiki text). These
tests assert the exact fail-closed flag set is constructed correctly and
that the committed empty MCP config is genuinely empty — WITHOUT spawning a
real `claude` process in ordinary CI (no `claude` CLI, no auth, in a stock
GitHub Actions runner).

A separate, opt-in live smoke test (`test_live_zero_tools_smoke_test`) is
included for local verification when the `claude` CLI is available and
authenticated — it is skipped automatically otherwise so CI never depends
on it. See docs/memory-continuity.md's "Safety design" section for the
smoke-test proof this port's live run produced.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from heartbeat import tier2_classify  # noqa: E402

HAS_CLAUDE_CLI = shutil.which("claude") is not None


def test_empty_mcp_config_is_committed_and_genuinely_empty():
    path = tier2_classify._EMPTY_MCP_CONFIG
    assert path.exists(), "empty_mcp_config.json must ship committed next to tier2_classify.py"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"mcpServers": {}}


def test_zero_tool_flags_contains_tools_empty_string():
    flags = tier2_classify._zero_tool_flags()
    assert "--tools" in flags
    idx = flags.index("--tools")
    assert flags[idx + 1] == ""


def test_zero_tool_flags_does_not_rely_on_disallowed_tools_alone():
    """--disallowed-tools was empirically proven insufficient (a stale
    denylist leaves every un-named tool reachable) — must not appear as the
    ONLY gating mechanism. --tools "" must be present."""
    flags = tier2_classify._zero_tool_flags()
    assert "--disallowed-tools" not in flags
    assert "--tools" in flags


def test_zero_tool_flags_includes_strict_mcp_config_and_empty_config_path():
    flags = tier2_classify._zero_tool_flags()
    assert "--strict-mcp-config" in flags
    assert "--mcp-config" in flags
    idx = flags.index("--mcp-config")
    mcp_path = Path(flags[idx + 1])
    assert mcp_path.exists()
    assert json.loads(mcp_path.read_text(encoding="utf-8")) == {"mcpServers": {}}


def test_zero_tool_flags_keeps_allowed_tools_empty_as_defense_in_depth():
    flags = tier2_classify._zero_tool_flags()
    assert "--allowed-tools" in flags
    idx = flags.index("--allowed-tools")
    assert flags[idx + 1] == ""


def test_classify_stall_dry_run_never_spawns_a_process(monkeypatch):
    """dry_run=True must produce a stand-in result without calling
    subprocess.run at all — assert this by making subprocess.run raise if
    invoked, proving the dry-run path never reaches it."""
    def _boom(*args, **kwargs):
        raise AssertionError("subprocess.run must not be called in dry_run mode")

    monkeypatch.setattr(subprocess, "run", _boom)
    result = tier2_classify.classify_stall(
        card_text="---\nid: x\n---\nbody",
        evidence_proof="no evidence",
        days_silent=10.0,
        existing_reason=None,
        dry_run=True,
    )
    assert result.mocked is True
    assert result.reason in tier2_classify.STALL_REASON_ENUM


def test_classify_stall_real_invocation_uses_zero_tool_flags(monkeypatch):
    """Without spawning a real process, assert that the argv passed to
    subprocess.run (when dry_run=False) contains the exact fail-closed flag
    set — this is the load-bearing assertion for the whole module."""
    captured = {}

    class _FakeCompleted:
        returncode = 0
        stdout = json.dumps({"result": json.dumps({
            "reason": "attention-shift",
            "rationale": "test",
            "notify_message": "test message",
            "queue_resume": False,
        })})
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = tier2_classify.classify_stall(
        card_text="card text", evidence_proof="evidence", days_silent=8.0,
        existing_reason=None, dry_run=False,
    )
    assert result.reason == "attention-shift"
    cmd = captured["cmd"]
    assert "--tools" in cmd and cmd[cmd.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in cmd
    assert "--mcp-config" in cmd
    assert "--allowed-tools" in cmd and cmd[cmd.index("--allowed-tools") + 1] == ""
    assert "--disallowed-tools" not in cmd
    assert "--bare" not in cmd


@pytest.mark.skipif(not HAS_CLAUDE_CLI, reason="claude CLI not available in this environment")
def test_live_zero_tools_smoke_test():
    """Opt-in live proof (only runs where `claude` is actually installed):
    invoke the real CLI with the exact flag set this module uses and assert
    the stream-json init event reports zero tools AND zero MCP servers. Uses
    an isolated $HOME with no other settings so this test is never
    confounded by an operator's own global hooks/config."""
    with tempfile.TemporaryDirectory() as home:
        home_path = Path(home)
        (home_path / ".claude").mkdir(parents=True, exist_ok=True)
        (home_path / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
        env = {**os.environ, "HOME": str(home_path)}
        cmd = [
            "claude", "-p", "reply with just the word OK",
            "--model", "sonnet",
            "--output-format", "stream-json",
            "--verbose",
            *tier2_classify._zero_tool_flags(),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env, check=False)
        init_events = [
            json.loads(line) for line in result.stdout.splitlines()
            if '"subtype":"init"' in line
        ]
        assert init_events, f"no init event observed in stream-json output: {result.stdout[:500]}"
        init = init_events[0]
        assert init["tools"] == []
        assert init["mcp_servers"] == []
