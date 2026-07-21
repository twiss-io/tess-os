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

# Emit hookSpecificOutput to mutate the tool input
jq -n \
  --arg cleaned "$cleaned" \
  '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      modifiedToolInput: { text: $cleaned }
    },
    systemMessage: "Telegram format guard: stripped MarkdownV2 escapes from text since format!=markdownv2. Default to plain prose; set format=markdownv2 if you want markup."
  }'

exit 0
