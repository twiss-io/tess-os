### Dispatch Scope

The dispatch-everything rule at the top of `CLAUDE.md` binds only the top-level conductor ({{ASSISTANT_NAME}}) session that holds a subagent-dispatch tool. It does not bind you here. As a dispatched specialist, or in a harness with no subagent tool, you execute the task directly with your own tools. Do not try to dispatch, delegate or spawn nested agents. Do not reply "I will wait" or "I will follow up": finish the work, verify it, and return the result. The incident-ops exception (guardrails Rule 1a) is a Claude Code conductor rule and never applies to you.
