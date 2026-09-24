---
name: brain-review
description: "Show the operator what the brain learned or holds for confirmation (auto-promoted items, proposed material decisions, open loops, inbox candidates) as a numbered list, then apply their answer in their own words: approve, reject, retract, correct. Use for 'what did you learn', 'review the brain', a [brain] review line at session start, or a weekly review."
---

# brain-review

## Steps

1. `python3 scripts/brain/tessbrain.py review --json`
2. Show a numbered list: number, what it is, the statement, why it is waiting
   (the verifier's reason). Keep it short.
3. Ask the operator to answer in words, for example "approve 1 and 3,
   reject 2, 4 is wrong: it should be ...".
4. Apply each answer with the operator's exact reply as the quote:

   ```
   python3 scripts/brain/tessbrain.py confirm <id> --quote "<their words>"     # approve (sets confirmed: true)
   python3 scripts/brain/tessbrain.py reject <id> --quote "<their words>"      # "that was not a decision"
   python3 scripts/brain/tessbrain.py retract <id> --quote "<their words>"     # "forget that / that is wrong"
   python3 scripts/brain/tessbrain.py promote <C-id> --quote "<their words>"   # approve an inbox candidate
   ```

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

- Never approve on the operator's behalf. Every change needs their words.
- Never edit record files by hand; the tool keeps history intact.
