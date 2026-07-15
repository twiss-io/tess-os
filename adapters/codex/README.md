# Codex render target — pilot

> This is a shipped Tess OS render target, not certified native-parity support.
> The driver has not been live-tested against Codex event samples. Treat the
> files below as a project-level pilot and confirm current Codex behavior in
> your environment before relying on them. See
> [Support and status](../../docs/STATUS.md).

Implementation: `CodexRenderTarget` in `.tess/bin/tessctl`
(`name = "codex"`, registered in `RENDER_TARGETS`).

## What it renders

| Live path | Compiled from |
|---|---|
| `AGENTS.md` | `render_agents_md()` — SHARED with the `generic` target (see below) |
| `.codex/prompts/*.md` | one per `.tess/core/commands/*.md` command body (the same 26 files the claude-code target restores to `.claude/commands/*.md`), mirrored verbatim through `apply_token_sub()` |
| `.codex/config.toml` | `.tess/core/templates/agents-md/codex-config.toml.tpl` — `approval_policy = "on-request"`, `sandbox_mode = "workspace-write"` |

`CodexRenderTarget.expected_live_bytes()` and `render_generated_paths()`
implement the interface's drift-checking hooks for all three; see
`_check_untracked_render_generated()` in `.tess/bin/tessctl` for how
`.codex/prompts/*.md` gets drift-checked without an individual `tess.lock`
entry (the underlying `.tess/core/commands/*.md` source is already
base_sha-pinned by the claude-code surface's own `.claude/commands/**`
entries — see that function's docstring for the full reasoning).

## AGENTS.md ownership

`render_agents_md(root)` takes **no harness argument** — it produces
byte-identical output whether called from `CodexRenderTarget` or
`GenericRenderTarget`. This is deliberate: AGENTS.md is a single,
conventionally-named root file; if an install ever enables both `codex` and
`generic` at once (unusual, not forbidden), there is no ordering hazard —
both targets agree on the same bytes, so whichever renders "last" changes
nothing. Each target's *companion* artifacts (`.codex/prompts/**` +
`.codex/config.toml` for `codex`; `prompts/**` for `generic`) are where they
actually differ.

## Using the rendered output today

- **AGENTS.md** — Codex CLI reads this natively at the project root; nothing
  further required.
- **`.codex/config.toml`** — Codex only loads a project-scoped
  `.codex/config.toml` for a project you have explicitly marked *trusted*
  ([Codex config reference](https://developers.openai.com/codex/config-reference)).
  An untrusted project ignores it entirely, so the shipped
  `approval_policy`/`sandbox_mode` defaults can only ever narrow behavior
  below whatever your own `~/.codex/config.toml` already allows.
- **`.codex/prompts/*.md`** — Codex's custom-prompt loader currently reads
  only `$CODEX_HOME/prompts` (defaults to `~/.codex/prompts/`); project-scoped
  prompt discovery (reading `.codex/prompts/` at the project root) is not yet
  shipped upstream — tracked at
  [openai/codex#9848](https://github.com/openai/codex/issues/9848). Until it
  lands, symlink or copy this project's `.codex/prompts/` into
  `~/.codex/prompts/` to use them as native `/name` prompts today:
  ```sh
  ln -s "$(pwd)/.codex/prompts" ~/.codex/prompts/tess-os
  ```
  This is exactly why `tessctl` renders into `.codex/prompts/` (project-root,
  containment-respecting) rather than writing to `~/.codex/prompts/`
  directly — `guarded_write`'s C1 containment check refuses any path that
  resolves outside the project root, by design, regardless of target.

## Enabling this target

Not enabled by default (see `tess.manifest.json`'s `render_targets._doc` —
the future harness-select wizard axis is meant to make this choice
per-install, not the engine). Preview it any time with
`tessctl render --target codex`, or opt in permanently by adding `"codex"`
to `tess.manifest.json`'s `render_targets.enabled` list.

## Determinism and idempotency

Both hold for the same reason they hold for `claude-code`
(`adapters/claude-code/README.md`): every artifact is a pure function of
`.tess/core/**` bytes + operator state, with no absolute/per-machine path
baked into rendered content. See `tests/test_render_targets_codex_generic.py`
for the direct proof (two independent projects with identical core content
render byte-identical `AGENTS.md` and `.codex/prompts/*.md`; two consecutive
`render()` calls on one project produce identical bytes both times).

## Capability tier

Tier B (adapters/README.md "Capability tiers"): Codex has no in-session
subagent tool the way Claude Code / Gemini do — process fan-out via
`codex exec` conducts a crew instead of native sub-agent dispatch. This
target only renders doctrine + prompt artifacts; it does not (and cannot)
change how Codex itself composes a crew from an orchestrator's plan.

## Doctrine profile (G3, 2026-07-08)

`CodexRenderTarget.doctrine_profile == "worker"` (see `adapters/README.md`
"Doctrine profile"). `AGENTS.md`'s payload is deliberately lean (~40-60
rendered lines): environment/gate facts + the ~5-line hard floor, zero
orchestration doctrine (no Rule Zero, no outcome-orchestrator routing, no
26-row command table) — a 2026-07-07 proving-ground benchmark measured that
exact payload as harmful when mounted into a single-agent harness like
Codex. `_check_worker_profile_denylist()` (wired into `doctor`/`verify`/
`lock --check`) fails loud if orchestration doctrine ever leaks back in.
