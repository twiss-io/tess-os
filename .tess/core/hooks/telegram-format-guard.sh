#!/usr/bin/env bash
# PreToolUse hook for mcp__plugin_telegram_telegram__reply (and edit_message)
# Auto-strips MarkdownV2 escape backslashes from the text parameter when
# `format` is NOT explicitly set to "markdownv2". Without this, escapes like
# \-, \#, \(, \. render literally in the chat because Telegram defaults to
# plain text, which surfaces as visibly malformed output to the message recipient.

input="$(cat)"

text="$(printf '%s' "$input" | jq -r '.tool_input.text // ""')"
format="$(printf '%s' "$input" | jq -r '.tool_input.format // ""')"

# Skip if format is markdownv2 (escapes are intentional)
if [ "$format" = "markdownv2" ]; then
  exit 0
fi

# Check for any backslash-escape pattern characteristic of MarkdownV2
has_mv2_escape=0
case "$text" in
  *'\_'*|*'\*'*|*'\['*|*'\]'*|*'\('*|*'\)'*|*'\~'*|*'\`'*|*'\>'*|*'\#'*|*'\+'*|*'\='*|*'\|'*|*'\{'*|*'\}'*|*'\.'*|*'\!'*|*'\-'*)
    has_mv2_escape=1
    ;;
esac

if [ "$has_mv2_escape" -eq 0 ]; then
  exit 0
fi

# Strip backslashes from MarkdownV2 reserved chars (BRE, not ERE — ERE was eating the literal backslash)
cleaned="$(printf '%s' "$text" | sed 's/\\\([_*()~`>#+={}.!|-]\)/\1/g' | sed 's/\\\(\[\)/\1/g' | sed 's/\\\(\]\)/\1/g')"

# Emit hookSpecificOutput to update the tool input. `updatedInput` REPLACES
# the tool's entire input (it is not a merge — see Claude Code hooks docs,
# "PreToolUse: updatedInput directly under hookSpecificOutput replaces a
# tool's arguments before it runs"). `modifiedToolInput` is NOT a real hook
# field, so the strip previously never applied at all even though the
# systemMessage below claimed it did. Build the replacement from the
# ORIGINAL tool_input and only overwrite `text`, so every other field
# (chat_id, reply_to, files, etc.) survives untouched.
updated_input="$(printf '%s' "$input" | jq --arg cleaned "$cleaned" '.tool_input | .text = $cleaned')"

jq -n \
  --argjson updated_input "$updated_input" \
  '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      updatedInput: $updated_input
    },
    systemMessage: "Telegram format guard: stripped MarkdownV2 escapes from text since format!=markdownv2 (all other tool_input fields preserved). Default to plain prose; set format=markdownv2 if you want markup."
  }'

exit 0
