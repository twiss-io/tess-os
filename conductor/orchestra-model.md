# The Orchestra Model — Conductor, Crew-Plans, and the Single Dispatcher

> System doctrine. Defines how ~165 agents coordinate under one dispatcher. Resolves the orchestrator dispatch-contradiction: in Claude Code a subagent **cannot** spawn subagents, so an outcome orchestrator cannot "activate crew" — it returns a **crew-plan** that Tess (the main loop) or a **Workflow** dispatches. Composes with [dispatch-brief.md](dispatch-brief.md), [doctrine.md](doctrine.md) gates, and [verification-routing.md](verification-routing.md). Authored 2026-06-27; source defect: `kb/wiki/synthesis/2026-06-26-tess-starter-review.md` §1.3, §4 (the tess-starter review).

---

## 1. The Platform Constraint That Forces This Model

Claude Code has exactly one agent-spawning surface: the **Agent/Task tool**, and it is held only by the **top-level loop**. A subagent — any `.claude/agents/*` definition Tess dispatches — runs in its own context with its own tools, but **it has no Agent/Task tool and cannot dispatch a further subagent.** Dispatch is **one level deep, always.**

This is not a limitation to route around; it is the spine of the model. It means there is **exactly one conductor** and the orchestra is **flat**: the conductor plays every player directly. The previous doctrine told six orchestrators to "activate crew" and "dispatch agents" — instructions a subagent physically cannot execute. That made the orchestration layer's defining behavior unperformable. This document replaces "the orchestrator dispatches" with "the orchestrator **plans**; the conductor **dispatches**."

### The two valid conductors

| Conductor | What it is | When it leads | Depth |
|---|---|---|---|
| **Tess (main loop)** | The interactive top-level agent | Default for every mission; all interactive work | Dispatches subagents one level deep, in sequence or parallel batches |
| **Workflow** | A scripted harness (e.g. a saved workflow / WDK-style runner) driving the same Agent tool | Larger or repeatable missions needing staged/parallel sections, retries, and durable state | Dispatches subagents one level deep, organised into stages and parallel sections |

Both are **sole dispatchers** in their run. An orchestrator is never either of these — it is a **player that returns sheet music** (a crew-plan).

---

## 2. Roles in the Orchestra

| Role | Who | Holds Agent/Task tool? | Job |
|---|---|---|---|
| **Conductor** | Tess, or a Workflow | **Yes (only it)** | Dispatches every agent, enforces gates, runs verification + retries, holds mission state, talks to the operator on Telegram |
| **Routing brain** | The 6 outcome orchestrators | No | Owns an outcome; **returns a crew-plan** (who, order, briefs, gates, verifier); later synthesises returned artifacts |
| **Player** | The ~165 specialist agents (42 dispatchable today; the rest persona specs Eva can promote) | No | Executes one brief from genuine expertise; returns primary artifacts |
| **Verifier** | Reid / Quinn / Cyra / Verity / Maialen / Lysandra | No | Reads **primary artifacts** (never Tess's summary) and returns a verdict per [review-output-standards.md](review-output-standards.md) |

"Synchronous orchestra" means: the conductor brings players in on cue (gate-satisfied), runs independent players **together** (one parallel batch), waits for the section to land, then brings in the next. Nobody plays out of turn; nobody plays themselves.

---

## 3. The Crew-Plan Contract

A crew-plan is the **return value** of an orchestrator's PLAN pass. It is structured data the conductor can execute mechanically. It is not prose; it is a dispatch program.

### 3.1 Required shape

```yaml
crew_plan:
  mission_id: <string>                 # ties to mission-states record
  outcome_owner: <orchestrator name>   # who owns the outcome (this orchestrator)
  outcome_type: decide|design|build|convert|recover|govern|review|communicate|scale
  notes: <string>                      # framing the conductor needs before dispatch

  stages:                              # ordered; stage N+1 starts only when stage N's gate clears
    - stage: 1
      gate_in: <gate that must be satisfied to start this stage>   # see doctrine.md gates
      parallel: true|false             # may all tasks in this stage run in one dispatch batch?
      tasks:
        - id: <slug>                   # unique within the plan
          agent: <dispatchable agent name>      # e.g. leah, ada, athena
          role: Owner|Core Contributor|Reviewer|Control|Standby
          depends_on: [<task id>, ...] # intra-mission edges; [] if none
          brief:                       # the six-field Dispatch Brief Contract — VERBATIM REQUIRED
            objective: <one sentence success for THIS agent>
            output_contract: <file path + format + required sections>
            tools_sources_constraints: <tools; PRIMARY ARTIFACTS to read by path/URL; constraints; evidence requirement>
            not_responsible_for: <the one boundary line>
            milestones: <deliverable + named acceptance-evidence artifact + owner>   # required if >15min or prod-touching
            escalation_trigger: <condition that stops the agent and surfaces to the conductor>
          verifier:                    # null only if internal-only AND not irreversible
            agent: Reid|Quinn|Cyra|Verity|Maialen|Lysandra
            required: true|false       # true for prod-touching / client-facing / externally-visible / irreversible-informing
            primary_artifacts: [<path/url the verifier must read itself>]

  synthesis:
    owner: <orchestrator name | tess>  # who writes the 10-section memo on the SYNTHESIS pass
    format: output-framework.md/10-section
    inputs: [<task ids whose artifacts feed synthesis>]

  escalations:                         # conditions that bounce the whole mission back to Tess/the operator
    - <condition>
```

### 3.2 Rules the plan must satisfy (the conductor rejects a plan that violates these)

1. **Every task carries a full six-field [dispatch brief](dispatch-brief.md).** No "dispatch a general-purpose agent" without the six fields. Missing fields = the same warn-mode signal the brief validator raises.
2. **Every `agent` is a real, dispatchable definition** (`.claude/agents/*`). If the needed specialist does not exist, the plan names a **general-purpose agent** with a complete brief **and** a `flag_for_tess: source <capability>` so the gap is logged (this is how the current analytics / M&A / legal / finance gaps are handled honestly).
3. **`gate_in` references a real gate** from [doctrine.md](doctrine.md): intake-before-anything, research-before-build, crew-before-deploy, review-before-synthesis, verification-before-externally-visible. No stage may start before its gate clears.
4. **`verifier.required: true`** for any task that is prod-touching, client-facing, externally-visible, or informs an irreversible decision ([verification-routing.md](verification-routing.md)). The verifier's `primary_artifacts` are the real outputs, never a summary.
5. **≤ 4 guilds** per orchestrator mission (the anti-sprawl cap). More than 4 → the plan's `escalations` must carry "exceeds 4-guild cap → escalate to Tess."
6. **One outcome owner.** Exactly one `outcome_owner`; no co-owners.
7. **Parallelism is explicit.** `parallel: true` asserts the tasks share no state and have no intra-stage `depends_on` edges — the conductor dispatches them in a single batch.

### 3.3 Minimal worked example (Revenue Orchestrator, "pipeline conversion is dropping")

```yaml
crew_plan:
  mission_id: 2026-06-27-rev-conv-001
  outcome_owner: revenue-orchestrator
  outcome_type: recover
  notes: Diagnose the conversion drop before any intervention; analytics gap → general-purpose agent, flag to source.
  stages:
    - stage: 1
      gate_in: intake-complete
      parallel: true
      tasks:
        - id: pipeline-data
          agent: general-purpose            # NOTE: no dispatchable Analytics specialist
          role: Core Contributor
          depends_on: []
          brief:
            objective: Quantify where in the funnel conversion is dropping, stage by stage.
            output_contract: /tmp/.../conv-analysis.md — sections [Funnel table, Drop-off stage, Evidence]
            tools_sources_constraints: Read the CRM export at <path>; every number traces to a quoted row; inference labelled.
            not_responsible_for: Recommending fixes (that is stage 2).
            milestones: Funnel table with per-stage conversion + the source rows quoted.
            escalation_trigger: Export missing or stages unmappable → stop, surface to conductor.
          verifier: { agent: Verity, required: true, primary_artifacts: [<crm export path>] }
          flag_for_tess: source a dedicated Analytics specialist
        - id: offer-read
          agent: apolline
          role: Owner
          depends_on: []
          brief: { objective: ..., output_contract: ..., tools_sources_constraints: ..., not_responsible_for: ..., milestones: ..., escalation_trigger: ... }
          verifier: { agent: null, required: false, primary_artifacts: [] }
  synthesis:
    owner: revenue-orchestrator
    format: output-framework.md/10-section
    inputs: [pipeline-data, offer-read]
  escalations:
    - Conversion drop traces to a product defect → hand to Product & Delivery Orchestrator.
```

---

## 4. The Conductor Loop

This is what Tess (or a Workflow) executes. It is the only place dispatch happens.

```
1. INTAKE (Tess)            frame the mission; classify Simple vs full (doctrine.md);
                            decide owner. Simple Task Path → skip steps 2–3, dispatch directly.
2. PLAN (dispatch ×1)       dispatch the chosen outcome orchestrator in PLAN mode.
                            It RETURNS a crew_plan. It dispatches nothing.
3. VALIDATE PLAN (Tess)     check §3.2 rules. On violation: retry the orchestrator with a
                            CHANGED brief (subagent-failure-protocol.md), max 3, else escalate.
4. EXECUTE STAGES           for each stage in order:
   a. gate check            confirm gate_in is satisfied; never start early.
   b. dispatch batch        dispatch all parallel:true tasks in ONE message (one level deep);
                            sequential tasks dispatched in dependency order.
   c. collect artifacts     read each returned PRIMARY artifact (never trust the summary).
   d. verify                for every task with verifier.required:true, dispatch the named
                            verifier with the real primary_artifacts (verification-routing.md).
   e. retry on failure      verifier rejection or task failure → classify cause → retry with a
                            CHANGED brief → max 3 attempts → escalate to the operator with per-attempt log.
5. SYNTHESIS (dispatch ×1)  re-invoke the orchestrator in SYNTHESIS mode WITH the collected,
                            verified artifacts attached. It returns the 10-section memo.
                            (Or Tess synthesises directly for lighter missions.)
6. DELIVER (Tess)           Telegram the result; append verdicts to the mission record;
                            update mission-states.
```

Key properties:
- **Dispatch is one level deep at every step.** The orchestrator is dispatched (step 2, step 5); the players are dispatched (step 4); the verifiers are dispatched (step 4d). Nothing a subagent does causes a further spawn.
- **The orchestrator is invoked twice** — once to plan, once to synthesise — because it cannot stay resident driving the crew. Between those two invocations the **conductor** drives the crew. This two-pass shape is the concrete resolution of the contradiction.
- **State lives in the conductor**, not the orchestrator. Each orchestrator invocation is stateless w.r.t. the others; the crew-plan + collected artifacts are the hand-off.

---

## 5. Why a Workflow, and When

Tess's interactive loop handles most missions: dispatch a batch, read results, dispatch the next. But three pressures push larger missions toward a **Workflow** conductor:

1. **Many stages / large fan-out** — a 6-stage, 20-task mission is fragile to drive by hand; a Workflow encodes the stages and parallel sections as code and runs them deterministically.
2. **Durability** — a Workflow can persist mission state across interruptions and resume; the interactive loop cannot.
3. **Repeatability** — recurring missions (e.g. the daily error report) are saved workflows, not re-improvised each time.

A Workflow consumes the **same crew-plan contract** (§3) and runs the **same conductor loop** (§4). The orchestrator does not know or care which conductor executes its plan — that is the point of returning data rather than performing dispatch. Stages map to Workflow steps; `parallel: true` stages map to a Workflow parallel section; `verifier.required` maps to a verification step that gates the next stage.

> **Boundary:** even inside a Workflow, dispatch is one level deep. A Workflow may dispatch an orchestrator and dispatch players, but a dispatched orchestrator still cannot dispatch. The Workflow is the conductor; the orchestrator is still only a routing brain.

---

## 6. How ~165 Agents Coordinate Without Chaos

The roster is large (165 persona specs; 42 dispatchable today). They coordinate as an orchestra, not a free-for-all, through four mechanisms — all owned by the conductor, none requiring agent-to-agent spawning:

1. **Outcome ownership (one per mission).** An orchestrator owns the outcome and authors the single crew-plan. No second plan competes. ([cross-guild-coordination.md](cross-guild-coordination.md) one-owner rule.)
2. **The ≤4-guild cap + stay-out rule.** Most missions touch a handful of players; the cap keeps the section small enough to conduct. Sprawl escalates to Tess rather than silently growing.
3. **Roles, not just names.** Every task carries a role (Owner / Core Contributor / Reviewer / Control / Standby), so two players never collide on the same responsibility and a Control/Reviewer is present where the cost of error is real.
4. **Gates serialise only what must be serial.** Independent players run in one parallel batch; dependent players wait on a gate. The mission graph (intake's output) plus the crew-plan's stages encode exactly which is which.

The 123 non-dispatchable personas are **bench depth**: Eva promotes a persona to a dispatchable definition before the conductor can field it. Until then the crew-plan names a `general-purpose` agent with a full brief and a `flag_for_tess` to source the specialist — the gap is visible, never silently skipped.

---

## 7. Composition With the Rest of the System

| System piece | How the orchestra model composes with it |
|---|---|
| **[Dispatch Brief Contract](dispatch-brief.md)** | Every `tasks[].brief` is a verbatim six-field brief. The plan is rejected if any field is missing — the crew-plan is a *carrier* of dispatch briefs, not a replacement for them. |
| **[Dependency gates](doctrine.md)** | `stages[].gate_in` references the canonical gates. The conductor enforces them at step 4a. Research-before-build, crew-before-deploy, review-before-synthesis, verification-before-externally-visible all hold unchanged. |
| **[Verification routing](verification-routing.md)** | `tasks[].verifier` names the mandatory domain verifier and the primary artifacts it must read. The conductor dispatches the verifier (step 4d) before any externally-visible output. |
| **[Retry protocol](subagent-failure-protocol.md)** | Plan-validation failures, task failures, and verifier rejections all enter the typed retry loop: classify → changed brief → max 3 → escalate. |
| **[Mission states](mission-states.md)** | `mission_id` ties the plan to the FSM record; the conductor advances state as stages clear. |
| **[Simple Task Path](doctrine.md)** | Tightly-scoped single-domain execution skips the orchestrator entirely — Tess dispatches one player directly. No crew-plan needed; the orchestra model is for serious missions. |
| **Telegram** | Only the conductor (Tess) talks to the operator — start, milestones, completion, blockers. Players and orchestrators return artifacts to the conductor; they do not message the operator. |

---

## 8. One-Paragraph Summary

There is exactly one dispatcher per mission: **Tess (the main loop) or a Workflow.** Outcome orchestrators are **routing brains** that, when dispatched in PLAN mode, **return a crew-plan** — a structured dispatch program naming each agent, its order and parallelism, its six-field dispatch brief, its gate, and its mandatory verifier — and then stop, because a Claude Code subagent cannot spawn subagents. The conductor validates the plan, dispatches the crew **one level deep** (parallel where independent, sequential where gated), reads the **primary artifacts**, runs **mandatory verification** and **typed retries**, and finally re-invokes the orchestrator in SYNTHESIS mode with the collected artifacts to produce the 10-section memo. ~165 agents stay coordinated as a synchronous orchestra through one outcome owner, one crew-plan, the ≤4-guild cap, explicit roles, and dependency gates — never through agents spawning agents.
