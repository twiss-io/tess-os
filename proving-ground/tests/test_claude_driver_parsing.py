"""Unit tests for pg_lib.claude_driver's output parsing, using canned
`claude -p --output-format json` payloads captured from real, live
invocations made while building this harness (see
`proving-ground/README.md` "Verified against a real claude -p invocation")
— no network call, no `claude` subprocess, $0.
"""
from __future__ import annotations

import json

from pg_lib.claude_driver import _build_command, _parse_output
from pg_lib.scaffolds import BARE, TESS_OS

# Captured verbatim (trimmed to the fields _parse_output reads) from a real
# `claude -p "..." --bare --output-format json` call with no
# ANTHROPIC_API_KEY set.
BARE_AUTH_FAILURE_EVENTS = [
    {"type": "system", "subtype": "init", "model": "<synthetic>"},
    {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "Not logged in · Please run /login"}]},
        "error": "authentication_failed",
    },
    {
        "type": "result", "subtype": "success", "is_error": True,
        "result": "Not logged in · Please run /login",
        "session_id": "c25e021f-e3ee-4d96-aab3-3852575d29b7",
        "total_cost_usd": 0, "num_turns": 1, "duration_ms": 37,
    },
]

# Captured verbatim (trimmed) from a real successful `claude -p
# "Reply with exactly the single word: OK" --model haiku --output-format
# json --setting-sources project` call.
SUCCESSFUL_HAIKU_EVENTS = [
    {"type": "system", "subtype": "init", "model": "claude-haiku-4-5-20251001"},
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "OK"}]}},
    {
        "type": "result", "subtype": "success", "is_error": False,
        "result": "OK", "session_id": "6a4b8835-3d65-45d3-b44e-5ac3d05c912f",
        "total_cost_usd": 0.0165499, "num_turns": 1, "duration_ms": 2073,
    },
]


def test_parses_a_real_bare_auth_failure_as_zero_cost_error():
    result = _parse_output(json.dumps(BARE_AUTH_FAILURE_EVENTS), "", 1)
    assert result.ok is True  # the subprocess/JSON parsed fine...
    assert result.is_error is True  # ...but the CLAUDE SESSION reported an error
    assert result.cost_usd == 0.0
    assert "Not logged in" in result.result_text


def test_parses_a_real_successful_haiku_result():
    result = _parse_output(json.dumps(SUCCESSFUL_HAIKU_EVENTS), "", 0)
    assert result.ok is True
    assert result.is_error is False
    assert result.result_text == "OK"
    assert result.cost_usd == 0.0165499
    assert result.session_id == "6a4b8835-3d65-45d3-b44e-5ac3d05c912f"


def test_empty_stdout_is_a_harness_level_error_not_a_crash():
    result = _parse_output("", "some stderr noise", 1)
    assert result.ok is False
    assert result.is_error is True


def test_malformed_json_stdout_is_a_harness_level_error_not_a_crash():
    result = _parse_output("{not valid json", "", 0)
    assert result.ok is False
    assert result.is_error is True


def test_missing_result_event_is_a_harness_level_error_not_a_crash():
    events = [{"type": "system", "subtype": "init"}]
    result = _parse_output(json.dumps(events), "", 0)
    assert result.ok is False
    assert result.is_error is True


# --- Regression lock: every `claude -p` invocation this harness makes must
# disallow Agent/Task, permanently, for BOTH scaffolds. See the fair-run
# report (`reports/2026-07-07-fair.md`) for why: a real Agent/Task-tool
# dispatch was observed to actually fire from a headless `claude -p` call
# with the `tess-os` scaffold mounted, spawning a genuine nested background
# subagent outside this harness's cost/timeout accounting. This was fixed
# ad hoc during that run and then upstreamed into `_build_command` as an
# unconditional flag — these tests exist so a future edit that narrows the
# flag to one scaffold, or drops it, fails CI instead of silently
# reintroducing the safety hole.

def test_bare_command_always_disallows_agent_and_task_tools():
    command = _build_command("do the task", "haiku", BARE, 1.0, "bypassPermissions", True)
    assert "--disallowedTools" in command
    idx = command.index("--disallowedTools")
    assert command[idx + 1] == "Agent,Task"


def test_tess_os_command_always_disallows_agent_and_task_tools():
    command = _build_command("do the task", "haiku", TESS_OS, 1.0, "bypassPermissions", True)
    assert "--disallowedTools" in command
    idx = command.index("--disallowedTools")
    assert command[idx + 1] == "Agent,Task"


def test_disallowedTools_present_regardless_of_strict_bare_flag():
    # strict_bare only decides whether `--bare` vs `--setting-sources
    # project` is appended — it must never gate the safety flag.
    for strict_bare in (True, False):
        command = _build_command("x", "haiku", BARE, 1.0, "bypassPermissions", strict_bare)
        assert "Agent,Task" in command
