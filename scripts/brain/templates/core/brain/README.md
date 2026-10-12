# Rules for this brain

This folder is the operator's second brain. Files are the source of truth;
any runtime's own memory is only a cache. Start at [START-HERE.md](START-HERE.md).

## Reading

- Open an entity's `AGENTS.md` (its START HERE) before answering about that
  client, person, project, unit or area.
- Search before saying something is unknown:
  `python3 scripts/brain/tessbrain.py recall "<words>"`.
- `profile.md` is how the operator wants to work, `decisions/INDEX.md` what
  was decided, `open-loops.md` what is pending, `learned.md` what the brain
  learned recently, and `journal/` every conversation (one file per session).

## Writing

- A decision, preference, correction, fact or open loop is recorded only with
  a principal's exact words, through the tool (skills `brain-decide`,
  `brain-remember`, `brain-distill`). A script checks every quote against
  the journal before anything is written. Never write or edit a record by
  hand, and never record your own suggestion, a question or a hypothetical.
- Records are never edited after acceptance: a change is a new record that
  supersedes the old one.
- Files marked `generated: true`, and the text between `tess:gen` markers,
  are rewritten by `tessbrain.py index`. Write everything else by hand.
- New files go in their owning folder and are linked from that folder's
  START HERE.

## Saved

"Saved" = in its owning folder + linked from its START HERE + committed +
pushed. Run `python3 scripts/brain/tessbrain.py status` (skill `brain-save`)
before saying "saved". The tools never bypass git hooks.

## Never here

Secrets, passwords, tokens, government IDs, pay, health or HR records, and
contract files. Write a pointer to where they live instead. `.private/`
folders are local only and never committed.
