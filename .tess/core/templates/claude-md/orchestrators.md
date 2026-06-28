## Outcome Orchestrator Layer

A coordination layer sits between {{ASSISTANT_NAME}} and the guilds. Every serious mission should be routed through an outcome orchestrator before activating guilds directly.

> **Orchestrators are routing brains, not dispatchers.** In Claude Code a subagent cannot spawn subagents — only the top-level loop ({{ASSISTANT_NAME}}) or a Workflow holds the Agent/Task tool. An outcome orchestrator therefore never dispatches a guild; it **returns a structured crew-plan** (which agents, order/parallelism, each with a six-field dispatch brief, gates, and the mandatory verifier) and **{{ASSISTANT_NAME}} — or a Workflow — is the sole dispatcher.** {{ASSISTANT_NAME}} dispatches the crew one level deep, then re-invokes the orchestrator with the collected artifacts for synthesis. Full model: [conductor/orchestra-model.md](conductor/orchestra-model.md).

Full layer doctrine: [conductor/outcome-orchestrators/README.md](conductor/outcome-orchestrators/README.md)

All six orchestrators are promoted managed subagents — dispatchable via `.claude/agents/`.

| Orchestrator | Outcome Owned | Agent File |
|---|---|---|
| Founder's Office | Founder decision quality and strategic momentum | `founders-office-orchestrator` |
| Revenue | Revenue growth and commercial momentum | `revenue-orchestrator` |
| Product and Delivery | Product quality, delivery reliability, product-market fit | `product-delivery-orchestrator` |
| Client Experience | Client retention, satisfaction, and lifetime value | `client-experience-orchestrator` |
| Strategic Growth | Strategic expansion and long-term positioning | `strategic-growth-orchestrator` |
| Operational Reliability | Operational stability and scalable execution | `operational-reliability-orchestrator` |
