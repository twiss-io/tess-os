#!/usr/bin/env bash
# PreToolUse companion hook for mcp__plugin_telegram_telegram__reply and
# edit_message — anti-fabrication guard (audit reform S2/G2, 2026-06-10).
# Runs ALONGSIDE telegram-format-guard.sh (which stays unmodified).
#
# WARN-MODE ONLY: this hook NEVER blocks or mutates a message. Every path
# exits 0 — it only surfaces a systemMessage warning. Block-mode is explicitly
# NOT authorized (Decision 7); a false-positive block on the primary comms
# channel would create silence and violate Telegram-first doctrine.
#
# Trigger: the outgoing message contains completion-claim markers (past-tense
# results, commit SHAs, PR numbers, x/y counts, percentages) WHILE a dispatched
# task is still in flight (lock set by task-lock-set.sh). Numbers and statuses
# composed before reading agent results are a known fabrication risk — a status,
# count, or commit reference invented before the real output is read is a
# fabricated claim. Dispatch-start narration and progress updates carry no
# completion markers and pass silently.

LOCK_DIR="/tmp/tess-dispatch-locks"

input="$(cat)"

text="$(printf '%s' "$input" | jq -r '.tool_input.text // ""' 2>/dev/null)" || text=""
[ -n "$text" ] || exit 0

# Only relevant while a dispatch is in flight; otherwise results have had a
# chance to be read before composing the message.
if ! { [ -d "$LOCK_DIR" ] && find "$LOCK_DIR" -name '*.lock' -mmin -1440 2>/dev/null | grep -q .; }; then
  exit 0
fi

markers=""

# Past-tense completion verbs (report pattern list: merged/deployed/fixed/live...)
if printf '%s' "$text" | grep -qiE '(^|[^[:alnum:]])(merged|deployed|redeployed|shipped|pushed|committed|fixed|resolved|completed|finished|verified|confirmed|released|landed|rolled back|went live|now live|is live)([^[:alnum:]]|$)'; then
  markers="${markers}past-tense completion verb; "
fi

# Commit-SHA-like tokens (7-40 hex chars containing at least one a-f letter,
# to avoid matching plain numbers/timestamps)
if printf '%s' "$text" | grep -oE '(^|[^[:alnum:]])[0-9a-f]{7,40}([^[:alnum:]]|$)' | grep -q '[a-f]'; then
  markers="${markers}commit SHA; "
fi

# PR numbers
if printf '%s' "$text" | grep -qiE '(#[0-9]+|PR[ #]?[0-9]+)'; then
  markers="${markers}PR number; "
fi

# x/y counts
if printf '%s' "$text" | grep -qE '(^|[^[:alnum:]])[0-9]+/[0-9]+([^[:alnum:]]|$)'; then
  markers="${markers}x/y count; "
fi

# Percentages
if printf '%s' "$text" | grep -qE '[0-9]+(\.[0-9]+)?%'; then
  markers="${markers}percentage; "
fi

[ -n "$markers" ] || exit 0

jq -n --arg m "$markers" '{
  systemMessage: ("ANTI-FABRICATION WARNING (warn-mode): this Telegram message contains completion-claim markers (" + $m + ") while a dispatched task is STILL IN FLIGHT. Never message data before reading it: send action -> read the real result next turn -> THEN report. Composing numbers/status/root-cause in the same batch as the dispatch is how fabricated facts reach a recipient — fabricated output reaching a user or downstream consumer is a critical failure. This message was ALLOWED (warn-mode never blocks) — if any claim here depends on the in-flight task, wait for its real output and verify before sending a completion claim.")
}'

exit 0
