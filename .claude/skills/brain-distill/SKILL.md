---
name: brain-distill
description: "After answering, turn the recent conversation into typed, quoted candidates (decisions, preferences, corrections, facts, open loops, reusable skills) for the brain inbox. Use when a [brain] reminder says turns are undistilled, at the end of a substantial session, or when asked to 'learn from this conversation'. Proposes only; a script verifies."
---

# brain-distill

The cue pass already catches explicit phrases ("let's go with", "from now
on", "that's wrong", "remind me"). Distill catches what it missed: implicit
decisions, stated facts, commitments. You PROPOSE; the verifier decides.

## Steps

1. Answer the operator first. Distill afterwards.
2. `python3 scripts/brain/tessbrain.py sync --quiet`
3. Read the newest session files under `brain/journal/YYYY/MM/DD/` (the
   `## Messages` section). Principal lines look like
   `[L12 14:05 <slug> cli] <their words>`; the line reference is
   `brain/journal/.../<file>.md#L12`.
4. For each item worth keeping, run one command with the exact quote and the
   line reference:

   ```
   python3 scripts/brain/tessbrain.py inbox add --kind <decision|preference|correction|fact|open_loop|skill> \
     --quote "<verbatim words from that line>" --source-ref "brain/journal/<...>.md#L12" \
     [--statement "<only words from the quote; leave it out to use the quote>"] \
     [--entity clients/<slug>] [--register brain/<entity>/decisions] [--tier material]
   ```

   The title and statement may only use words from the quote (rule V10); a
   rewording, reported speech, a pasted block or something taken back goes
   to `review` for the operator instead of being accepted.
5. When done: `python3 scripts/brain/tessbrain.py distilled` (resets the reminder).
6. Tell the operator in one line what was learned (the command output says
   accepted / active / proposed / review / fail).

## Never

- Never write records or edit files under `brain/` directly; only `inbox add`.
- Never quote assistant replies (`[R.. assistant]` lines) as a principal's words.
- Never propose questions, hypotheticals or brainstorming as decisions.
- Never include secrets or personal identifiers; they are redacted in the journal.
