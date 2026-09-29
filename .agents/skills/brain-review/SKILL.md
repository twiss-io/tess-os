---
name: brain-review
description: "Show the operator what the brain learned or holds for confirmation (auto-promoted items, proposed material decisions, open loops, inbox candidates) as a numbered list, then apply their answer in their own words: approve, reject, retract, correct. Use for 'what did you learn', 'review the brain', a [brain] review line at session start, or a weekly review."
---

# brain-review

## Steps

1. `python3 scripts/brain/tessbrain.py review --json`
2. Show a numbered list: number, the item's **short id** (`short_id`), what
   it is, the statement, why it is waiting (the verifier's reason), and the
   item's `reply` line word for word, for example:

   `1. D-0929-use-postgres: decision "Use Postgres for billing" (needs your confirmation).`
   `   Reply "confirm D-0929-use-postgres" to accept, or "reject D-0929-use-postgres" to drop it`

   Keep it short. Running `review` records that these items, as they are now,
   were shown to the operator, together with each short id.
3. Ask the operator to answer with those phrases. An answer is accepted only
   when it comes after this listing, names the item's short id (or full id),
   and is a plain instruction: the WHOLE reply is exactly
   `confirm <short id>` (or `yes, confirm ...`, `accept ...`) or
   `reject <short id>` (a short reason after a comma is fine), optionally in
   quotes. A list number, an earlier message, a bare "yes", a question
   ("should I confirm ...?"), a condition on the same or another line
   ("If legal approves:" then "confirm ..."), a code block, a `>` quote, a
   list item or a quote is not enough (the tool refuses it, and you never
   type the approval yourself). Several answers in one reply go on separate
   lines, one id per line, with nothing else in the reply.
4. Apply each answer with the operator's exact reply as the quote, and the
   item's FULL id (`id`) as `<id>`:

   ```
   python3 scripts/brain/tessbrain.py confirm <id> --quote "<their words>"     # approve (sets confirmed: true)
   python3 scripts/brain/tessbrain.py reject <id> --quote "<their words>"      # "that was not a decision"
   python3 scripts/brain/tessbrain.py retract <id> --quote "<their words>"     # "forget that / that is wrong"
   python3 scripts/brain/tessbrain.py promote <C-id> --quote "<their words>"   # approve an inbox candidate
   ```

   If the tool answers that the item "has not been shown", "changed since it
   was shown", that their words "predate" the listing, or that the quote must
   name a different id (another item now shares the short id), run step 1
   again, show the item with its new `reply` line, and ask again.

   If the tool answers `"status": "pending"`, this shell cannot write the
   brain's private state (a sandbox): the confirmation is queued, and the
   next hook records and applies it when this turn ends. Tell the operator
   exactly that; do not say it was accepted, and do not run it again.

   A correction ("4 should be ...") is recorded with skill `brain-remember`
   (`--kind correction --supersedes <id>`).
5. Finish with `python3 scripts/brain/tessbrain.py status`.

## Consolidate (when a tool says "consolidate: brain-review --consolidate")

`brain/profile.md` or a register is at its size cap, so the tool refused to
add more (nothing was truncated). Show the operator the active preferences
and corrections (`python3 scripts/brain/tessbrain.py recall "" --type preference`
or `brain/profile/INDEX.md`), ask which ones to drop or merge, and apply
their words: `retract <id> --quote "..."` for each one to drop, then record a
merged preference with skill `brain-remember` quoting their new wording.
Then run `python3 scripts/brain/tessbrain.py sync`.

## Weekly review (when asked, or 7 days after the last one)

Inbox to zero; projects without a next action; waiting-fors older than 14
days; START HERE files whose `last_verified` is older than 30 days; budgets
(`tessbrain.py lint`).

## Never

- Never approve on the operator's behalf. Every change needs their words, naming the id.
- Never edit record files by hand; the tool keeps history intact.
