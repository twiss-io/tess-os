# Generic render target — interoperability baseline

Implementation: `GenericRenderTarget` in `.tess/bin/tessctl`
(`name = "generic"`, registered in `RENDER_TARGETS`).

This target emits the portable minimum: an `AGENTS.md` file plus a plain
mirror of this project's commands. Hosts may choose to read `AGENTS.md`, but
their discovery, tool permissions, command handling, and subagent behavior
remain host-specific. `generic` is not proof of native integration or feature
parity for every tool that recognizes the convention.

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

Not enabled by default — unlike `codex` (enabled in this repo's own
manifest as of issue #118), no target-specific consumer of the plain
`prompts/**` mirror has been validated yet (`tess.manifest.json`'s
`render_targets._doc`). Preview with `tessctl render --target generic`, or
add `"generic"` to `render_targets.enabled` to opt in permanently.

## Capability tier

Tier C (adapters/README.md "Capability tiers"): rules-file-only assistants
(Cursor, Copilot-class) get doctrine + the gate spine via AGENTS.md, with no
orchestration/dispatch mechanics assumed. This is the floor every harness
gets for free — `codex`/`claude-code` layer harness-specific mechanics
(native prompts, subagent dispatch) on top of the same doctrine.

## Governance boundary

Generic rendering emits `AGENTS.md` and prompt mirrors only. It does not
configure CI, branch protection, a verifier or sign-off trust root, or native
gate enforcement for any host. Do not treat rendered files as approval or a
bootstrap instruction; use the ref-bound diagnostics in
[Gate operation and custody](../../docs/GATE_QUICKSTART.md) instead.

## Doctrine profile (G3, 2026-07-08)

`GenericRenderTarget.doctrine_profile == "worker"` — same lean AGENTS.md
payload `codex` renders (byte-identical, see "AGENTS.md ownership" above),
for exactly the same reason: no orchestration doctrine reaches a harness
with no dispatchable crew. See `adapters/README.md` "Doctrine profile" and
`adapters/codex/README.md`'s own note for the full rationale and the
benchmark finding behind it.
