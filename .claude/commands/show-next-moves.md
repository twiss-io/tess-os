---
description: Display the immediate next actions for the active mission — sequenced, with owners and dependencies.
---

# /show-next-moves

Display the immediate next actions for the active mission.

For each move report:
- **The action** — specific, not abstract
- **Owner**
- **Dependencies** — what must complete first (respect the dependency gates in [conductor/doctrine.md](../../conductor/doctrine.md): research before build, crew before deploy, review before synthesis, verification before anything externally visible)

Present in execution sequence. Independent moves that can run in parallel should be flagged as such. Read-only — confirms sequencing; does not execute.
