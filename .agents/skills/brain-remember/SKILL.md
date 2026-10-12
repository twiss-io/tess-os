---
name: brain-remember
description: "Record what the operator wants remembered: a standing preference ('from now on ...', 'always/never ...'), a correction ('no, that's wrong ...'), a fact they stated, or an open loop ('remind me ...', 'waiting on ...'). Uses their exact words; a script verifies before anything is written."
---

# brain-remember

## Steps

1. `python3 scripts/brain/tessbrain.py sync --quiet` (brings the journal up to date).
2. Copy the principal's exact words.
3. Run one of:

   ```
   python3 scripts/brain/tessbrain.py remember --kind preference --quote "<exact words>"
   python3 scripts/brain/tessbrain.py remember --kind correction --quote "<exact words>" [--supersedes P-...|C-...]
   python3 scripts/brain/tessbrain.py remember --kind fact --quote "<exact words>" --entity clients/<slug> --verify-via "<where to re-check it>"
   python3 scripts/brain/tessbrain.py remember --kind open_loop --quote "<exact words>" [--entity clients/<slug>] [--due YYYY-MM-DD] [--owner <slug>]
   ```

4. Report what the result says: `active` (preference/correction/fact),
   `proposed` (open loops wait for the principal's confirmation), `review`,
   or `fail` with the rule that refused it.

## Rules

- Preferences and corrections go to `brain/profile/` and appear in
  `brain/profile.md`, which the next session reads.
- A correction that replaces an older preference passes `--supersedes <id>`.
- Facts you or a tool found (not the principal's words) are never promoted
  automatically: they wait in the inbox for review.
- `--verify-via` is required for anything that can change (prices, owners,
  versions, dates).
- Never store secrets, government IDs, pay, health or HR details. Write a
  pointer to where they live instead.
