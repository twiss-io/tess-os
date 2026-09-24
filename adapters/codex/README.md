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
| `.agents/skills/tess-<name>/SKILL.md` | one Agent Skill per `.tess/core/commands/*.md` command body (the same 26 files the claude-code target restores to `.claude/commands/*.md`) — `render_agent_skill_md()`: frontmatter `name` (`tess-<name>`, equal to the directory name) and `description` (the command's own), then the body through `apply_token_sub()` with relative links rebased onto the skill directory |
| `.agents/skills/tess-<name>/agents/openai.yaml` | `render_agent_skill_openai_yaml()` — `policy: allow_implicit_invocation: false`, so Codex runs a Tess command only when the user names it (`$tess-<name>`), the way a Claude Code slash command works |
| `.codex/config.toml` | `.tess/core/templates/agents-md/codex-config.toml.tpl` — `approval_policy = "on-request"`, `sandbox_mode = "workspace-write"` |

`CodexRenderTarget.expected_live_bytes()` and `render_generated_paths()`
implement the interface's drift-checking hooks for all of them; see
`_check_untracked_render_generated()` in `.tess/bin/tessctl` for how the
skills get drift-checked without an individual `tess.lock` entry (the
underlying `.tess/core/commands/*.md` source is already base_sha-pinned by
the claude-code surface's own `.claude/commands/**` entries).

It does **not** render `.codex/agents/` or `.codex/hooks.json`: no Tess hook
runs inside Codex in this release. See [`../CONFORMANCE.md`](../CONFORMANCE.md)
for what that means for enforcement (Codex is Partial).

### Retired: `.codex/prompts/`

Before v0.2.0 this target mirrored the commands into `.codex/prompts/*.md`.
Codex never loads a project-scoped prompts directory — the feature request
was closed as not planned
([openai/codex#9848](https://github.com/openai/codex/issues/9848)) — so those
files did nothing. They are no longer rendered or owned. `CodexRenderTarget.
retired_paths()` lists them, and `tessctl render` prints one `retired` line
while any still exist. Nothing deletes them: remove them yourself once the
skills work for you.

## AGENTS.md ownership

`render_agents_md(root)` takes **no harness argument** — it produces
byte-identical output whether called from `CodexRenderTarget` or
`GenericRenderTarget`. This is deliberate: AGENTS.md is a single,
conventionally-named root file; if an install ever enables both `codex` and
`generic` at once (unusual, not forbidden), there is no ordering hazard —
both targets agree on the same bytes, so whichever renders "last" changes
nothing. Each target's *companion* artifacts (`.agents/skills/tess-*/` +
`.codex/config.toml` for `codex`; `prompts/**` for `generic`) are where they
actually differ.

## Using the rendered output today

- **AGENTS.md** — Codex reads it natively: one file per directory from the
  git root down to cwd, up to 32 KiB in total including your own
  `~/.codex/AGENTS.md`
  ([AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md.md)).
  The rendered worker profile stays at or under 12,000 bytes.
- **Skills** — Codex scans `.agents/skills` in every directory from cwd up to
  the repo root ([skills](https://learn.chatgpt.com/docs/build-skills.md)).
  Run a command with `$tess-wake` (or pick it from `/skills`). Because of the
  explicit-only policy, the model does not see Tess commands in its implicit
  skill list; that keeps the orchestration commands out of a worker
  session's context unless you ask for one.
- **`.codex/config.toml`** — Codex only loads a project-scoped
  `.codex/config.toml` for a project you have explicitly marked *trusted*
  ([Codex config reference](https://learn.chatgpt.com/docs/config-file/config-reference.md)).
  An untrusted project ignores it entirely, so the shipped
  `approval_policy`/`sandbox_mode` defaults can only ever narrow behavior
  below whatever your own `~/.codex/config.toml` already allows.

### Upgrading an install made before v0.2.0

An older `tess.manifest.json` fences off `.agents/**` (never_touch) and owns
`.codex/prompts/**` instead. `tessctl render` then skips the skills
(`skipped ... not-owned`) and prints the one line to add. Add this entry to
`owned_globs` yourself — `tessctl` never rewrites your manifest:

```json
".agents/skills/tess-*/**"
```

The glob covers only the `tess-` prefix, so skills you author under
`.agents/skills/` stay out of the write gate's reach (owned_globs wins over
never_touch for that prefix only).

## Enabling this target

Enabled by default in this repo's own `tess.manifest.json` (issue #118 — a
deliberate, reviewed manifest edit, not the engine auto-enabling a
newly-registered target; see `render_targets._doc`). A different install
that never edited its own manifest to add `"codex"` is unaffected — the
future harness-select wizard axis is meant to make this choice per-install,
not the engine. Preview it any time with `tessctl render --target codex`
regardless of enablement, or edit `tess.manifest.json`'s
`render_targets.enabled` list yourself to opt in or out.

## Determinism and idempotency

Both hold for the same reason they hold for `claude-code`
(`adapters/claude-code/README.md`): every artifact is a pure function of
`.tess/core/**` bytes + operator state, with no absolute/per-machine path
baked into rendered content. See `tests/test_render_targets_codex_generic.py`
and `tests/test_v02_codex_skills.py` for the direct proof (two independent
projects with identical core content render byte-identical `AGENTS.md` and
skills; a second render leaves `git status --porcelain` empty).

## Capability tier

Tier B (adapters/README.md "Capability tiers"). Codex now documents its own
subagents (`.codex/agents/*.toml`, the `spawn_agent` tool —
[subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents.md)),
but Tess renders no Codex agent roster, so a Codex session reading this
project has no Tess crew to dispatch; Tess's process fan-out drives
`codex exec` instead. This target only renders doctrine + skill artifacts;
it does not (and cannot) change how Codex itself composes a crew from an
orchestrator's plan.

## Doctrine profile (G3, 2026-07-08)

`CodexRenderTarget.doctrine_profile == "worker"` (see `adapters/README.md`
"Doctrine profile"). `AGENTS.md`'s payload is deliberately lean (~40-60
rendered lines): environment/gate facts + the ~5-line hard floor, zero
orchestration doctrine (no Rule Zero, no outcome-orchestrator routing, no
26-row command table) — a 2026-07-07 proving-ground benchmark measured that
exact payload as harmful when mounted into a single-agent harness like
Codex. `_check_worker_profile_denylist()` (wired into `doctor`/`verify`/
`lock --check`) fails loud if orchestration doctrine ever leaks back in.
