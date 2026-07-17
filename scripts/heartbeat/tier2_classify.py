"""Tier-2 — the ONLY place this runner spends a token.

Invoked in exactly two situations:
  1. A NEW stall event (a card just crossed its own `stall_after` for the
     first time this stall episode) — needs judgment to pick the right
     `stall.reason` enum value and compose the right alert, not just a
     timestamp comparison.
  2. The daily recompile — cross-referencing loosely-matching text (an
     optional memory-project glob, an optional wiki-log tail, an optional
     org-wide repo scan — all operator-configured, see config.py) against
     the registry is a fuzzy-matching/reading-comprehension task, not a
     string match.

Everything else (the mechanical moving-path refresh, and repeat-escalation
reminders for an *already-classified* stall) is handled without a model in
run.py/escalation.py — those are pure arithmetic on timestamps a human
already gave meaning to.

★ SAFETY-CRITICAL — this call is given ZERO tools, verified fail-closed, not
merely "the tools we thought to name". This is the load-bearing part of the
whole daemon and MUST NOT be weakened without re-running the live tests
this module's flag set was built from:

  - `--tools ""` (NOT `--disallowed-tools`/`--allowed-tools` alone — both
    were empirically tested against a real `claude` CLI (2.1.208) and do
    NOT achieve zero tools: a stale `--disallowed-tools` denylist leaves
    every tool it forgot to name (Task, Workflow, SendMessage,
    ScheduleWakeup, CronCreate/CronDelete, RemoteTrigger, ToolSearch, ...)
    reachable, and passing an empty value to `--allowed-tools` alone was
    observed, live, to be silently ignored — the init event still showed
    the full default toolset. `--tools` is a distinct, separate flag
    ("available tools from the built-in set") and `--tools ""` is the flag
    verified, live, to produce `"tools": []` in the
    `claude -p --output-format stream-json` init event. `--allowed-tools ""`
    is kept alongside it as defense-in-depth (harmless, but proven NOT
    sufficient alone), never relied on by itself.
  - `--strict-mcp-config --mcp-config <empty_mcp_config.json>` (committed
    next to this file, `{"mcpServers": {}}`) — proven necessary, live: with
    NO mcp flags at all, `--tools ""` alone still connects every MCP server
    from the operator's own global config and exposes every one of their
    tools in the init event, regardless of the `--tools`/`--allowed-tools`
    value. The tool allowlist and the MCP server list are independent
    gates — closing one does not close the other. Live-verified during this
    port: `claude -p ... --tools "" --allowed-tools "" --strict-mcp-config
    --mcp-config scripts/heartbeat/empty_mcp_config.json --output-format
    stream-json` produces an init event with `"tools":[]` AND
    `"mcp_servers":[]` — the exact proof this module's safety claim rests on.
  - `--bare` was tested and NOT used: it reduces (not zeroes) the default
    toolset on its own and, more importantly, forces API-key-only auth
    ("OAuth and keychain are never read") — in an environment using
    subscription OAuth with no dedicated API key provisioned for this
    daemon, `--bare` calls fail outright ("Not logged in · Please run
    /login"), which would silently disable Tier-2 entirely rather than
    isolate it. Do not add `--bare` without first provisioning a dedicated
    API key for this daemon — a separate, explicit decision this module
    does not make.

All context this call needs is embedded directly in the prompt; with a
zero-length tool list and zero MCP servers it can only reason and answer in
text — it cannot touch the filesystem, cannot dispatch an agent or workflow,
cannot notify anyone directly, cannot reach any MCP server, and cannot do
the "actual resume work" this runner reserves for a real dispatched
agent/session. The parent process (this script) is the only thing that
ever writes a card or sends a notification, based on the JSON this call
returns.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config as config_mod

STALL_REASON_ENUM = [
    "awaiting-decision",
    "blocked-external",
    "attention-shift",
    "error",
    "frontier-reached",
]

# Committed empty MCP config — ships next to this file so it's resolvable
# regardless of the scheduler's cwd, and so "zero MCP servers" holds even if
# the operator's own global config (~/.claude.json etc.) changes.
_EMPTY_MCP_CONFIG = Path(__file__).resolve().parent / "empty_mcp_config.json"


def _zero_tool_flags() -> List[str]:
    """Verified fail-closed flag set — see module docstring for the live
    testing that ruled out `--disallowed-tools` (stale denylist) and bare
    `--allowed-tools ""` (silently ignored, empirically confirmed a no-op).
    `--tools ""` is the flag verified to actually zero the init event's
    `tools` list; `--allowed-tools ""` rides along as harmless
    defense-in-depth, never trusted alone."""
    return [
        "--tools", "",
        "--allowed-tools", "",
        "--strict-mcp-config",
        "--mcp-config", str(_EMPTY_MCP_CONFIG),
    ]


_CLASSIFY_SYSTEM_NOTE = f"""You are a narrow, tool-less classification call invoked by an unattended
memory-continuity heartbeat daemon (not an interactive session). You have NO tools —
you cannot read files, run commands, or dispatch anything. Everything you need is in
this prompt. Do not attempt to call a tool.

Task: classify why ONE project card silently crossed its own stall_after threshold with
no new evidence, and decide what the daemon should do about it. Reason must be exactly
one of: {", ".join(STALL_REASON_ENUM)}.

Reply with ONLY a single JSON object (no prose, no markdown fences) with exactly these keys:
  "reason": one of the enum values above
  "rationale": one sentence, grounded only in the card content/evidence given below
  "notify_message": the exact plain-text message to send the operator via their configured
      notification channel (plain ASCII prose, no Markdown special characters that could
      break a channel's own escaping), OR null if reason is "blocked-external" (no alarm
      needed — expected to be quiet)
  "queue_resume": true if the card's own `resume:` recipe should be queued at the top of
      registry.md for the next session to act on, else false

Do not invent facts not present in the card or evidence below. If the evidence is
ambiguous, say so in rationale and default to "attention-shift" (the safe/visible choice)
rather than guessing "blocked-external" (which suppresses the alarm)."""


@dataclass
class ClassifyResult:
    reason: str
    rationale: str
    notify_message: Optional[str]
    queue_resume: bool
    raw: str
    mocked: bool


def _build_prompt(card_text: str, evidence_proof: str, days_silent: float) -> str:
    return (
        f"{_CLASSIFY_SYSTEM_NOTE}\n\n"
        f"--- CARD (memory/projects/*.md, verbatim) ---\n{card_text}\n\n"
        f"--- FRESH EVIDENCE PROBE (just run, $0, no LLM) ---\n{evidence_proof}\n\n"
        f"--- ELAPSED ---\n{days_silent:.1f} days with no evidence newer than the card's "
        f"recorded last_activity, past its own stall_after threshold.\n"
    )


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    return json.loads(text)


def _result_text_from_envelope(envelope: Any) -> str:
    """`claude -p --output-format json` has been observed, live, to return a
    JSON array of turn/event objects rather than the single result dict the
    `--output-format` help text ("json (single result)") implies. Handle
    both shapes rather than trust one; smoke-test this path for real once at
    first activation before trusting it fully unattended (see
    scripts/heartbeat/README.md)."""
    if isinstance(envelope, dict):
        return envelope.get("result", envelope.get("output", json.dumps(envelope)))
    if isinstance(envelope, list):
        for item in reversed(envelope):
            if isinstance(item, dict) and item.get("type") == "result" and "result" in item:
                return item["result"]
        for item in reversed(envelope):
            if isinstance(item, dict) and "result" in item:
                return item["result"]
        # last resort: hope the final list entry carries usable text
        return json.dumps(envelope[-1]) if envelope else "{}"
    return str(envelope)


def classify_stall(
    card_text: str,
    evidence_proof: str,
    days_silent: float,
    existing_reason: Optional[str],
    dry_run: bool,
    cfg: Optional[config_mod.HeartbeatConfig] = None,
) -> ClassifyResult:
    cfg = cfg or config_mod.load()
    prompt = _build_prompt(card_text, evidence_proof, days_silent)

    if dry_run:
        # No spawn, no token spent. Best-effort stand-in so the dry-run can
        # still validate the downstream write/alarm shape: reuse the card's
        # own already-recorded reason if present, else the conservative
        # default the real prompt itself specifies.
        reason = existing_reason if existing_reason in STALL_REASON_ENUM else "attention-shift"
        return ClassifyResult(
            reason=reason,
            rationale=(
                "DRY-RUN: no claude -p spawned. Stand-in classification reuses the card's "
                "own existing stall.reason for output-shape validation only — not a real "
                "model judgment."
            ),
            notify_message=(
                None if reason == "blocked-external"
                else f"[DRY-RUN] would alarm: stalled {days_silent:.1f}d, reason={reason}"
            ),
            queue_resume=reason != "blocked-external",
            raw="<dry-run: not invoked>",
            mocked=True,
        )

    cmd = [
        "claude", "-p", prompt,
        "--model", cfg.model,
        "--output-format", "json",
        *_zero_tool_flags(),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"claude -p classify failed ({result.returncode}): {result.stderr[:500]}")

    envelope = json.loads(result.stdout)
    result_text = _result_text_from_envelope(envelope)
    parsed = _extract_json(result_text)

    reason = parsed.get("reason")
    if reason not in STALL_REASON_ENUM:
        raise ValueError(f"claude -p returned invalid reason enum value: {reason!r}")

    return ClassifyResult(
        reason=reason,
        rationale=parsed.get("rationale", ""),
        notify_message=parsed.get("notify_message"),
        queue_resume=bool(parsed.get("queue_resume", False)),
        raw=result_text,
        mocked=False,
    )


def daily_recompile_synthesis(
    registry_snapshot: str,
    memory_project_titles: List[str],
    wiki_log_tail: str,
    org_repo_scan: List[str],
    dry_run: bool,
    cfg: Optional[config_mod.HeartbeatConfig] = None,
) -> Dict[str, Any]:
    """The daily recompile's fuzzy cross-reference step: flag candidate
    UNREGISTERED open work — never auto-create a card (that's a judgment
    call for a human/agent session), only surface candidates in the digest.
    """
    cfg = cfg or config_mod.load()
    prompt = (
        "You are the memory-continuity heartbeat daemon's daily recompile call. No tools "
        "available — reason over the text below only. Cross-reference the current "
        "registry against any configured memory-project titles, wiki-log tail, and "
        "org-wide repo scan. Reply with ONLY a JSON object: "
        '{"unregistered_candidates": [{"name": str, "evidence": str}], '
        '"stale_card_suspects": [{"slug": str, "why": str}]}. '
        "unregistered_candidates = things that look like live open work with no "
        "matching memory/projects/*.md card. stale_card_suspects = cards whose "
        "narrative looks contradicted by the registry/evidence given (e.g. a "
        "branch the card says is pending review that other evidence already shows "
        "merged). Do not invent entries not supported by the text below.\n\n"
        f"--- REGISTRY SNAPSHOT ---\n{registry_snapshot}\n\n"
        f"--- CONFIGURED MEMORY-PROJECT TITLES (may be empty if not configured) ---\n"
        f"{chr(10).join(memory_project_titles)}\n\n"
        f"--- WIKI LOG TAIL (may be empty if not configured) ---\n{wiki_log_tail}\n\n"
        f"--- ORG REPO SCAN (may be empty if not configured) ---\n{chr(10).join(org_repo_scan)}\n"
    )

    if dry_run:
        return {
            "unregistered_candidates": [],
            "stale_card_suspects": [],
            "_dry_run_note": "no claude -p spawned; daily recompile synthesis skipped in dry-run",
        }

    cmd = [
        "claude", "-p", prompt,
        "--model", cfg.model,
        "--output-format", "json",
        *_zero_tool_flags(),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"claude -p daily recompile failed ({result.returncode}): {result.stderr[:500]}")
    envelope = json.loads(result.stdout)
    result_text = _result_text_from_envelope(envelope)
    return _extract_json(result_text)
