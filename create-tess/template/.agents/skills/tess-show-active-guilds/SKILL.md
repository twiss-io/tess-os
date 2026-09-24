---
name: tess-show-active-guilds
description: "List all currently active guilds with their participation role, specific mandate on this mission, and expected output."
---

<!-- Rendered by `tessctl render --target codex` from .tess/core/commands/show-active-guilds.md. Regenerate; do not hand-edit. -->

Tess OS command `/show-active-guilds`, packaged as an Agent Skill. Run it only when the user asks for it by name (`$tess-show-active-guilds` in Codex).

# /show-active-guilds

List every active guild on the current mission, per [conductor/cross-guild-coordination.md](../../../conductor/cross-guild-coordination.md).

For each guild report:
- **Guild name**
- **Participation role** — Owner / Core Contributor / Reviewer / Control / Standby
- **Specific mandate** on this mission
- **Expected output**

Then state whether the crew is **right-sized** — flag over-orchestration (too many guilds for the task) or gaps (a needed guild on Standby). Calibrate orchestration weight to the task per [conductor/daily-operating-behavior.md](../../../conductor/daily-operating-behavior.md). Read-only.
