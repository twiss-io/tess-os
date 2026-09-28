---
name: brain-save
description: "Make brain work actually saved: in its owning folder, linked from its START HERE, committed and pushed. Use before saying 'saved', 'done' or 'recorded', at the end of a session, or when status reports unsaved, unpushed, unreachable or misplaced files."
---

# brain-save

"Saved" = in its owning folder + linked from its START HERE + committed +
pushed. Only the tool's output proves it.

## Steps

1. If your runtime has no capture hooks and no transcript sweep (anything
   other than Claude Code, Codex or Gemini CLI), note the conversation first:
   `python3 scripts/brain/tessbrain.py journal note --text "<the operator's words this session, verbatim>"`
   (add `--speaker <slug>` for another principal). A hand-written note is
   held for the operator's review; it is never auto-promoted.
2. `python3 scripts/brain/tessbrain.py status`
3. Fix what it reports:
   - "unreachable": add a link to the file in its entity `AGENTS.md`
     (START HERE) or in `brain/START-HERE.md`, then
     `python3 scripts/brain/tessbrain.py index`.
   - "Ignored or gate-blocked, never committed": move the file under
     `brain/` (for example `kb/research/x.md` -> `brain/kb/research/x.md`,
     `clients/acme/kb/...` -> `brain/clients/acme/kb/...`) and link it.
4. `python3 scripts/brain/tessbrain.py save -m "brain: <what changed>"`
   In Codex: its default sandbox keeps `.git` read-only, so a save run inside
   the sandbox fails with `index.lock: Operation not permitted`. Run this
   command with escalated permissions from the start (shell tool
   `sandbox_permissions: "require_escalated"`, justification "save the
   brain: git commit"), so Codex asks the operator to approve it. Tell them
   it is one click: "Yes, proceed", or "Yes, and don't ask again for
   commands that start with" it to skip the question next time. If they
   decline, report the work as not saved; never report a sandbox failure as
   saved and never retry it silently.
5. Report the result honestly: committed (hash), pushed or not, and why not.

## Never

- Never bypass git hooks. A folder made with `npm create tess` passes the
  ship-gate on its first push (it carries the signed release's proof); if
  a push is still refused, tell the operator what the gate said and point
  them to docs/brain/ONBOARDING.md section 8; they decide what to do.
- Never push brain data to the public Tess OS framework repository or any
  public remote (the tool refuses; do not work around it).
- Never say "saved" while status still lists the file.
