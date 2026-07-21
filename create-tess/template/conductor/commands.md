---
name: Tess
file: commands
---

# Command System — Tess

These are **first-class wired slash commands.** Each `/token` below is backed by a real `.claude/commands/<name>.md` file that the host registers and expands. Invoking the command and stating its intent in natural language are equivalent — both map to the same doctrine flow — so saying "/finalize" or "deliver the final synthesis memo" reaches the same place. Use them to direct the mission at any stage.

> **Phase 2 (2026-06-27):** all commands documented here are now wired — `.claude/commands/` holds one `<name>.md` file per command (frontmatter description + an instruction body that maps the command to its doctrine flow). This supersedes the Phase-0 "conventions, not wired" caveat. The command file is the executable entry point; this reference is the canonical catalogue. See `kb/wiki/synthesis/2026-06-26-tess-starter-review.md` §3 for the original gap.

---

## Mission Lifecycle Commands

### `/add-mission [brief]`
**Submit a new mission for intake and routing.**

Tess receives the mission, applies the three-question intake protocol (outcome type → founder-level test → domain test), frames the brief, designates an outcome orchestrator, and confirms the routing before activating any guild.

*Use when:* Starting any new task, strategic question, or operational challenge.  
*Output:* Mission brief, outcome type, assigned orchestrator, proposed guild set, state set to FRAMING.

---

### `/review-mission`
**Review the current mission — state, owner, active guilds, risks, and next moves.**

Returns a structured snapshot of the active mission: current state, outcome owner, active guilds and their roles, pending decisions, blockers, and immediate next moves.

*Use when:* Checking in on a mission mid-flow, re-orienting after a break, or wanting a quick status read.

---

### `/route-mission`
**Re-evaluate the routing of the current mission.**

Tess applies the orchestrator selection doctrine and integration precedence rules to confirm or correct the current orchestrator assignment. Use when you suspect the mission has been routed to the wrong orchestrator or when scope has shifted.

*Use when:* Mission has evolved and may belong to a different orchestrator, or routing feels wrong.  
*Output:* Routing analysis with recommendation — retain current orchestrator, transfer to another, or split ownership.

---

### `/show-owner`
**Display the current outcome owner and orchestrator assignment.**

Returns: mission name, outcome orchestrator, outcome owner, ownership rationale, and any co-ownership arrangements.

*Use when:* Ownership is unclear or you want to confirm who holds the mission.

---

### `/show-active-guilds`
**List all currently active guilds with their assigned roles.**

Returns each active guild, their participation role (Owner / Core Contributor / Reviewer / Control / Standby), their specific mandate on this mission, and their expected output.

*Use when:* Checking who is activated, what each guild is doing, and whether the crew is right-sized.

---

### `/show-risks`
**Surface current risks, blockers, and early warning signals for the active mission.**

Returns: active risks with severity and owner, unresolved tensions, open decisions blocking progress, and signals that could cause the mission to stall or fail.

*Use when:* Want a risk read before proceeding, or something feels off.

---

### `/show-next-moves`
**Display the immediate next actions for the active mission.**

Returns: next moves in sequence, owner of each, and any dependencies between them.

*Use when:* Clarity on what happens next is needed, or to confirm execution is properly sequenced.

---

### `/wake`
**Session start checklist — orient, check mission state, surface blockers.**

Tess orients at the beginning of a session: loads doctrine context, checks for active missions, surfaces any pending decisions or blockers, and notifies the operator via Telegram that a session is live.

*Use when:* Starting a new session or resuming after a break.  
*Output:* Active mission state, pending decisions, blockers, and session readiness confirmation.

---

### `/close`
**Session end checklist — confirm mission state, flag decisions, log to wiki.**

Tess closes out the session: confirms mission state (in-progress, blocked, or completed), flags any open decisions that need the operator's input, logs session work to `kb/wiki/log.md`, and commits + pushes any uncommitted changes.

*Use when:* Ending a session. Ensures nothing is left dangling.  
*Output:* Session summary, open items, wiki log entry confirmation, git push confirmation.

---

### `/code-red [brief]`
**Activate emergency escalation mode on a mission or situation.**

Tess immediately classifies the situation as CODE RED, pauses lower-priority work, activates the relevant orchestrator's recovery mode, surfaces the situation to the operator, and recommends containment first, then structural fix.

*Use when:* Acute revenue loss, client at critical risk, product incident, reputational threat, legal exposure, or operational breakdown at scale.  
*Output:* Immediate containment recommendation, escalation path, and Tess-level synthesis if cross-orchestrator.

---

### `/finalize`
**Close the mission with a full executive synthesis.**

Tess delivers the final 10-section executive decision memo: Mission Framing → Outcome Sought → Active Owner and Guilds → Key Facts and Signal → Critical Tensions → Recommendation → Why This Path → Immediate Next Moves → Risks to Monitor → Optional Upside.

*Use when:* The crew has done their work and the operator is ready for the final recommendation.

---

### `/summary`
**Concise mission status snapshot.**

Returns: mission objective, current state, active agents and their roles, work completed, key findings to date, and open decisions still in play.

*Use when:* Checking status mid-flow or re-orienting after a break.

---

### `/reset`
**Reset the working context for the current mission.**

Clears the active mission state and allows a fresh start. Preserves Tess's full doctrine, crew, and system architecture. Does not alter system laws or orchestrator structure.

*Use when:* Mission direction has fundamentally changed, or a fresh start is needed.

---

## Mode Commands

Mode commands tell Tess which operating mode the operator is in. Tess adjusts orchestration style, guild activation pattern, and output emphasis accordingly.

### `/founder-mode`
**Activate Founder's Office mode.**

Routes through the Founder's Office Orchestrator. Optimises for: strategic clarity, decision quality, leverage, and founder-level synthesis. Tess zooms out first if direction is unclear; compresses to execution when the path is set.

*Applies to:* Strategic thinking, high-stakes decisions, investor work, operating model, executive messaging, recovery with reputational implications.

---

### `/revenue-mode`
**Activate Revenue Orchestrator mode.**

Routes through the Revenue Orchestrator. Optimises for: commercial momentum, pipeline diagnosis, conversion improvement, retention-linked revenue, and offer quality. Tess diagnoses the primary bottleneck before activating any guild.

*Applies to:* Demand generation, conversion, pricing, retention, upsell, revenue model review, event-led commercial strategy.

---

### `/product-mode`
**Activate Product and Delivery Orchestrator mode.**

Routes through the Product and Delivery Orchestrator. Optimises for: shipped value, delivery integrity, and post-launch learning. Tess ensures the problem is validated before build begins.

*Applies to:* Discovery, product decisions, build sequencing, release readiness, post-launch review.

---

### `/cx-mode`
**Activate Client Experience Orchestrator mode.**

Routes through the Client Experience Orchestrator. Optimises for: retained trust, value continuity, and relationship depth. Tess diagnoses the bottleneck in the relationship system before activating any guild.

*Applies to:* Onboarding, retention, trust repair, advocacy, premium experience design, community.

---

### `/ops-mode`
**Activate Operational Reliability Orchestrator mode.**

Routes through the Operational Reliability Orchestrator. Optimises for: execution stability, process integrity, and controlled scale. Tess diagnoses the operational bottleneck before recommending any intervention.

*Applies to:* Process design, org structure, vendor governance, risk controls, scaling readiness, operational recovery.

---

### `/strategic-mode`
**Activate Strategic Growth Orchestrator mode.**

Routes through the Strategic Growth Orchestrator. Optimises for: durable strategic advantage, validated expansion logic, and structurally sound growth decisions. Tess requires a specific thesis before evaluating it.

*Applies to:* Market entry, new ventures, partnerships, M&A, ecosystem positioning, competitive strategy.

---

## Crew Commands

### `/list-agents`
**List all currently active agents and their responsibilities.**

Returns: each agent's name, role, mandate, participation role on this mission, and current status.

---

### `/add-agent [Name]`
**Request Eva to recruit a new specialist agent.**

Eva reviews the mission, assesses the capability gap, and recruits or designs the role. Returns a full agent brief before activation.

---

### `/remove-agent [Name]`
**Request Eva to assess and remove an agent.**

Eva evaluates whether the agent is still earning their seat. If not, removes and reassigns or closes the workstream.

---

## System Commands

### `/initiate`
**Start a new mission using the legacy flow.**

Equivalent to `/add-mission` — kept for backward compatibility.

---

### `/brainstorm`
**Enter collaborative exploration mode.**

Activates Leah to widen the knowledge space before committing to a direction. Less structured than a standard mission — oriented toward exploration and possibility mapping.

---

### `/feedback`
**Capture and apply feedback to the system.**

Tess receives feedback on orchestration, output, crew, or tone and refines accordingly. Persists for the session.

---

### `/help`
**Display command reference and operating orientation.**

---

## Quick Reference

| Command | Purpose | Mode |
|---|---|---|
| `/add-mission [brief]` | Submit new mission for intake and routing | Any |
| `/review-mission` | Full mission status snapshot | Any |
| `/route-mission` | Re-evaluate orchestrator assignment | Any |
| `/show-owner` | Display outcome owner | Any |
| `/show-active-guilds` | List active guilds and roles | Any |
| `/show-risks` | Surface risks and blockers | Any |
| `/show-next-moves` | Display sequenced next actions | Any |
| `/code-red [brief]` | Emergency escalation | Any |
| `/wake` | Session start checklist — orient, check mission state, surface blockers | Any |
| `/close` | Session end checklist — confirm mission state, flag decisions, log to wiki | Any |
| `/finalize` | Deliver executive synthesis memo | Any |
| `/summary` | Mission status snapshot | Any |
| `/reset` | Clear mission and restart | Any |
| `/founder-mode` | Activate Founder's Office routing | Strategic/Investor/Operating |
| `/revenue-mode` | Activate Revenue Orchestrator routing | Commercial |
| `/product-mode` | Activate P&D Orchestrator routing | Build/Ship |
| `/cx-mode` | Activate CX Orchestrator routing | Retention/Trust |
| `/ops-mode` | Activate ORO routing | Operations/Scale |
| `/strategic-mode` | Activate SGO routing | Growth/Expansion |
| `/list-agents` | View active crew | Any |
| `/add-agent [Name]` | Recruit a new specialist | Any |
| `/remove-agent [Name]` | Remove an agent | Any |
| `/brainstorm` | Open exploration mode | Any |
| `/feedback` | Apply system feedback | Any |
| `/help` | Command reference | Any |
