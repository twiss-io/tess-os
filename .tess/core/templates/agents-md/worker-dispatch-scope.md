### Roles and Dispatch

Installed roles (`tessctl roster list`; each is `.tess/core/agents-dispatch/<role>.md`): {{WORKER_ROLES}}. Asked who you are or what roles you can use, name these. The dispatch-everything rule at the top of `CLAUDE.md` and the incident-ops exception (guardrails Rule 1a) are Claude Code conductor rules and do not bind you ([conductor/orchestration-budget.md](conductor/orchestration-budget.md) Rule 1).

- Default: do small, clear work yourself. Use a role when the operator names it or its job ("use the research role", "have reid review this") or asks you to delegate.
- Codex: each role is a custom agent, `.codex/agents/<role>.toml`. Call `spawn_agent` with `agent_type` set to the role name and a self-contained `message` (goal, scope, done-when, what to return), without `fork_context` (Codex rejects `agent_type` on a full-history fork). Spawn once, `wait_agent` for its result before any `close_agent`, then relay it and say what you checked.
- If the role will not spawn, never start a generic agent and call it that role: say it could not start and why, then do the work yourself as that role (read its file; follow its Permissions and Return) and say so. Do the same in a runtime with no subagent tool.
- If you are a spawned role ("You are a dispatched specialist"): never spawn or re-delegate; finish, verify and return. Never reply "I will wait" or "I will follow up".
