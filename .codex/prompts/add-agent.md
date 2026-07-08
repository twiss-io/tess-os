---
description: Request Eva to recruit or design a new specialist agent — assesses the capability gap and returns a full agent brief before activation.
argument-hint: [Name or capability needed]
---

# /add-agent

Recruit a new specialist: **$ARGUMENTS**

Dispatch **Eva** (HR Specialist & AI Talent Strategist — crew gate) to:
1. Review the active mission and identify the capability gap.
2. Decide recruit vs design vs reuse-existing (avoid roster bloat — portfolio discipline in [conductor/agent-lifecycle.md](../../conductor/agent-lifecycle.md)).
3. Return a full agent brief — name (naming discipline per agent-lifecycle.md), role, mandate, tools, model tier, and `lifecycle_status` — **before** activation.

Per Rule Zero, Tess dispatches Eva rather than designing the agent solo. New agent files follow the `.claude/agents/<name>.md` frontmatter convention. Confirm with the operator before activating if the role is non-trivial.
