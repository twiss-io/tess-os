---
name: brain-recall
description: "Find what the brain already knows before answering about a client, person, project, decision, preference or past conversation. Use before saying something is unknown, when asked 'what did we decide about X', 'what does the operator prefer', or 'where is the note of that conversation'."
---

# brain-recall

## Steps

1. Start at the map: `brain/START-HERE.md`, then the entity's `AGENTS.md`
   (START HERE) for the client, person, project, unit or area involved.
2. Search: `python3 scripts/brain/tessbrain.py recall "<words>" [--entity clients/<slug>] [--type decision]`
   It prints `path:line: text`, best matches first.
3. Open the files it points to. For a decision, the record's `source_ref`
   points at the journal line with the principal's exact words; quote that.
4. Answer with the file path. Say which status the record has (accepted,
   proposed, superseded, retracted); never present a superseded or
   unverified record as current.

## Where things are

- Decisions: `brain/decisions/INDEX.md` and `brain/<entity>/decisions/INDEX.md`
- Preferences and corrections: `brain/profile.md`
- Open loops: `brain/open-loops.md`
- Every conversation: `brain/journal/INDEX.md` (one file per session)
- What was learned lately: `brain/learned.md`

Never say something is unknown before searching `brain/`.
