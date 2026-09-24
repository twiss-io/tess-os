# Orchestration Budget

Agent fan-out is the largest cost in this system. Each spawned agent reloads the full instruction set, the skills list and the agent roster before it does any work. A multi-agent workflow on the top model at maximum effort can use millions of tokens in minutes. These rules keep orchestration proportional to the task.

## 1. Rule Zero is scoped to the top-level conductor
"Always dispatch" applies **only** to the top-level conductor session. A dispatched specialist (subagent, workflow agent, teammate) executes its task directly with its own tools and **never** re-delegates, spawns agents, or replies "I will wait / follow up". Every dispatch brief says so.

## 2. Size the orchestration to the task
| Task | Orchestration |
|---|---|
| Question, lookup, known answer, one-file change | One agent, or answer directly from doctrine/memory |
| Normal build or fix | One builder + one verifier |
| Wide audit, migration, multi-area build | A workflow, and only when the operator asks for breadth or the work truly spans independent areas |
- Default cap: **6 concurrent agents** per workflow unless the operator raises it.
- Declare **model and effort per agent**: the cheaper model at normal effort for mechanical work (grep, git, formatting, file moves, measurements); the top model only for design, security review and hard judgement.
- A session setting such as "ultracode"/maximum effort multiplies every rule above. When the operator reports usage running out, drop to normal effort and say so.

## 3. Verification is proportional
The mandatory verifier applies to production-touching, client-facing and externally visible outputs (see verification-routing). Internal drafts, research notes and reversible local changes get the builder's own tests, not a second agent. **Never re-verify a head that has not changed.** A retry needs a changed brief.

## 4. Never message an agent inside a workflow
Sending a message to an agent that belongs to a running workflow can **resume a second copy** with the same id, which puts two writers on one worktree. Give workflow agents their instructions through a shared decisions file they already read (e.g. `handoffs/ORCHESTRATOR-DECISIONS.md`), or in the next stage's prompt. To change course, stop the workflow and resume it with an edited script.

## 5. One writer per worktree or branch
Each worktree/branch has exactly one owning agent. An agent that finds another writer stops and reports; it does not keep writing.

## 6. Resume and restart discipline
- Before restarting a workflow, check which agents already finished. Resume by run id so finished agents replay from cache, and don't relaunch from scratch.
- A resumed workflow may still re-run stages whose inputs changed. Budget for it.
- Don't restart a design run to add a requirement. Put the requirement in the next stage.

## 7. Budget checkpoints
Before any fan-out of more than 3 agents, the conductor states in one line how many agents it will run and on which model/effort. If the operator reports the budget running low, save state to git first (handoff + commit + push), then pause further fan-out.

## 8. Retire long-lived agents; context growth is the hidden cost
Every turn of an agent re-reads its whole conversation, so cost per turn grows with the agent's age. In a measured 14-day sample, about 97% of all tokens were cache reads, and the costliest agents were subagents kept alive for days across thousands of turns. Rules:
- An agent ends when its task ends (PR merged, answer delivered). Don't keep one parked for "the next thing".
- For long work, hand off: write state to git, then start a fresh agent from the handoff instead of continuing a very long transcript. Start fresh at about 300 turns or when the context feels heavy.
- No hook may make every agent completion trigger extra model work (e.g. a PostToolUse hook forcing a notification after each Agent call).
