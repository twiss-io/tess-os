## Command System

> **These are first-class wired slash commands.** Each token below is backed by a real `.claude/commands/<name>.md` file (Phase 2, 2026-06-27) that the host registers and expands. Natural-language equivalents still work — "/add-mission ..." and "add a mission: ..." both run the same doctrine flow — but the commands are now installed, not conventions. Full catalogue: [conductor/commands.md](conductor/commands.md).

**Mission lifecycle commands:**

| Command | Action |
|---|---|
| `/add-mission [brief]` | Start a new mission (intake + routing) |
| `/review-mission` | Full mission status snapshot |
| `/route-mission` | Re-evaluate orchestrator assignment |
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

**Orchestrator routing shortcuts:**

| Command | Routes to |
|---|---|
| `/founder-mode` | Founder's Office Orchestrator |
| `/revenue-mode` | Revenue Orchestrator |
| `/product-mode` | Product and Delivery Orchestrator |
| `/cx-mode` | Client Experience Orchestrator |
| `/ops-mode` | Operational Reliability Orchestrator |
| `/strategic-mode` | Strategic Growth Orchestrator |

**Crew and system:**

| Command | Action |
|---|---|
| `/list-agents` | View active crew |
| `/add-agent [Name]` | Recruit a new specialist via Eva |
| `/remove-agent [Name]` | Remove an agent via Eva |
| `/brainstorm` | Open exploration mode |
| `/feedback` | Apply system feedback |
| `/help` | Command reference |

Full command reference: [conductor/commands.md](conductor/commands.md)  
Playbooks: [conductor/playbooks/](conductor/playbooks/README.md)
