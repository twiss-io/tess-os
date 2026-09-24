---
name: brain-decide
description: "Record a decision in the Tess brain, in the principal's exact words. Use when the operator or another principal listed in brain/brain.json decides, approves, picks, drops or reverses something ('let's go with X', 'decision: ...', 'we'll use ...', 'yes, ship it'). Never for your own suggestion, a question or a hypothetical."
---

# brain-decide

A decision is recorded only with the decider's **verbatim** words. A script (the
verifier, rules V1-V9) checks the quote against the journal, the speaker,
every number, scope, and hypotheticals before anything is written.

## Steps

1. Bring the journal up to date: `python3 scripts/brain/tessbrain.py sync --quiet`.
2. Pick the exact sentence the principal said. Copy it character for character
   from their message. Do not tidy, translate or shorten words inside it.
3. Choose the register:
   - one client, unit, project or area named -> `brain/<entity>/decisions`
     (for example `brain/clients/acme/decisions`);
   - otherwise `brain/decisions`.
4. Run:

   ```
   python3 scripts/brain/tessbrain.py decide \
     --register brain/decisions \
     --title "<short title using only words and numbers from the quote>" \
     --statement "We will <what was decided>" \
     --quote "<the principal's exact words>" \
     [--supersedes D-YYYYMMDD-HHMM-slug] [--tier material] [--kind decision|requirement|constraint|question]
   ```

   - `--tier material` for anything about money, prices, people (hiring, pay,
     roles) or contracts. Material decisions stay `proposed` until the
     operator confirms them.
   - `--supersedes` when this reverses or narrows an earlier decision (find it
     with `tessbrain.py recall "<words>"`). History is never edited.
   - When the principal approved something YOU proposed ("yes, do that"), pass
     `--approves-quote "<your proposal, verbatim>"` and the principal's short
     approval as `--quote`.
5. Read the result. `accepted` or `proposed` = recorded. `fail` lists the rule
   that refused it: fix the quote (it must be their words) or tell the
   operator plainly that it was not recorded and why.

## Never

- Never record your own suggestion, a question, "what if ...", "maybe ...",
  "thinking out loud", or something the principal only discussed.
- Never invent or paraphrase a quote. If you cannot find their exact words,
  ask them to state the decision.
- Never put a number, date, URL or amount in `--title`/`--statement` that is
  not in the quote (rule V4 rejects it).
- Never edit an accepted decision file. Supersede it.
