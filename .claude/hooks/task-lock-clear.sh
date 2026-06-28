#!/usr/bin/env bash
# PostToolUse hook for the dispatch tool (Agent/Task) — decrements the
# dispatch-in-flight lock counter set by task-lock-set.sh; removes the lock
# file when the last in-flight dispatch returns.
# ALSO wired on SessionEnd (block-mode flip, 2026-06-10): when a session ends,
# its lock is removed outright regardless of counter value — a session that no
# longer exists cannot have a dispatch in flight, and PostToolUse will never
# fire for it again. This closes the lock-stranding gap (e.g. session crash or
# close between dispatch and completion).
# Part of audit reform S1/G1 + S2/G2 (2026-06-10).
# This hook NEVER blocks anything (always exit 0 on every path).
#
# STALE-LOCK SAFETY: locks older than 4 hours (240 min) are stale — reaped
# here on every invocation and IGNORED by both guards.

LOCK_DIR="${TESS_LOCK_DIR:-/tmp/tess-dispatch-locks}"
STALE_MIN=240

input="$(cat)"
event="$(printf '%s' "$input" | jq -r '.hook_event_name // ""' 2>/dev/null)" || event=""
sid="$(printf '%s' "$input" | jq -r '.session_id // "global"' 2>/dev/null)" || sid="global"
[ -n "$sid" ] && [ "$sid" != "null" ] || sid="global"
sid="$(printf '%s' "$sid" | tr -cd 'A-Za-z0-9._-')"
[ -n "$sid" ] || sid="global"

# Reap stale locks (>4h) so leaked locks from dead sessions cannot strand.
[ -d "$LOCK_DIR" ] && find "$LOCK_DIR" -name '*.lock' -mmin +"$STALE_MIN" -delete 2>/dev/null

lock="$LOCK_DIR/$sid.lock"

# SessionEnd: remove this session's lock entirely — no counter math. Other
# sessions' locks are untouched (parallel-session semantics preserved).
if [ "$event" = "SessionEnd" ]; then
  rm -f "$lock" 2>/dev/null
  exit 0
fi

[ -f "$lock" ] || exit 0

count="$(cat "$lock" 2>/dev/null || echo 0)"
case "$count" in
  ''|*[!0-9]*) count=0 ;;
esac
count=$((count - 1))

if [ "$count" -le 0 ]; then
  rm -f "$lock" 2>/dev/null
else
  echo "$count" > "$lock" 2>/dev/null
fi

exit 0
