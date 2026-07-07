# AGENTS.md

> Portable agent doctrine for **{{ASSISTANT_NAME}}**, rendered from the same
> `.tess/core/**` source that produces `CLAUDE.md` for Claude Code (Decision
> #1: *doctrine compiles, never copied* — one core, rendered per harness).
> This file follows the open **AGENTS.md** convention — a README for agents,
> stewarded by the Agentic AI Foundation under the Linux Foundation and read
> natively by Codex, Cursor, GitHub Copilot, Gemini CLI, Zed, Devin, and
> 60,000+ other repositories. If you are an AI coding agent operating inside
> this repository, the rules below are load-bearing, not advisory — treat
> them the same way you would treat a `CLAUDE.md` or a system prompt.

{{CORE_RULE_ZERO}}

{{CORE_HARD_FLOOR}}

{{CORE_SYSTEM_LAWS}}

## Outcome Orchestrators

Serious work is routed through one of six outcome orchestrators before any
crew is assembled — each owns a business outcome, not a task type: Founder's
Office, Revenue, Product and Delivery, Client Experience, Strategic Growth,
Operational Reliability. Full routing doctrine and the crew-plan contract
each orchestrator returns: [conductor/outcome-orchestrators/README.md](conductor/outcome-orchestrators/README.md).
How your harness composes a crew from an orchestrator's plan (native
sub-agents, sequential sessions, or manual hand-off) is harness-specific —
this file only pins the routing/outcome layer, not the dispatch mechanics.

## Command Reference

{{HARNESS_NOTE}}

{{COMMAND_TABLE}}

Full command reference (natural-language equivalents + doctrine flow):
[conductor/commands.md](conductor/commands.md).

{{CORE_DIRECTORY}}

## Further Reading

| Document | Purpose |
|---|---|
| [conductor/identity.md](conductor/identity.md) | Who {{ASSISTANT_NAME}} is and what she is not |
| [conductor/doctrine.md](conductor/doctrine.md) | Full operating doctrine — dependency gates and node types |
| [conductor/guardrails.md](conductor/guardrails.md) | Non-negotiable behavioural rules |
| [conductor/dispatch-brief.md](conductor/dispatch-brief.md) | Dispatch Brief Contract — 6 required fields for every dispatch |
| [conductor/verification-routing.md](conductor/verification-routing.md) | Mandatory verifier routing for prod/client/external outputs |
| [conductor/subagent-failure-protocol.md](conductor/subagent-failure-protocol.md) | Typed retry loop — cause classification, 3-attempt cap, escalation |
| [adapters/README.md](adapters/README.md) | The render-target seam that produced this file |

---

This file is a compiled artifact — regenerate it with `tessctl render
--target codex` / `--target generic` after any doctrine change under
`conductor/**`, never hand-edit it directly (hand-edits are flagged as
uncaptured drift by `tessctl doctor`/`verify`).
