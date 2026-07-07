"""Subprocess wrapper around `claude -p ... --output-format json`.

Verified interactively against a real `claude` 2.1.201 install while
building this harness (see `proving-ground/README.md` "Verified against a
real `claude -p` invocation"):

- `--output-format json` returns a JSON ARRAY of stream events; the last
  event with `"type": "result"` carries `total_cost_usd`, `is_error`,
  `result` (final text), `num_turns`, `duration_ms`, `session_id`.
- `--model` accepts an alias (`haiku`, `opus`, `sonnet`, ...) or a full
  model name, and resolves it into that same `result` event's context.
- `--bare` (true harness isolation: no hooks, no plugin sync, no CLAUDE.md
  auto-discovery) is authenticated ONLY via `ANTHROPIC_API_KEY` or
  `apiKeyHelper` — it explicitly refuses OAuth/keychain auth. Confirmed
  live: without `ANTHROPIC_API_KEY` set, a `--bare` call fails instantly
  with `"error":"authentication_failed"` and `"total_cost_usd":0` (zero
  spend, fails before any request goes out) — see `bare_mode_available()`.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from pg_lib.scaffolds import BARE, TESS_OS

DEFAULT_PERMISSION_MODE = "bypassPermissions"


@dataclass
class ClaudeRunResult:
    ok: bool                 # the subprocess ran and its output parsed as expected
    is_error: bool            # the CLAUDE SESSION reported an error (auth failure, budget cutoff, etc.)
    result_text: str
    cost_usd: float
    num_turns: int
    duration_ms: int
    session_id: Optional[str]
    raw_events: List[Dict[str, Any]] = field(default_factory=list)
    stderr: str = ""
    timed_out: bool = False


def bare_mode_available() -> bool:
    """`--bare` mandates ANTHROPIC_API_KEY (or an apiKeyHelper, out of scope
    for this harness) — OAuth/keychain auth is explicitly never read in
    that mode. Cheap, local, zero-cost precondition check."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def run_claude(
    prompt: str,
    cwd: Path,
    model: str,
    scaffold: str,
    max_budget_usd: float,
    timeout_seconds: int,
    strict_bare: bool = True,
    permission_mode: str = DEFAULT_PERMISSION_MODE,
) -> ClaudeRunResult:
    """Invoke one headless `claude -p` turn and parse its result.

    `scaffold == "bare"` maps to the `--bare` CLI flag when `strict_bare`
    is True (the methodologically clean condition). If `strict_bare` is
    False, the bare condition is approximated instead by omitting scaffold
    files and passing `--setting-sources project` — cheaper to run without
    an API key, but NOT a pure baseline (it still inherits the operator's
    installed plugins/MCP servers/tool list). Every trial produced this
    way must be marked `impure_bare` in the report — see `run.py`.
    """
    command = _build_command(prompt, model, scaffold, max_budget_usd, permission_mode, strict_bare)
    env = _build_env(scaffold)
    try:
        proc = subprocess.run(
            command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout_seconds, env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return ClaudeRunResult(
            ok=False, is_error=True, result_text="", cost_usd=0.0, num_turns=0,
            duration_ms=timeout_seconds * 1000, session_id=None,
            stderr=f"timed out after {timeout_seconds}s: {exc}", timed_out=True,
        )
    return _parse_output(proc.stdout, proc.stderr, proc.returncode)


def _build_env(scaffold: str) -> Dict[str, str]:
    """The subprocess env for one `claude -p` cell invocation.

    `tess-os` cells mount `.claude/hooks/dispatch-guard.sh` (see
    `pg_lib/scaffolds.py`), which fires a "RULE ZERO — stop and dispatch"
    warning on every non-safe-listed Bash/Edit/Write call. That warning
    presupposes a caller holding the Agent/Task tool; a headless `claude -p`
    trial in this harness structurally has nothing to dispatch to, so the
    warning was pure friction (see `proving-ground/reports/2026-07-07.md`,
    and the hook fix in `.claude/hooks/dispatch-guard.sh` /
    `.tess/core/hooks/dispatch-guard.sh`). Setting `TESS_HEADLESS=1` makes
    the hook a silent no-op for that cell.

    `bare` cells never mount `.claude/` at all (`scaffold_source_paths`
    returns `[]` for `bare`), so the variable would be inert there anyway —
    but it is deliberately withheld from `bare`'s env regardless, so `bare`
    stays a clean, unmodified-environment baseline and this fix cannot be
    read as touching both arms of the comparison.
    """
    env = dict(os.environ)
    if scaffold == TESS_OS:
        env["TESS_HEADLESS"] = "1"
    return env


def _build_command(
    prompt: str, model: str, scaffold: str, max_budget_usd: float, permission_mode: str, strict_bare: bool
) -> List[str]:
    command = [
        "claude", "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--permission-mode", permission_mode,
        "--max-budget-usd", str(max_budget_usd),
        "--no-session-persistence",
        # Safety/methodology fix found while verifying the fair re-run
        # (2026-07-07): this operator's environment has REAL Agent/Task-tool
        # dispatch infrastructure wired up (unlike the assumption baked into
        # this harness's own docs/README, "this headless single-shot claude
        # -p harness has no subagent to dispatch to"). A direct probe with
        # the tess-os scaffold mounted showed the model actually invoking the
        # Agent tool and a genuine nested agent spawning, running, and
        # completing in the background — outside this trial's cost/timeout
        # accounting and with access to whatever MCP servers/credentials the
        # child session resolves. Disallowed for BOTH scaffolds (not just
        # tess-os) so the safety net is symmetric and neither arm of the
        # comparison gets an advantage from it — bare tasks never need to
        # dispatch either. Verified: with this flag set, the tool call is
        # rejected ("No such tool available: Agent... not enabled in this
        # context") and the model falls back to executing directly, which is
        # the behavior the harness's cost/pass-rate model already assumes.
        "--disallowedTools", "Agent,Task",
    ]
    if scaffold == BARE and strict_bare:
        command.append("--bare")
    else:
        command += ["--setting-sources", "project"]
    return command


def _parse_output(stdout: str, stderr: str, returncode: int) -> ClaudeRunResult:
    if not stdout.strip():
        return ClaudeRunResult(
            ok=False, is_error=True, result_text="", cost_usd=0.0, num_turns=0,
            duration_ms=0, session_id=None, stderr=stderr or "(empty stdout)",
        )
    try:
        events = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return ClaudeRunResult(
            ok=False, is_error=True, result_text=stdout[-2000:], cost_usd=0.0, num_turns=0,
            duration_ms=0, session_id=None, stderr=f"{stderr}\nJSON parse error: {exc}",
        )

    result_event = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if result_event is None:
        return ClaudeRunResult(
            ok=False, is_error=True, result_text="", cost_usd=0.0, num_turns=0,
            duration_ms=0, session_id=None, raw_events=events,
            stderr=f"{stderr}\nno 'result' event in output stream",
        )

    return ClaudeRunResult(
        ok=True,
        is_error=bool(result_event.get("is_error", returncode != 0)),
        result_text=str(result_event.get("result", "")),
        cost_usd=float(result_event.get("total_cost_usd") or 0.0),
        num_turns=int(result_event.get("num_turns") or 0),
        duration_ms=int(result_event.get("duration_ms") or 0),
        session_id=result_event.get("session_id"),
        raw_events=events,
        stderr=stderr,
    )
