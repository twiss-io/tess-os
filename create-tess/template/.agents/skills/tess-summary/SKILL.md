---
name: tess-summary
description: "Concise mission status snapshot — objective, current state, active agents, work completed, key findings, and open decisions."
---

<!-- Rendered by `tessctl render --target codex` from .tess/core/commands/summary.md. Regenerate; do not hand-edit. -->

Tess OS command `/summary`, packaged as an Agent Skill. Run it only when the user asks for it by name (`$tess-summary` in Codex).

# /summary

Return a quick status snapshot of the active mission (lighter than `/review-mission`):

- **Objective** — what the mission is trying to achieve
- **Current state** ([conductor/mission-states.md](../../../conductor/mission-states.md))
- **Active agents and roles**
- **Work completed** to date
- **Key findings** so far
- **Open decisions** still in play

Calibrate the weight to the ask — keep it tight. Read-only; use mid-flow or to re-orient after a break.
