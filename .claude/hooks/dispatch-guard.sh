#!/usr/bin/env bash
# PreToolUse hook for Bash/Edit/Write — Rule Zero dispatch guard.
# WARN-MODE ONLY: this hook NEVER blocks a tool call. Every path exits 0 and
# never emits a permission decision — it only surfaces a systemMessage warning.
# Block-mode is explicitly NOT authorized (audit reform Decision 7, 2026-06-10).
#
# Design (audit reform S1/G1): hooks fire in ALL contexts including dispatched
# subagents (conductor/hook-testing-protocol.md). A dispatch-in-flight lock
# (set by task-lock-set.sh on PreToolUse-of-Agent/Task, cleared by
# task-lock-clear.sh on PostToolUse) suppresses the warning while any dispatch
# is running, so dispatched engineers never see false positives. When NO
# dispatch is in flight, direct Bash/Edit/Write outside the Rule-Zero safe set
# is, by definition, the main conductor session executing solo — warn.
#
# Safe set = reconciliation of CLAUDE.md Rule Zero + guardrails.md Rule 1:
# doctrine files (CLAUDE.md, conductor/*, agents/README.md, .claude/agents/*),
# project memory files, and trivial orchestration commands.
#
# HEADLESS / no-subagent-available exception (Proving Ground finding,
# proving-ground/reports/2026-07-07.md): Rule Zero ("always dispatch, never
# execute solo") presupposes a caller that HOLDS the Agent/Task tool — the
# real Tess orchestrator. A headless single-agent execution context (a
# `claude -p` worker, `codex exec`, or any harness with no subagent-dispatch
# capability at all) has structurally nothing to dispatch TO, so the warning
# is pure friction with no corrective action available to the model. The
# benchmark measured this: a 3.1-3.2x cost/latency overhead on every task,
# AND a reproducible fabrication regression (task 05-research-roster-facts,
# strong+tess-os failed all 3 attempts an unassisted strong+bare run passed
# cleanly) plausibly caused by the model re-litigating "should I be doing
# this myself" against a contextually-wrong warning instead of the task's
# actual instructions.
#
# When the CALLER/SCAFFOLD sets TESS_HEADLESS=1 (or the alias
# TESS_NO_SUBAGENTS=1 — either is sufficient) this hook becomes a pure
# no-op: it still consumes stdin (protocol contract — PreToolUse hooks are
# fed the tool-call JSON and must not leave it unread) but exits 0 before
# ANY other check, including the dispatch-lock check below, and NEVER emits
# a systemMessage. This is opt-in by the render target / harness, never
# inferred from process state — the real Tess orchestrator session never
# sets either variable, so its warn-mode behavior below is byte-for-byte
# unchanged. Presence-based, not boolean-parsed: ANY non-empty value
# (including the string "0") counts as set — unset or empty ("") is the
# only way to leave headless mode off. See conductor/hook-testing-protocol.md
# and this file's companion test, tests/test_dispatch_guard_headless.py.

LOCK_DIR="${TESS_LOCK_DIR:-/tmp/tess-dispatch-locks}"
TESS_ROOT="$CLAUDE_PROJECT_DIR"

input="$(cat)"

# Headless / no-subagent-available context — see header comment. Checked
# FIRST, ahead of the dispatch-lock check, since a headless harness cannot
# have a valid dispatch lock in the first place and this must win regardless.
if [ -n "${TESS_HEADLESS:-}" ] || [ -n "${TESS_NO_SUBAGENTS:-}" ]; then
  exit 0
fi

# Dispatch in flight -> key on THIS session's lock specifically (the hook
# input carries session_id, same field/sanitization task-lock-set.sh writes
# with), NOT "any *.lock in the shared dir". A lock belonging to a DIFFERENT
# concurrent Claude Code session must never suppress THIS session's own Rule
# Zero warning — that was the split-brain: with TESS_LOCK_DIR unset, every
# session shares /tmp/tess-dispatch-locks/, so session B executing solo
# stayed silently unwarned merely because session A had an unrelated
# dispatch in flight. A dispatched SUBAGENT's own tool calls correctly stay
# suppressed here because a subagent runs within its dispatching session's
# SAME session_id (hooks "fire in ALL contexts including dispatched
# subagents" per conductor/hook-testing-protocol.md — there is no separate
# subagent session_id to key on). The freshness window MUST match
# STALE_MIN=240 in task-lock-set.sh / task-lock-clear.sh, which prune and
# ignore locks >4h old; a wider window would keep suppressing the warning
# for up to a day on a leaked lock from a crashed session.
sid="$(printf '%s' "$input" | jq -r '.session_id // "global"' 2>/dev/null)" || sid="global"
[ -n "$sid" ] && [ "$sid" != "null" ] || sid="global"
sid="$(printf '%s' "$sid" | tr -cd 'A-Za-z0-9._-')"
[ -n "$sid" ] || sid="global"
lock="$LOCK_DIR/$sid.lock"
if [ -f "$lock" ] && find "$lock" -mmin -240 2>/dev/null | grep -q .; then
  exit 0
fi

tool="$(printf '%s' "$input" | jq -r '.tool_name // ""' 2>/dev/null)" || tool=""

warn=0
detail=""

case "$tool" in
  Edit|Write)
    fp="$(printf '%s' "$input" | jq -r '.tool_input.file_path // ""' 2>/dev/null)" || fp=""
    case "$fp" in
      "$TESS_ROOT/CLAUDE.md") : ;;                       # entry-point doctrine
      "$TESS_ROOT"/conductor/*) : ;;                     # doctrine files
      "$TESS_ROOT"/agents/README.md) : ;;                # roster overview
      */.claude/projects/*/memory/*) : ;;                # project memory
      *) warn=1; detail="$tool -> $fp" ;;
    esac
    ;;
  Bash)
    cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // ""' 2>/dev/null)" || cmd=""
    first="${cmd%%[$' \t\n']*}"
    case "$first" in
      date|echo|printf|pwd|true|sleep)
        : ;;                                             # trivial orchestration logic
      cat|ls|head|tail|grep|rg|wc|find|stat)
        # Read-only inspectors are safe only when aimed at doctrine/memory paths.
        case "$cmd" in
          *clients/*|*dev.nosync*) warn=1 ;;             # client work is never solo
          *conductor/*|*CLAUDE.md*|*agents/README.md*|*/memory/*|*.claude/agents*) : ;;
          *) warn=1 ;;
        esac
        [ "$warn" -eq 1 ] && detail="Bash (read-only tool outside doctrine paths) -> $cmd"
        ;;
      *)
        warn=1
        detail="Bash -> $cmd"
        ;;
    esac
    ;;
  *)
    exit 0
    ;;
esac

if [ "$warn" -eq 0 ]; then
  exit 0
fi

# Truncate detail for a single-line message
detail="$(printf '%s' "$detail" | tr '\n' ' ' | head -c 200)"

jq -n --arg d "$detail" '{
  systemMessage: ("RULE ZERO WARNING (dispatch-guard, warn-mode): no dispatched task is in flight and this session is directly executing [" + $d + "] outside the Rule-Zero safe set. Rule Zero: ALWAYS DISPATCH — NEVER EXECUTE SOLO. Tess may only read doctrine/memory files, send Telegram messages, and do brief orchestration logic; all other work goes to a subagent via the Agent tool. This call was ALLOWED (warn-mode never blocks) — if this is task work, stop and dispatch it.")
}'

exit 0
