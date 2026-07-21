# Tess OS: current position and roadmap

This is a current-state document, not a feature checklist for every agent
framework. The project will not claim parity with a provider, SDK, or model
until an adapter and its evidence exist.

## What Tess OS is for

Tess OS is a local governance layer around coding-agent work. Its distinctive
job is to connect repository policy, review evidence, and a delivery gate. It
does not try to be a general model SDK, a hosted workflow service, or proof that
one model produces better code than another.

## Current comparison by capability

| Capability | Tess OS today | Boundary |
|---|---|---|
| Review gate | Local policy/evidence gate with fail-closed behavior for governed paths. | Not production admission control yet: external first-key custody and GitHub required checks are unresolved. |
| Coding-agent integration | Claude Code target/driver; opt-in Codex target/driver; generic `AGENTS.md` output. | Claude is an uncertified preview; Codex is pilot; generic output is not native feature parity. |
| Agent management | Crew-plan contracts, mission gates, validation, retry cap, escalation, and a sequential `tessctl run` loop. | Parallel execution and synthesis are not implemented. |
| Observability | Local JSONL records for selected gate/validation actions and explicit local export. | No hosted telemetry service and no full `run` instrumentation. |
| Memory | `kb/` conventions and a governance model. | No advanced retrieval, ACL, lifecycle, or shared-memory implementation. |
| Cloud coordination | None. | Tess Cloud is planned as a separate optional product. |
| Secret capabilities | A local-first embedded vault/risk-reduction pattern. | Tess Vault is planned as a separate product; no agent-era capability vault is shipped. |
| Platform breadth | A deliberately narrow set of render targets and drivers. | No Perplexity or Gemini Tess-specific adapter; no universal-platform claim. |

## Why the narrower claim matters

MCP, an OpenAI-compatible API, or a provider's model catalogue can make tools
interoperate. They do not establish a trusted review path. Tess OS should call a
surface supported only when it can show which actions are observed, which are
denied, how evidence is bound to artifacts, and how VCS admission is enforced.

That is also why Tess OS does not claim to improve model quality. Its own
benchmarking found no evidence that merely loading the doctrine improves a
single agent's output. The project is useful only to the extent that its policy
and evidence are independently verifiable at the delivery boundary.

## Roadmap, stated without promises

1. Repair the external trust-root and GitHub admission-control prerequisites.
2. Extract a stable provider-neutral core and an adapter conformance suite.
3. Bring Claude and Codex through evidence-backed conformance separately.
4. Add local, scoped memory and task-graph orchestration with privacy controls.
5. Build Tess Cloud and Tess Vault as separately reviewed optional dependents.

Each step needs its own design review and acceptance evidence. A future idea is
not a shipped feature, and a future adapter is not a supported platform.

See [Support and status](STATUS.md) for the source of truth on public claims.
