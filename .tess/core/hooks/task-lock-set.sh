#!/usr/bin/env bash
# PreToolUse hook for the dispatch tool (Agent/Task) — records a
# "dispatch in flight" lock counter so dispatch-guard.sh can distinguish
# tool calls made by dispatched subagents (hooks fire in ALL contexts, per conductor/hook-testing-protocol.md)
# from Tess executing solo. Counter handles parallel dispatches.
# Part of audit reform S1/G1 + S2/G2 (2026-06-10).
# This hook NEVER blocks anything (always exit 0 on every path).
#
# STALE-LOCK SAFETY (block-mode flip, 2026-06-10): locks older than 4 hours
# (240 min) are stale — pruned here and in task-lock-clear.sh, and IGNORED by
# dispatch-guard.sh. A leaked lock from a crashed session must not permanently
# suppress dispatch-guard.

# Per-user lock dir (v0.2.1, 2026-09-29 security review): the old shared
# /tmp/tess-dispatch-locks was world-writable, so any local user or process
# could plant a lock that silenced dispatch-guard. The dir is now private to
# this user (mode 700). TESS_LOCK_DIR still overrides (tests, custom setups).
LOCK_DIR="${TESS_LOCK_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/tess/dispatch-locks}"
STALE_MIN=240

input="$(cat)"
sid="$(printf '%s' "$input" | jq -r '.session_id // "global"' 2>/dev/null)" || sid="global"
[ -n "$sid" ] && [ "$sid" != "null" ] || sid="global"
# Sanitize to a safe filename
sid="$(printf '%s' "$sid" | tr -cd 'A-Za-z0-9._-')"
[ -n "$sid" ] || sid="global"

( umask 077; mkdir -p "$LOCK_DIR" ) 2>/dev/null || exit 0
chmod 700 "$LOCK_DIR" 2>/dev/null

# Prune stale locks (>4h old, e.g. from crashed sessions) so a dead lock
# cannot strand and permanently silence or trip the guards.
find "$LOCK_DIR" -name '*.lock' -mmin +"$STALE_MIN" -delete 2>/dev/null

lock="$LOCK_DIR/$sid.lock"
count="$(cat "$lock" 2>/dev/null || echo 0)"
case "$count" in
  ''|*[!0-9]*) count=0 ;;
esac
echo $((count + 1)) > "$lock" 2>/dev/null

exit 0
