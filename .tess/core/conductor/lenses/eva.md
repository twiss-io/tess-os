# Lens: Eva — Crew Design

> Lens, not an agent. The conductor loads this file into its own planning, or into a role's brief, when the task needs this expertise. It adds questions and a quality bar; it never adds permissions. Eva was the recruiting agent; in the ten-role roster the roster is fixed, so this lens is how the conductor decides which role and which lenses a task gets.

**Use when:** planning a dispatch whose right role or lens is not obvious, or when a task seems to need expertise the roster lacks.

## Focus

Design the function first, then pick the role. The roster is fixed at ten roles defined by permissions (`conductor/roster.md`); expertise comes from lenses. Crew design is choosing the fewest roles, each with the right lens, in the right order.

## Questions and principles

- What does the task need to DO (read, search, research, build, review, test, sign, record, release, design)? That picks the role.
- What does it need to KNOW? That picks the lens (see `conductor/lenses/README.md`).
- Can one role do it? Default to one builder plus one verifier; add roles only for a real capability gap.
- No overlap: two dispatches producing similar output is waste.
- Which verifier does the output need (conductor/verification-routing.md)?

## Output shape

| Section | Purpose |
|---|---|
| Task | What must be done and what done looks like |
| Roles | Each role used, in order, with what it does |
| Lenses | The lens loaded into each role's brief, and why |
| Verifier | Reid, Quinn or Cyra, and the primary artifacts they read |
| Not used | Roles or lenses considered and left out, and why |

## Guardrails

- Never create a new agent file to cover a gap. Write or extend a lens instead, and say so.
- A lens never widens a role's permissions.
