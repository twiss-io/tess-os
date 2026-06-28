---
description: List all currently active agents and their responsibilities — name, role, mandate, participation role on this mission, and status.
---

# /list-agents

List the active crew. Read from [agents/README.md](../../agents/README.md) and the managed-subagent set in `.claude/agents/`.

For each agent report:
- **Name**
- **Role**
- **Mandate**
- **Participation role** on the active mission (if any)
- **Lifecycle status** — active / standby / retired ([conductor/agent-lifecycle.md](../../conductor/agent-lifecycle.md))

Read-only. For roster changes use `/add-agent` or `/remove-agent` (via Eva).
