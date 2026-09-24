# Roster: Ten Roles + Lens Library

> System doctrine (v0.2). The same roster for every use case: personal, agency and organisation. Supersedes the 150-agent roster, the guild packs and the six outcome-orchestrator agents as *registered agents*. Their substance is kept as lenses.

## The rule

The roster is ten roles. A role is defined by its **permissions, model tier and isolation**, not by its expertise. Expertise comes from **lenses**: short briefs the conductor loads into a role's dispatch when a task needs them. A lens never widens a role's permissions.

Every dispatched role carries the line: *"You are a dispatched specialist: execute directly, never re-delegate or spawn agents."* Only the conductor dispatches (see `conductor/orchestration-budget.md` where installed).

## The ten roles

| # | Role | Name | Permissions and isolation | Model tier | Agent file |
|---|---|---|---|---|---|
| 1 | Conductor | Tess (operator-renameable) | The main session. Plans, loads lenses, dispatches, synthesises. Not a subagent. | session model | none (CLAUDE.md / AGENTS.md) |
| 2 | Builder | Ada | Full tools: code and files, commits on a feature branch. No push, merge, tag or deploy. | default (sonnet) | `.claude/agents/ada.md` |
| 3 | Explorer | Morwenna | Read-only: Read, Grep, Glob, read-only Bash. Search and mapping. | cheaper (haiku) | `.claude/agents/morwenna.md` |
| 4 | Researcher | Leah | Read-only plus web. Cites every source. | strong (opus) | `.claude/agents/leah.md` |
| 5 | Code reviewer | Reid | Read-only. Mandatory verifier for code diffs. | strong (opus) | `.claude/agents/reid.md` |
| 6 | QA | Quinn | Runs tests and probes. No source edits, no push or merge. Mandatory verifier for release readiness. | strong (opus) | `.claude/agents/quinn.md` |
| 7 | Security + approval signer | Cyra | Read-only review of the code; its only write is the verdict file it signs with `tessctl verdict sign` (so its Codex sandbox is workspace-write). Mandatory verifier for security and protected paths. | strong (opus) | `.claude/agents/cyra.md` |
| 8 | Scribe | Clio | Writes only to the brain paths (notes, decisions, KB wiki/conversations). Anti-fabrication: every claim links to its source. | default (sonnet) | `.claude/agents/clio.md` |
| 9 | Release / devops | Vega | Push, tag, publish, deploy: only behind the gate (`tessctl gate`, required verdicts present). | default (sonnet) | `.claude/agents/vega.md` |
| 10 | Designer | Iris | Frontend and design, with the design skills attached. | default (sonnet) | `.claude/agents/iris.md` |

The nine role files are core-managed (`.tess/core/agents-dispatch/`). Claude Code reads them from `.claude/agents/`; the Codex render target compiles the same files to `.codex/agents/<name>.toml` (with `sandbox_mode` from each role's `sandbox:` field). Every starter path (`tessctl roster apply <path>`, and the `create-tess` wizard) installs all nine; the path only changes the suggested default lenses (`.tess/core/roster-paths.json` `default_lenses`).

## Lenses

About 140 former personas (strategists, the six outcome orchestrators, Eva, Verity, Maialen, Lysandra and the guild specialists) are the lens library at `conductor/lenses/` (index: `conductor/lenses/README.md`, mirrored in `docs/LENSES.md`). The long-form persona source stays under `agents/<name>/` as reference.

How the conductor uses them:

1. **Pick the role** by what the task must do (the table above).
2. **Pick at most two lenses** by what the task must know. Add `Lens: conductor/lenses/<name>.md` to the brief.
3. **Pick the verifier** (conductor/verification-routing.md): Reid, Quinn or Cyra, with a lens where the domain needs one.

"Conductor + lens" replaces the old gates that named agents: the research gate is Leah (with a research lens if needed); crew design is the conductor applying the `eva` lens; an outcome orchestrator is the conductor applying that outcome lens (`revenue-orchestrator`, `product-delivery-orchestrator`, ...).

## Organisation roles are not agents

Seats in the operator's organisation (a CFO, a client lead, a team) are **brain entities**: records the brain keeps about people and their decisions. They are never agents and never get an agent file.

## Changing the roster

The ten roles are fixed framework doctrine. To add expertise, write or extend a lens. `tessctl recruit` / `tessctl bench` still move a role between installed and staged, but benching a verifier role breaks mandatory verification; do it only with a reason.
