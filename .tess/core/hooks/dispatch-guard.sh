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

LOCK_DIR="/tmp/tess-dispatch-locks"
TESS_ROOT="$CLAUDE_PROJECT_DIR"

input="$(cat)"

# Dispatch in flight (any lock fresher than 24h) -> assume subagent context, stay silent.
if [ -d "$LOCK_DIR" ] && find "$LOCK_DIR" -name '*.lock' -mmin -1440 2>/dev/null | grep -q .; then
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
