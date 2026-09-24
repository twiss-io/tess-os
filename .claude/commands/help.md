---
description: Display the command reference and operating orientation for the Tess command system.
---

# /help

Display the Tess command reference and a short operating orientation. Source of truth: [conductor/commands.md](../../conductor/commands.md).

Present the commands grouped as:

**Mission lifecycle:** `/add-mission`, `/review-mission`, `/route-mission`, `/show-owner`, `/show-active-guilds`, `/show-risks`, `/show-next-moves`, `/wake`, `/close`, `/finalize`, `/summary`, `/reset`, `/code-red`

**Orchestrator modes:** `/founder-mode`, `/revenue-mode`, `/product-mode`, `/cx-mode`, `/ops-mode`, `/strategic-mode`

**Crew:** `/list-agents`, `/add-agent`, `/remove-agent`

**System:** `/initiate` (legacy → `/add-mission`), `/brainstorm`, `/feedback`, `/help`

Orientation reminders: Rule Zero (always dispatch, never execute solo), every task is reported in the active session, and mission flow is governed by dependency gates (intake → research → crew → review → verification). Full doctrine: [conductor/README.md](../../conductor/README.md).
