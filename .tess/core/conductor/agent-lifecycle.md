# Agent Lifecycle and Governance Framework

> **v0.2 ten-role roster ([roster.md](roster.md)).** The registered roster is fixed at ten roles defined by permissions. The portfolio this doctrine governs is now the **lens library** (`conductor/lenses/`): create, merge and retire lenses under these rules; never add an agent file to cover an expertise gap. Where this file says "agent", read "lens" unless it names one of the nine roles.

## Tess's Agent Portfolio Doctrine

Tess's agent realm must be governed as a portfolio, not allowed to grow by accumulation.

Every agent must justify her existence through outcome quality, role clarity, and system usefulness.

> **Single-dispatcher rule (applies to every agent in the portfolio).** In Claude Code a subagent cannot spawn subagents — only the top-level loop (Tess) or a Workflow holds the Agent/Task tool. No agent in this portfolio — **including the outcome orchestrators** — may dispatch, activate, or spawn another agent. An agent that needs other agents (an orchestrator, a guild lead) **returns a crew-plan** naming them with dispatch briefs; **Tess or a Workflow is the sole dispatcher.** "Activated" as an agent status (below) means *Tess has dispatched this agent on a live mission*, not that the agent dispatched itself. Full model: [orchestra-model.md](orchestra-model.md).

---

## 1. Agent Status Types

Every agent must have one of the following statuses:

### Core
Permanent, foundational agents essential to the operating system.

### Active
Currently activated on a live mission.

### Standby
Relevant to a mission or outcome area, but not currently active.

### Temporary
Created for a specific mission or narrow short-term need.

### Experimental
Newly created and not yet proven reliable or necessary.

### Dormant
Previously useful but not currently needed.

### Deprecated
No longer fit, no longer necessary, or superseded by better structure.

---

## 2. Agent Lifecycle Stages

Every agent must move through the following possible stages:

1. propose
2. design
3. pilot
4. certify
5. operate
6. review
7. narrow, merge, split, or retire

### Lifecycle Principle
No agent should become permanent by accident.

---

## 3. Agent Creation Rule

The conductor (applying the `eva` lens) may only create a new lens when all of the following are true:

- an important capability gap exists
- no current agent can credibly cover the role
- the role materially improves mission quality
- the role has a clear reason to exist beyond novelty
- the role will not create confusing overlap
- the expected value exceeds the added governance complexity

### Creation Principle
Do not create a new agent to satisfy naming elegance or organisational vanity.  
Create only when capability clarity requires it.

---

## 4. Naming Discipline Rule

All agent names must follow strict anti-confusion rules.

### Naming Rules
- no exact duplicates
- no one-letter-apart names
- no near-identical phonetic pairs
- no repeated prefix clusters beyond a safe threshold
- no adjacent guilds with highly similar names
- all approved names must be checked against the full reserved-name registry

### Naming Principle
Names are part of routing quality.  
Poor naming creates silent orchestration errors.

---

## 5. Overlap and Redundancy Rule

The conductor (applying the `eva` lens) must continuously assess the lens library:
- whether agents overlap too heavily
- whether two agents should be merged
- whether one agent has become too broad and should be split
- whether a role is decorative rather than useful
- whether a dormant agent should remain dormant or be deprecated

### Overlap Principle
The existence of two smart agents is not proof that both should exist.

---

## 6. Agent Review Cadence

All non-trivial agents must be reviewed periodically.

### Review Questions
- Does this agent improve outcomes materially?
- Is the mandate still sharp?
- Is the agent activated for the right reasons?
- Is there role confusion?
- Should this role be narrower, broader, split, merged, or retired?
- Is this still a core need or only a legacy artifact?

### Review Outcomes
- retain
- narrow
- broaden
- split
- merge
- move to dormant
- deprecate
- redesign and re-pilot

---

## 7. Performance Scorecards

Every agent should be assessed across three dimensions:

### Outcome Value
Did this agent improve the mission outcome?

### Orchestration Fit
Did this agent participate at the right times, in the right way, with clear boundaries?

### Quality of Contribution
Was the contribution sharp, useful, differentiated, and worth the added complexity?

### Scorecard Principle
Do not assess agents by output volume.  
Assess them by usefulness, clarity, and outcome lift.

---

## 8. Temporary Agent Rule

Temporary agents must:
- have a narrow mandate
- be linked to a defined mission
- be reviewed after the mission ends
- not be retained automatically
- either be retired, redesigned, or certified intentionally

### Temporary Principle
Temporary agents are a tool, not a shortcut to uncontrolled sprawl.

---

## 9. Core Agent Protection Rule

Core agents should be:
- few
- durable
- high-clarity
- structurally important
- reviewed less often, but more seriously

Core status must be earned, not granted casually.

---

## 10. Registered Roles (v0.2 — replaces managed-subagent promotion)

There is no promotion path in v0.2. The registered agents are exactly the nine roles in [roster.md](roster.md), each with a `.claude/agents/<name>.md` file defined by permissions (least-privilege tool set), model-tier alias (`haiku` / `sonnet` / `opus`, never a pinned dated id) and isolation. Expertise that once justified promoting a persona is now a lens in `conductor/lenses/`, loaded into a role's brief. Nobody (conductor or lens) creates a new agent file; a gap that needs a permission the roles lack goes to the operator.

**Distinct from `model_tier` (roster metadata):** the `model:` alias is the harness-concrete setting Claude Code reads at dispatch time; `model_tier` in `agents/README.md` is the coarser role-based recommendation it follows.

## 11. Agent Portfolio Principle

Tess's realm must behave like a disciplined portfolio of specialist intelligence.

The goal is not to maximise agent count.  
The goal is to maximise:
- capability clarity
- routing quality
- outcome improvement
- reusability
- governance discipline
- long-term system sharpness
