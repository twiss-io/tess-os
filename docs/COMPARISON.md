---
title: "Tess OS vs. the coding-agent framework landscape"
status: living document — update when a cited fact changes upstream or in this repo
date: 2026-07-07
based_on: docs/competitive-analysis-2026-07-07.md (full sourced analysis, 15 frameworks surveyed)
confidence: high
---

# Tess OS vs. the field

Every row below is either **repo-verified** (a command you can run against this
tree yourself — see [Appendix: how the Tess OS numbers were checked](#appendix-how-the-tess-os-numbers-were-checked))
or **cited** (a link to the primary source). Where Tess OS is behind, this
document says so — a comparison that only shows wins isn't a comparison.

**Category note.** Tess OS is not an application-framework SDK like LangGraph
or CrewAI — those are libraries you write code against to build an agent
application. Tess OS is a **harness-layer governance framework**: it sits on
top of an existing coding agent (today: Claude Code) and adds doctrine plus
deterministic enforcement at the git/CI boundary. Its direct competitive set
is GitHub Spec Kit, Ruflo/claude-flow, and BMAD-METHOD. The SDKs are included
below because they define the feature expectations (durable execution,
tracing, evals, memory) that anyone adopting an agent framework in 2026 now
assumes — and Tess OS should be measured against that bar too, even outside
its own category.

---

## Orchestration

| Framework | What it actually runs |
|---|---|
| **Tess OS** | No mechanical dispatch driver. Six outcome orchestrators + a dispatch-brief contract exist as **doctrine** — markdown a model reads and (in principle) self-enforces. There is no `tessctl run`, no `mission`/`dispatch` subcommand, and no code that mechanically executes the intake → research → crew → build → review → verification gate sequence. *Repo-verified: `tessctl`'s 27 subcommands (`init restore doctor update publish override capture rollback diff render verify approve resolve reset selfupdate lock roster recruit bench identity rename setop pathway vault validate verdict gate`) include no `run`/`mission`/`dispatch` command.* 144 persona specs exist as markdown; only 7 are compiled into `.claude/agents/` (*repo-verified: `find agents -mindepth 1 -maxdepth 1 -type d \| wc -l` → 144; `ls .claude/agents/*.md \| wc -l` → 7*). |
| **GitHub Spec Kit** | A spec-driven pipeline (`/speckit.constitution → specify → plan → tasks → implement`) — no execution engine of its own; the connected coding agent (30+ supported) does the work. [github.com/github/spec-kit](https://github.com/github/spec-kit) |
| **Ruflo / claude-flow v3.6** | A real runtime: queen/worker "hive-mind" swarms over Claude Code, Codex, and other harnesses; 314 MCP tools; claims an 84.8% SWE-bench solve rate. [github.com/ruvnet/ruflo](https://github.com/ruvnet/ruflo) — note the SWE-bench figure is self-reported by the project, not an independent leaderboard result. |
| **BMAD-METHOD** | A role-simulation pipeline (Analyst/PM/Architect/Scrum Master) that produces planning artifacts (PRDs, architecture docs). No execution engine — artifacts are prose handed to the next agent, not machine-checked. |
| **LangGraph 1.0 / CrewAI / Microsoft Agent Framework 1.0** | Real graph/flow/crew runtimes with checkpointer-based durable execution, resumable after a crash, and (LangGraph, MS Agent Framework) native human-in-the-loop interrupts. [changelog.langchain.com/.../langgraph-1-0-is-now-generally-available](https://changelog.langchain.com/announcements/langgraph-1-0-is-now-generally-available) · [docs.crewai.com/en/concepts/flows](https://docs.crewai.com/en/concepts/flows) · [learn.microsoft.com/en-us/agent-framework/overview](https://learn.microsoft.com/en-us/agent-framework/overview/) |

**Where Tess OS is behind:** every competitor in this row that isn't BMAD has
either a real runtime or, in Spec Kit's case, an explicit agent-agnostic
execution contract. Tess OS's orchestration doctrine is currently unenforced
prose — the same gap this document's sibling analysis calls the single
biggest honesty risk in the "ultimate framework" pitch. *(Citation, added
2026-07-08: this is now measured, not just flagged as a risk — our own
benchmark of mounting this doctrine into a single agent's context found zero
quality benefit and a weak-tier regression; see
`proving-ground/reports/2026-07-07.md` and `2026-07-07-fair.md`. Whether the
doctrine helps when it IS enforced by a mechanical multi-agent runtime is a
different, still-untested question.)*

---

## Verification / ship-gate

| Framework | Verification mechanism |
|---|---|
| **Tess OS** | The one row where it leads. `tessctl gate` blocks a `git push` touching a policy-flagged path unless a **committed**, schema-valid, content-bound (`artifact_hashes` = git blob SHA per path), **GPG-signed** `disposition: APPROVE` verdict from an `allowed_verifiers` member covers it; hard-floor categories (credentials, money movement, destructive prod data, client-external claims) are never satisfiable by a verdict at all — only an explicit human sign-off artifact clears them. Fail-closed on every ambiguity (missing policy, unreadable verdict, failed git command = block, never allow). A CI workflow (`tessctl gate ci`) re-runs the same logic as a harness-independent backstop against `git push --no-verify`. *Repo-verified: `core/policy/policy.yaml`, `.tess/bin/tessctl`'s `gate`/`verdict` subcommands, 460 passing tests (`pytest --collect-only -q`).* **Caveat, disclosed in this repo's own policy file:** `verifier_keys` ships **empty** by design — a fresh install cannot produce a valid signed verdict until someone generates and registers a GPG key. First-run friction on the flagship feature is real. **And we published the benchmark where our own doctrine-as-context *lost* to bare models** (2026-07-07, twice — see `proving-ground/reports/`) — no other row in this table has self-run adversarial evidence at all, for or against its own claims. |
| **GitHub Spec Kit** | Ships checklist-style "quality gate" prompts as part of the spec workflow — these are instructions an agent or human can also just skip. Nothing in the tool itself stops a merge of unreviewed output. [github.github.com/spec-kit](https://github.github.com/spec-kit/) |
| **Ruflo / claude-flow** | No fail-closed ship boundary is described in the project's own documentation; verification is folded into the swarm's self-reported quality claims, not a separate gating artifact. [github.com/ruvnet/ruflo](https://github.com/ruvnet/ruflo) |
| **BMAD-METHOD** | No gate. Planning-artifact discipline is strong, but nothing in the method stops unreviewed code from shipping. |
| **App SDKs (OpenAI Agents SDK, Pydantic AI, Mastra, CrewAI)** | Ship "guardrails" / typed validation / evals — these check a single call's input or output against a schema or rule, in-session, while the model is running. None of them produce a **signed, committed, git/CI-enforced artifact** that gates the ship boundary itself. [openai.github.io/openai-agents-python](https://openai.github.io/openai-agents-python/) · [ai.pydantic.dev](https://ai.pydantic.dev/) · [mastra.ai](https://mastra.ai/) |

**Where Tess OS is behind:** the moat feature has zero first-run ergonomics —
no `tessctl verifier keygen`, no 10-minute quickstart, empty `verifier_keys` by
default. A framework whose headline claim is "verified output only" that ships
with no working verifier out of the box is a real credibility gap, not a
footnote.

---

## Portability (harness support)

| Framework | Harness reach |
|---|---|
| **Tess OS** | One harness, wired: Claude Code. A `RenderTarget` adapter seam exists in code (`class RenderTarget`, one registered implementation `ClaudeCodeRenderTarget`) but nothing else is plugged into it — no Codex target, no Gemini target, no generic/AGENTS.md emitter. *Repo-verified: `grep -rn "class.*RenderTarget" .tess/bin/tessctl` shows exactly one subclass; no `AGENTS.md` file exists anywhere in this repo.* The ship-gate itself is a partial exception: because it hooks git pre-commit/pre-push and CI rather than the coding agent, it enforces on a push regardless of which tool authored the diff — but that is a property of *where* the gate sits (the git/CI boundary), not evidence of multi-harness adapters. |
| **GitHub Spec Kit** | Agent-agnostic from day one; 30+ coding agents supported, 55+ releases since Feb 2026. [github.com/github/spec-kit](https://github.com/github/spec-kit) |
| **Ruflo / claude-flow** | Multi-harness by design — Claude Code, Codex, and others. [github.com/ruvnet/ruflo](https://github.com/ruvnet/ruflo) |
| **BMAD-METHOD** | Agent-agnostic in practice — its outputs are plain markdown artifacts any agent that can read a file can consume. |
| **App SDKs** | Mostly single-vendor by construction (LangGraph → LangChain ecosystem, OpenAI Agents SDK → OpenAI). Google ADK is the exception: A2A v0.3 adds a cross-vendor wire protocol (gRPC, signed security cards) for agent-to-agent interop. [google.github.io/adk-docs/a2a](https://google.github.io/adk-docs/a2a/) |

**Where Tess OS is behind:** this is the starkest gap in the whole comparison
— 1 harness vs. Spec Kit's 30+, in a market where [AGENTS.md](https://agents.md/)
(60k+ repos, stewarded by the Agentic AI Foundation — Linux Foundation, Dec
2025, with Anthropic, OpenAI, and Block as founding members) has become the
baseline expectation for "plug-and-play."

---

## Memory

| Framework | Memory story |
|---|---|
| **Tess OS** | `kb/` (`raw/`, `wiki/`, `lint/`) is a **described folder convention**, not tooling — there is no memory API, no retrieval layer, and no code that reads or writes to it programmatically. *Repo-verified: no memory/retrieval module exists in `.tess/bin/tessctl` or `core/`.* |
| **GitHub Spec Kit / BMAD-METHOD** | No dedicated memory system described in either project. |
| **Ruflo / claude-flow** | Claims "shared memory" as part of its swarm feature surface. [github.com/ruvnet/ruflo](https://github.com/ruvnet/ruflo) — not independently verified here. |
| **Letta (MemGPT)** | The most developed memory story surveyed: a 3-tier memory architecture plus **MemFS**, a git-backed memory filesystem that treats agent state as versioned files — the same instinct behind Tess OS's `kb/`, considerably more developed. [docs.letta.com/letta-agent/memory](https://docs.letta.com/letta-agent/memory) |
| **LangGraph** | Checkpointer persistence (SQLite/Postgres) — durable *run state* for resumability, not long-horizon agent memory per se. [docs.langchain.com/oss/python/langgraph/durable-execution](https://docs.langchain.com/oss/python/langgraph/durable-execution) |

**Where Tess OS is behind:** `kb/` is a convention, not a capability. Letta's
MemFS pattern (memory as versioned git files) is directly adoptable by Tess
OS's own architecture and currently isn't built.

---

## Observability

| Framework | Observability story |
|---|---|
| **Tess OS** | None. No tracing, no OpenTelemetry emission, no eval harness, no dashboard. *Repo-verified: no tracing/telemetry module exists in `.tess/bin/tessctl`.* |
| **GitHub Spec Kit / BMAD-METHOD** | None described. |
| **Ruflo / claude-flow** | Claims dashboards/metrics as part of its feature surface. [github.com/ruvnet/ruflo](https://github.com/ruvnet/ruflo) — self-reported, not independently verified here. |
| **CrewAI** | Shipped enterprise observability (OTel export + dashboard) in its 0.105 release, March 2026. [crewai.com/blog/lessons-from-2-billion-agentic-workflows](https://crewai.com/blog/lessons-from-2-billion-agentic-workflows) |
| **OpenAI Agents SDK / Microsoft Agent Framework** | Built-in tracing dashboards and telemetry as first-class SDK features. [openai.github.io/openai-agents-python](https://openai.github.io/openai-agents-python/) · [learn.microsoft.com/en-us/agent-framework/overview](https://learn.microsoft.com/en-us/agent-framework/overview/) |
| **Mastra 1.0** | Bundled observability plus built-in scorers (LLM-judge, rule-based, statistical) that run in CI. [mastra.ai](https://mastra.ai/) |

**Where Tess OS is behind:** this is table-stakes in 2026 — [OpenTelemetry's
GenAI semantic conventions](https://opentelemetry.io/blog/2025/ai-agent-observability/)
are now the industry's shared vocabulary (Datadog, Honeycomb, New Relic all
support them; LangChain, CrewAI, and AutoGen all emit them) — and Tess OS
emits nothing. A file-based JSONL trace mapped to `gen_ai.*` spans would be a
cheap way in; it does not exist today.

---

## Developer experience (first-run)

| Framework | First-run experience |
|---|---|
| **Tess OS** | `npm create tess@latest` — a 5-axis onboarding wizard (name, vibe, squad, conductor name, pathway) that stages to a temp directory, validates against the real roster, and only then promotes atomically (cancel leaves zero state behind). *Repo-verified: `create-tess/` wizard source + its Node test suite (part of the 460 tests referenced above).* Undercut by the verification-gate first-run gap noted above — the headline feature isn't usable in the same one command. |
| **GitHub Spec Kit** | Simple mental model (`specify → plan → tasks → implement`), 55+ releases since Feb 2026, 70+ community extensions. Large distribution advantage. [github.github.com/spec-kit](https://github.github.com/spec-kit/) |
| **Ruflo / claude-flow** | Large feature surface (314 MCP tools, federation, self-learning) — a correspondingly large complexity budget for a new adopter. [github.com/ruvnet/ruflo](https://github.com/ruvnet/ruflo) |
| **BMAD-METHOD** | Popular with teams that want planning-artifact discipline; no tooling to install beyond the method itself. |
| **Pydantic AI / Mastra** | Typed, IDE-friendly DX with evals wired into the development loop from day one. [ai.pydantic.dev](https://ai.pydantic.dev/) · [mastra.ai](https://mastra.ai/) |

**Where Tess OS is behind:** no `tessctl adopt` path for an existing
(non-greenfield) repo — the majority case for a team already mid-project with
a coding agent. Every walkthrough in this repo assumes a fresh clone or
`npm create tess`.

---

## Summary — the honest wedge

Tess OS's one clearly defensible edge across all 15 frameworks surveyed in the
underlying analysis is the **signed ship-gate**: a cryptographically-signed,
fail-closed, content-bound review artifact enforced at the git/CI boundary,
with hard floors no verdict can clear. Nothing else surveyed — inside or
outside its own category — ships an equivalent. Everywhere else in this
table — runtime orchestration, harness portability, memory, observability,
adoption ergonomics — Tess OS is behind, in several cases (harness count,
observability) by a wide margin. The gate spine itself is also not yet on
`main`, and its own first-run key setup is unfinished. Positioning Tess OS as
"the ultimate framework" would not survive this table; positioning it as "the
ship-gate, with everything else still to prove" does.

---

## Appendix: how the Tess OS numbers were checked

Every Tess OS-side number in this document was produced by running a command
against this repository (branch `phase-2b-gate-hardening` / this feature
branch), not by reading a claim and repeating it:

```bash
wc -l .tess/bin/tessctl                                   # 9,147 lines
python3 -m pytest --collect-only -q                       # 460 tests collected
find agents -mindepth 1 -maxdepth 1 -type d | wc -l        # 144 persona directories
ls .claude/agents/*.md | wc -l                             # 7 compiled agent defs
grep -n 'add_parser(' .tess/bin/tessctl | ...              # 27 top-level subcommands
grep -rn "class.*RenderTarget" .tess/bin/tessctl           # 1 subclass: ClaudeCodeRenderTarget
ls AGENTS.md                                               # No such file or directory
grep -A3 "verifier_keys" core/policy/policy.yaml           # DELIBERATELY EMPTY (repo's own comment)
git show origin/main:.tess/bin/tessctl | wc -l             # 6,467 lines (main has no gate spine)
```

Re-run any of these against the branch to confirm before relying on this
document — it is dated 2026-07-07 and will drift as the repo does.

## Sources (competitor claims)

- GitHub Spec Kit: [github.com/github/spec-kit](https://github.com/github/spec-kit) · [github.github.com/spec-kit](https://github.github.com/spec-kit/)
- Ruflo / claude-flow: [github.com/ruvnet/ruflo](https://github.com/ruvnet/ruflo)
- AGENTS.md standard + Agentic AI Foundation: [agents.md](https://agents.md/) · [openai.com/index/agentic-ai-foundation](https://openai.com/index/agentic-ai-foundation/)
- OpenTelemetry GenAI conventions: [opentelemetry.io/blog/2025/ai-agent-observability](https://opentelemetry.io/blog/2025/ai-agent-observability/)
- LangGraph 1.0 GA: [changelog.langchain.com](https://changelog.langchain.com/announcements/langgraph-1-0-is-now-generally-available) · durable execution: [docs.langchain.com](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- CrewAI Flows / observability: [docs.crewai.com/en/concepts/flows](https://docs.crewai.com/en/concepts/flows) · [crewai.com/blog/lessons-from-2-billion-agentic-workflows](https://crewai.com/blog/lessons-from-2-billion-agentic-workflows)
- Microsoft Agent Framework 1.0: [learn.microsoft.com/en-us/agent-framework/overview](https://learn.microsoft.com/en-us/agent-framework/overview/)
- OpenAI Agents SDK: [openai.github.io/openai-agents-python](https://openai.github.io/openai-agents-python/)
- Pydantic AI: [ai.pydantic.dev](https://ai.pydantic.dev/)
- Mastra: [mastra.ai](https://mastra.ai/)
- Letta / MemFS: [docs.letta.com/letta-agent/memory](https://docs.letta.com/letta-agent/memory)
- Google ADK + A2A: [google.github.io/adk-docs/a2a](https://google.github.io/adk-docs/a2a/)

Full sourced analysis (15 frameworks, methodology, and additional tailwind
data — Terminal-Bench harness-gap numbers, etc.):
[`docs/competitive-analysis-2026-07-07.md`](competitive-analysis-2026-07-07.md).
