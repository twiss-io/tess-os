---
name: brain-save
description: "Make brain work actually saved: in its owning folder, linked from its START HERE, committed and pushed. Use before saying 'saved', 'done' or 'recorded', at the end of a session, or when status reports unsaved, unpushed, unreachable or misplaced files."
---

# brain-save

"Saved" = in its owning folder + linked from its START HERE + committed +
pushed. Only the tool's output proves it.

## Steps

1. If your runtime has no capture hooks (anything other than Claude Code with
   project hooks, or Codex after `/hooks` approval), note the conversation first:
   `python3 scripts/brain/tessbrain.py journal note --text "<the operator's words this session, verbatim>"`
2. `python3 scripts/brain/tessbrain.py status`
3. Fix what it reports:
   - "unreachable": add a link to the file in its entity `AGENTS.md`
     (START HERE) or in `brain/START-HERE.md`, then
     `python3 scripts/brain/tessbrain.py index`.
   - "Ignored or gate-blocked, never committed": move the file under
     `brain/` (for example `kb/research/x.md` -> `brain/kb/research/x.md`,
     `clients/acme/kb/...` -> `brain/clients/acme/kb/...`) and link it.
4. `python3 scripts/brain/tessbrain.py save -m "brain: <what changed>"`
5. Report the result honestly: committed (hash), pushed or not, and why not.

## Never

- Never bypass git hooks. If the first push of a new instance is refused by
  the ship-gate, tell the operator about the one-time seed push in
  docs/brain/ONBOARDING.md; they run it themselves.
- Never push brain data to the public Tess OS framework repository or any
  public remote (the tool refuses; do not work around it).
- Never say "saved" while status still lists the file.
