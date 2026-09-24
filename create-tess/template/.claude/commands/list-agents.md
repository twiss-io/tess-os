---
description: List the ten roles (conductor plus nine dispatchable roles) and the lenses loaded on the active mission.
---

# /list-agents

List the roster: the ten roles in [conductor/roster.md](../../conductor/roster.md), which of the nine role files are installed in `.claude/agents/` (`tessctl roster list`), and the lenses ([conductor/lenses/README.md](../../conductor/lenses/README.md)) loaded on the active mission.

For each agent report:
- **Name**
- **Role**
- **Mandate**
- **Participation role** on the active mission (if any)
- **Lifecycle status** — active / standby / retired ([conductor/agent-lifecycle.md](../../conductor/agent-lifecycle.md))

Read-only. For expertise gaps use `/add-agent` (it adds a lens, not an agent); to bench a role use `/remove-agent`.
