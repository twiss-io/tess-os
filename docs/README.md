# Tess OS Documentation Index

Start with the [root README](../README.md) — it is the primary, most
up-to-date source for what Tess OS is, the quickstart, and the honest
"Status" section. The documents here go deeper on specific subsystems or
serve a specific audience (release engineering, competitive positioning,
long-range design).

## Start here

| Doc | For |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | A system-layer overview — the doctrine layer, the `tessctl` engine, the gate spine, the vault, and how they compose. Points into the root README's deeper sections rather than duplicating them. |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | How to contribute: workflow, quality gates, licensing terms. |

## Release engineering

| Doc | For |
|---|---|
| [`VERSIONING.md`](VERSIONING.md) | The SemVer policy: what bumps MAJOR/MINOR/PATCH, how `tess.lock`/`pyproject.toml`/`package.json`/`create-tess/package.json` relate, and known version-sync gaps. |
| [`../conductor/release-process.md`](../conductor/release-process.md) | The mechanics of cutting a signed release: the trust model, the maintainer release checklist, and the adopter upgrade flow. |
| [`../CHANGELOG.md`](../CHANGELOG.md) | Every notable change, Keep-a-Changelog format, with an `[Unreleased]` section tracking what has landed on `main` since the last tag. |

## Subsystem deep-dives

| Doc | For |
|---|---|
| [`GATE_QUICKSTART.md`](GATE_QUICKSTART.md) | Copy-paste-able walkthrough of the ship-gate: installing hooks, writing a policy rule, generating a verifier key, signing a verdict. |
| [`OBSERVABILITY.md`](OBSERVABILITY.md) | The mission trace log and OTel GenAI export (`tessctl trace export`) — what's instrumented today and what isn't. |
| [`MCP.md`](MCP.md) | `tessctl mcp serve` — exposing the gate's checks (contract validation, verdict coverage, mission reads, roster reads) as an MCP server for non-Claude-Code harnesses. |

## Positioning and long-range design

| Doc | For |
|---|---|
| [`COMPARISON.md`](COMPARISON.md) | Tess OS vs. GitHub Spec Kit, Ruflo/claude-flow, BMAD, and LangGraph-class app SDKs — sourced, with an explicit "where Tess OS is behind" section. Living document. |
| [`competitive-analysis-2026-07-07.md`](competitive-analysis-2026-07-07.md) | The full sourced research `COMPARISON.md` is built from (15 frameworks surveyed). |
| [`ULTIMATE_FRAMEWORK_PLAN.md`](ULTIMATE_FRAMEWORK_PLAN.md) | The longer-range design document driving the Phase 0/1/2/2b work. **A plan, not a completed-work claim** — carries its own supersession notice on the parts later disproven by `proving-ground/`. |

## Not in this index

- `proving-ground/` (the benchmark harness — see its own `proving-ground/reports/` and the root README's "Honest results" section) and `missions/` (per-project mission records — see `missions/README.md`) are data/tooling directories, not prose docs, and are documented in place rather than here.
