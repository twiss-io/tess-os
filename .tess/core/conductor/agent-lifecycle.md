# Agent Lifecycle and Governance Framework
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

Eva may only create a new agent when all of the following are true:

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

Eva must continuously assess:
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

## 10. Managed Subagent Promotion Governance

Not all agents need to be managed subagents. Doctrine agents are the default.

### Who Decides
**Eva owns all promotion and demotion decisions.** Tess does not promote agents unilaterally.

### Promotion Criteria (all three required)
1. **Tool dependency** — the agent's work materially improves with direct tool access
2. **Execution mandate** — the agent produces outputs, not just perspectives
3. **Mission evidence** — real missions have demonstrated the gap

### What Promotion Means
A promoted agent gets a `.claude/agents/<name>.md` file with:
- Defined tool set (principle of least privilege — only tools the role actually uses)
- Self-contained system prompt condensed from doctrine files
- Model assignment — a model-tier **alias** (`haiku` / `sonnet` / `opus`) matched to the role's stakes, never a pinned dated model id. Omit the field to inherit the session/orchestrator model. Default tier: `sonnet`. (Pinning a specific dated id such as a `claude-*-N-N` string is prohibited — it rots and drifts from the actual agent files, which already use bare aliases.)

### Demotion
Eva may revert any managed subagent to doctrine-only if tool access goes unused or overhead is unjustified.

### Portfolio Rule
The number of managed subagents should remain small and mission-justified. More managed subagents is not better. Clarity and utility are the metrics.

---

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
