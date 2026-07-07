"""
Headless / no-subagent-available exception for `dispatch-guard.sh`
(Proving Ground finding, proving-ground/reports/2026-07-07.md, Ada,
2026-07-07).

Rule Zero ("always dispatch, never execute solo") presupposes a caller
that HOLDS the Agent/Task tool — the real Tess orchestrator. In a headless
single-agent execution context (a `claude -p` worker, `codex exec`, or any
harness with no subagent-dispatch capability), the hook's "stop and
dispatch" warning fires on every task-completing Bash/Edit/Write call with
no valid corrective action available — the benchmark measured this as a
3.1-3.2x cost/latency overhead and a reproducible fabrication regression.

These tests exercise the REAL bash script via subprocess (the same
PreToolUse JSON-on-stdin protocol Claude Code uses), not a reimplementation,
so a regression in the actual shipped hook is what gets caught:

  * default (no flag set): warn-mode behavior is BYTE-FOR-BYTE unchanged —
    this is the real Tess orchestrator's path and must never regress.
  * TESS_HEADLESS=1 or the alias TESS_NO_SUBAGENTS=1: the hook becomes a
    pure no-op (exit 0, no systemMessage) for every case that would
    otherwise warn.
  * the flag is presence-based, not boolean-parsed (documented quirk: the
    string "0" still counts as "set") — pinned here so nobody "fixes" it
    without noticing it's an intentional, tested contract.
  * the two shipped copies (.claude/hooks/ live mirror + .tess/core/hooks/
    core master) stay byte-identical.

A pre-existing dispatch-in-flight lock (LOCK_DIR="/tmp/tess-dispatch-locks",
hardcoded in the hook, shared with the running host) is NOT touched or
asserted on by these tests — mutating a real, shared /tmp path from a test
suite is unsafe on a machine that may have a genuine dispatch in flight.
That suppression path is unchanged by this fix (the headless check runs
strictly BEFORE it) and is exercised structurally by reading the script's
source below instead of by mutating shared state.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE_HOOK = REPO_ROOT / ".claude" / "hooks" / "dispatch-guard.sh"
CORE_HOOK = REPO_ROOT / ".tess" / "core" / "hooks" / "dispatch-guard.sh"

HAS_BASH = shutil.which("bash") is not None
HAS_JQ = shutil.which("jq") is not None
pytestmark = pytest.mark.skipif(
    not (HAS_BASH and HAS_JQ), reason="bash and jq required to exercise the real hook"
)


def _run_hook(payload: dict, *, hook_path: Path = LIVE_HOOK,
              project_dir: Path | None = None, extra_env: dict | None = None):
    """Invoke the real hook exactly as Claude Code's PreToolUse protocol
    does: the tool-call JSON on stdin, CLAUDE_PROJECT_DIR in the env."""
    env = dict(os.environ)
    # Start from a clean slate: neither flag set unless the test opts in.
    env.pop("TESS_HEADLESS", None)
    env.pop("TESS_NO_SUBAGENTS", None)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir if project_dir is not None else REPO_ROOT)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(hook_path)],
        input=json.dumps(payload),
        capture_output=True, text=True, env=env,
    )


def _bash_call(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _edit_call(file_path: str) -> dict:
    return {"tool_name": "Edit", "tool_input": {"file_path": file_path}}


# ---------------------------------------------------------------------------
# Baseline: default behavior (no flag) is unchanged — the real Tess
# orchestrator's path. These must keep warning exactly as before the fix.
# ---------------------------------------------------------------------------


def test_default_warns_on_solo_bash_outside_safe_set():
    r = _run_hook(_bash_call("npm install"))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert "RULE ZERO WARNING" in out["systemMessage"]
    assert "npm install" in out["systemMessage"]


def test_default_warns_on_solo_edit_outside_safe_set(tmp_path):
    target = tmp_path / "some_random_file.py"
    r = _run_hook(_edit_call(str(target)), project_dir=tmp_path)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert "RULE ZERO WARNING" in out["systemMessage"]


def test_default_stays_silent_on_doctrine_safe_edit(tmp_path):
    """Regression guard: the pre-existing Rule-Zero safe list must be
    completely unaffected by the headless fix."""
    conductor = tmp_path / "conductor"
    conductor.mkdir()
    target = conductor / "doctrine.md"
    r = _run_hook(_edit_call(str(target)), project_dir=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


def test_default_stays_silent_on_trivial_bash():
    r = _run_hook(_bash_call("echo hello"))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


# ---------------------------------------------------------------------------
# The fix: TESS_HEADLESS / TESS_NO_SUBAGENTS silence the warning entirely.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["TESS_HEADLESS", "TESS_NO_SUBAGENTS"])
def test_headless_flag_silences_bash_warning(flag):
    r = _run_hook(_bash_call("npm install"), extra_env={flag: "1"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "", (
        f"{flag}=1 should fully suppress the warning, got: {r.stdout!r}"
    )


@pytest.mark.parametrize("flag", ["TESS_HEADLESS", "TESS_NO_SUBAGENTS"])
def test_headless_flag_silences_edit_warning(flag, tmp_path):
    target = tmp_path / "some_random_file.py"
    r = _run_hook(_edit_call(str(target)), project_dir=tmp_path, extra_env={flag: "1"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


def test_headless_flag_is_presence_based_not_boolean_parsed():
    """Documented quirk, intentionally pinned: the string "0" still counts
    as 'set' (bash `[ -n ... ]` is a presence check, not a truthy-value
    parse) — only unset/empty disables headless mode."""
    r = _run_hook(_bash_call("npm install"), extra_env={"TESS_HEADLESS": "0"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "", "TESS_HEADLESS=0 (non-empty) must still suppress the warning"


def test_headless_flag_empty_string_does_not_suppress():
    """The one way to leave headless mode OFF: unset, or explicitly empty."""
    r = _run_hook(_bash_call("npm install"), extra_env={"TESS_HEADLESS": ""})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert "RULE ZERO WARNING" in out["systemMessage"], (
        "TESS_HEADLESS='' (empty) must NOT suppress the warning"
    )


def test_headless_flag_never_blocks_the_tool_call():
    """Warn-mode invariant preserved: exit code is always 0, headless or not."""
    for extra_env in (None, {"TESS_HEADLESS": "1"}, {"TESS_NO_SUBAGENTS": "1"}):
        r = _run_hook(_bash_call("rm -rf /some/path"), extra_env=extra_env)
        assert r.returncode == 0, f"hook must never block (env={extra_env}): {r.stderr}"


# ---------------------------------------------------------------------------
# Both shipped copies (live mirror + core master) must be identical and
# individually exercise the same headless behavior.
# ---------------------------------------------------------------------------


def test_live_and_core_copies_are_byte_identical():
    assert LIVE_HOOK.read_bytes() == CORE_HOOK.read_bytes(), (
        "the .claude/hooks/ live mirror and .tess/core/hooks/ core master "
        "have drifted — both must ship the same headless fix"
    )


def test_core_copy_also_honors_the_headless_flag():
    r = _run_hook(_bash_call("npm install"), hook_path=CORE_HOOK, extra_env={"TESS_HEADLESS": "1"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Structural: the headless check must run BEFORE the dispatch-lock check,
# so it wins even if a lock happens to be present, and stdin is always
# consumed (protocol contract) regardless of which path is taken.
# ---------------------------------------------------------------------------


def test_headless_check_precedes_dispatch_lock_check_in_source():
    text = LIVE_HOOK.read_text(encoding="utf-8")
    # The CODE check (the `if [ -n "${TESS_HEADLESS...` line), not the first
    # mention of the token, which appears earlier in the header comment.
    headless_code_idx = text.index('if [ -n "${TESS_HEADLESS:-}" ]')
    lock_check_idx = text.index('find "$LOCK_DIR"')
    assert headless_code_idx < lock_check_idx, (
        "the TESS_HEADLESS/TESS_NO_SUBAGENTS check must be evaluated before "
        "the dispatch-lock check so it wins unconditionally in a headless "
        "context (which cannot have a valid dispatch lock in the first place)"
    )


def test_stdin_is_always_consumed_before_any_check():
    text = LIVE_HOOK.read_text(encoding="utf-8")
    input_read_idx = text.index('input="$(cat)"')
    headless_code_idx = text.index('if [ -n "${TESS_HEADLESS:-}" ]')
    assert input_read_idx < headless_code_idx, (
        "stdin must be fully read before the headless short-circuit, per "
        "the PreToolUse protocol contract"
    )
