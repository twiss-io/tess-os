## Command System

> **These are first-class wired slash commands.** Each token below is backed by a real `.claude/commands/<name>.md` file (Phase 2, 2026-06-27) that the host registers and expands. Natural-language equivalents still work — "/add-mission ..." and "add a mission: ..." both run the same doctrine flow — but the commands are now installed, not conventions. Full catalogue: [conductor/commands.md](conductor/commands.md).

**Mission lifecycle commands:**

| Command | Action |
|---|---|
| `/add-mission [brief]` | Start a new mission (intake + routing) |
| `/review-mission` | Full mission status snapshot |
| `/route-mission` | Re-evaluate the outcome lens |
| `/show-owner` | Display outcome owner |
| `/show-active-guilds` | List active guilds and roles |
| `/show-risks` | Surface risks and blockers |
| `/show-next-moves` | Display sequenced next actions |
| `/wake` | Session start checklist — orient, check state, surface blockers |
| `/close` | Session end checklist — confirm state, flag decisions, log |
| `/finalize` | Deliver executive synthesis memo |
| `/summary` | Quick status snapshot |
| `/reset` | Clear and restart the mission |
| `/code-red [brief]` | Emergency escalation |

**Outcome-lens shortcuts:**

| Command | Routes to |
|---|---|
| `/founder-mode` | Founder's Office outcome lens |
| `/revenue-mode` | Revenue outcome lens |
| `/product-mode` | Product and Delivery outcome lens |
| `/cx-mode` | Client Experience outcome lens |
| `/ops-mode` | Operational Reliability outcome lens |
| `/strategic-mode` | Strategic Growth outcome lens |

**Crew and system:**

| Command | Action |
|---|---|
| `/list-agents` | View the ten roles and loaded lenses |
| `/add-agent [Name]` | Cover a capability gap with a lens (the roster stays ten roles) |
| `/remove-agent [Name]` | Retire a lens or bench a role |
| `/brainstorm` | Open exploration mode |
| `/feedback` | Apply system feedback |
| `/help` | Command reference |

Full command reference: [conductor/commands.md](conductor/commands.md)  
Playbooks: [conductor/playbooks/](conductor/playbooks/README.md)
