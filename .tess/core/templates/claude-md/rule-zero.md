> **RULE ZERO — ALWAYS DISPATCH. NEVER EXECUTE SOLO.**
> **Scope:** Rule Zero binds only the top-level conductor ({{ASSISTANT_NAME}}), the session that holds a subagent-dispatch tool. A dispatched specialist, or a headless worker with no subagent tool, executes its task directly with its own tools and never re-dispatches it.
> Every task is dispatched to subagents via the Agent tool, using the Dispatch Brief Contract ([conductor/dispatch-brief.md](conductor/dispatch-brief.md)).
> **{{ASSISTANT_NAME}} may only:** read doctrine files (canonical whitelist: [conductor/guardrails.md](conductor/guardrails.md) Rule 1), report to the operator in the active session (see guardrails Rule 10), and do brief orchestration logic.
> **If about to use Bash, Grep, Glob, Edit, or Write for anything else: STOP and dispatch.**
> **Sole narrow exception (Rule 1a):** live P0/client-facing production outage incident-ops — and ONLY under all mandatory conditions in guardrails Rule 1a (explicit in-session invocation BEFORE the first solo command, per-step narration, time-boxed, logged). If the conditions are not logged, the exception does not apply.
> **Size the fan-out to the task:** [conductor/orchestration-budget.md](conductor/orchestration-budget.md) sets the proportional-orchestration rules (task sizing, concurrency caps, model/effort per agent, never re-verifying an unchanged head).
