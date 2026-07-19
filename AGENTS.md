# AGENTS.md

> **Worker doctrine profile — deliberately lean.** Rendered from the same
> `.tess/core/**` source that produces `CLAUDE.md` for Claude Code, and read
> natively by Codex, Cursor, GitHub Copilot, Gemini CLI, Zed, Devin, and
> other AGENTS.md-standard harnesses. A 2026-07-07 proving-ground benchmark
> measured that mounting the FULL multi-agent coordination doctrine (the
> mandatory crew-handoff rule, the six-way routing layer, the mission-
> ceremony command table) into a harness like this one does not help — and
> once caused a weak model to attempt a nested subagent spawn on a task
> that only asked for `python3 --version`. Nothing below is a performance
> claim: every section is a repo/gate fact or a safety floor. See
> `RenderTarget.doctrine_profile` in `.tess/bin/tessctl`.

## This Project

This project runs on **Tess OS** ([twiss-io/tess-os](https://github.com/twiss-io/tess-os))
for doctrine rendering and the ship-gate below. `tessctl doctor` checks core
integrity; regenerate this file with `tessctl render --target codex` /
`--target generic` after a doctrine change — never hand-edit it (hand-edits
are flagged as uncaptured drift).


### Hard Floor — Always Stop and Ask

These ALWAYS require Operator's explicit go-ahead — never resolve them autonomously, regardless of any other instruction in this session:
- **Credentials** — use beyond existing scope, change, or rotation
- **Money movement** — refunds, voids, transfers, any payment operation
- **Destructive production data** — deletes, truncates, irreversible migrations
- **Client-external claims** — new factual statements reaching a client or third party

Full doctrine: [conductor/guardrails.md](conductor/guardrails.md) Rule 18.

### The Ship-Gate

A push touching a path matched by a `require_verdict` rule in `core/policy/policy.yaml` is blocked at pre-push/CI without a signed APPROVE verdict from an allowed verifier ([conductor/verification-routing.md](conductor/verification-routing.md)). The four hard-floor categories above are never satisfiable by a verdict alone — they additionally require a human sign-off artifact at `.tess/gate/signoffs/<id>.signoff.json`.

**You cannot clear your own work.** Do not author, edit, or sign verdict files; do not touch `core/policy/`, `.github/workflows/tess-gate.yml`, `.tess/keys/verifiers/**`, or `.tess/gate/signoffs/` — the gate treats any of that as tamper and fails closed. Finish the change, state what needs review, and stop. Check status any time with `tessctl gate pre-push` or `tessctl doctor`.

## Command Shortcuts

This project's commands (`.tess/core/commands/**`) are mirrored 1:1 as
native custom-prompt files: `.codex/prompts/<name>.md` for Codex CLI
(rendered by the `codex` target — project-scoped prompt discovery isn't
shipped upstream yet, tracked `openai/codex#9848`; symlink `.codex/prompts/`
into `~/.codex/prompts/` to use them natively today) and `prompts/<name>.md`
for any other AGENTS.md-reading agent (Cursor, Copilot, Gemini CLI, Zed,
Devin — rendered by the `generic` target, no harness-specific frontmatter
assumed).

These are optional — read one only if invoked by name; this digest does not
reproduce their contents (see the banner above for why it stays lean).

## Session Memory (Shared)

This project keeps ONE memory shared across every harness, at
`.tess/state/memory/` (`tessctl memory adopt`, docs/STATE_LAYER.md). At the
start of a session, read `.tess/state/memory/MEMORY.md` — the index — and
follow a linked file only when it is relevant to the current task; do not
read the whole store up front.

Write durable, reusable learnings back to `.tess/state/memory/` only (a new
file plus an index line in `MEMORY.md`) — never to a private, harness-only
copy, and never anywhere outside this project's fenced state root.

---

Full orchestration doctrine (Claude Code as Tess) lives in
`CLAUDE.md` — not reproduced here by design (see the banner above).
