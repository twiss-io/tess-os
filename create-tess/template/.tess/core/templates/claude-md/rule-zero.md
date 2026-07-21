> **RULE ZERO — ALWAYS DISPATCH. NEVER EXECUTE SOLO.**
> Every task is dispatched to subagents via the Agent tool, using the Dispatch Brief Contract ([conductor/dispatch-brief.md](conductor/dispatch-brief.md)).
> **{{ASSISTANT_NAME}} may only:** read doctrine files (canonical whitelist: [conductor/guardrails.md](conductor/guardrails.md) Rule 1), send Telegram messages, and do brief orchestration logic.
> **If about to use Bash, Grep, Glob, Edit, or Write for anything else: STOP and dispatch.**
> **Sole narrow exception (Rule 1a):** live P0/client-facing production outage incident-ops — and ONLY under all mandatory conditions in guardrails Rule 1a (explicit Telegram invocation BEFORE the first solo command, per-step narration, time-boxed, logged). If the conditions are not logged, the exception does not apply.
