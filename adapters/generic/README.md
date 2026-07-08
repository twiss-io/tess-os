# Generic render target (Tier C)

Implementation: `GenericRenderTarget` in `.tess/bin/tessctl`
(`name = "generic"`, registered in `RENDER_TARGETS`).

This is the "plug-and-play for any AGENTS.md-reading agent" target: the
[AGENTS.md](https://agents.md) convention — a README for agents, stewarded
by the Agentic AI Foundation under the Linux Foundation — is read natively
by Codex, Cursor, GitHub Copilot, Gemini CLI, Zed, Devin, and 60,000+ other
repositories. `generic` assumes NONE of their harness-specific conventions
(no `.claude/` frontmatter, no Codex config.toml, no bespoke prompt-loader
path) — just the standard file, plus a plain mirror of this project's
commands.

## What it renders

| Live path | Compiled from |
|---|---|
| `AGENTS.md` | `render_agents_md()` — SHARED with the `codex` target (see `adapters/codex/README.md` "AGENTS.md ownership"; byte-identical regardless of which target renders it) |
| `prompts/*.md` | one per `.tess/core/commands/*.md` command body — a plain, tool-agnostic mirror with no harness-specific frontmatter conventions assumed of the reading tool |

Unlike `codex`, this target renders **no config fragment** — there is no
universal config format across "any AGENTS.md-reading agent," so `generic`
intentionally stops at doctrine + a plain prompt mirror.

`GenericRenderTarget.expected_live_bytes()` / `render_generated_paths()`
implement the same drift-checking hooks `codex` does; `prompts/*.md` is
drift-checked the same way `.codex/prompts/*.md` is — via
`_check_untracked_render_generated()` (no individual `tess.lock` entry; see
that function's docstring in `.tess/bin/tessctl`).

## Using the rendered output today

- **AGENTS.md** — read natively at the project root by any of the tools
  named above (subject to each tool's own discovery rules).
- **`prompts/*.md`** — no tool auto-loads this directory as native slash
  commands today (there is no cross-tool standard for a prompts directory
  the way there is for AGENTS.md itself). Treat it as documentation: point
  an agent at `prompts/<name>.md` and ask it to follow the instructions
  there, or wire it into your own tool's rules/prompt mechanism if it has
  one.

## Enabling this target

Not enabled by default — same rollout note as `codex`
(`tess.manifest.json`'s `render_targets._doc`). Preview with
`tessctl render --target generic`, or add `"generic"` to
`render_targets.enabled` to opt in permanently.

## Capability tier

Tier C (adapters/README.md "Capability tiers"): rules-file-only assistants
(Cursor, Copilot-class) get doctrine + the gate spine via AGENTS.md, with no
orchestration/dispatch mechanics assumed. This is the floor every harness
gets for free — `codex`/`claude-code` layer harness-specific mechanics
(native prompts, subagent dispatch) on top of the same doctrine.

## Doctrine profile (G3, 2026-07-08)

`GenericRenderTarget.doctrine_profile == "worker"` — same lean AGENTS.md
payload `codex` renders (byte-identical, see "AGENTS.md ownership" above),
for exactly the same reason: no orchestration doctrine reaches a harness
with no dispatchable crew. See `adapters/README.md` "Doctrine profile" and
`adapters/codex/README.md`'s own note for the full rationale and the
benchmark finding behind it.
