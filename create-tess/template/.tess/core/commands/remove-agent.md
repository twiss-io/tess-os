---
description: Request Eva to assess and remove an agent — evaluates whether the agent still earns its seat, then removes and reassigns or closes the workstream.
argument-hint: [Name]
---

# /remove-agent

Assess removal of: **$ARGUMENTS**

Dispatch **Eva** to:
1. Evaluate whether the agent is still earning its seat (portfolio discipline, [conductor/agent-lifecycle.md](../../conductor/agent-lifecycle.md)).
2. If not, set `lifecycle_status` to retired (or remove the `.claude/agents/<name>.md` file) and reassign or close any open workstream the agent owned.
3. Confirm no active mission depends on the agent before removal.

Per Rule Zero, Tess dispatches Eva rather than editing the roster solo. Confirm with the operator before removing an agent tied to live client work.
