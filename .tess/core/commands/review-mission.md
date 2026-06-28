---
description: Full mission status snapshot — current state, outcome owner, active guilds and roles, pending decisions, blockers, and immediate next moves.
---

# /review-mission

Return a structured snapshot of the active mission. Read state from [conductor/mission-states.md](../../conductor/mission-states.md) and ownership from [conductor/outcome-orchestrators/README.md](../../conductor/outcome-orchestrators/README.md).

Report, in order:
1. **Mission name and current state** (one of the 11 states in mission-states.md).
2. **Outcome owner and orchestrator** — who holds the mission and why.
3. **Active guilds and roles** — Owner / Core Contributor / Reviewer / Control / Standby per [conductor/cross-guild-coordination.md](../../conductor/cross-guild-coordination.md).
4. **Pending decisions** gating progress.
5. **Blockers and risks** — including any verification gates not yet cleared ([conductor/verification-routing.md](../../conductor/verification-routing.md)).
6. **Immediate next moves** — sequenced, with owners.

Read-only orientation command. Do not advance the mission; just report. Surface anything that gates on the operator per [conductor/guardrails.md](../../conductor/guardrails.md) Rule 18.
