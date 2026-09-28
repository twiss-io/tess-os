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
| `.codex/config.toml` | `.tess/core/templates/agents-md/codex-config.toml.tpl` — `approval_policy = "on-request"`, `sandbox_mode = "workspace-write"`, and one inline `[[hooks.SessionStart]]` that runs `scripts/brain/onboard.py hook session-start --runtime codex` (v0.2.1) |
| `.codex/agents/<role>.toml` | one Codex custom agent per INSTALLED role in `.tess/core/agents-dispatch/` (`_render_codex_agent_bytes()`): `name`, `description`, `sandbox_mode` (from the role's `sandbox:`; anything but `workspace-write` becomes `read-only`), `developer_instructions` = the role body. Removed when a role is benched; files you author in the same directory are never touched |

`CodexRenderTarget.expected_live_bytes()` and `render_generated_paths()`
implement the interface's drift-checking hooks for all of them; see
`_check_untracked_render_generated()` in `.tess/bin/tessctl` for how the
skills get drift-checked without an individual `tess.lock` entry (the
underlying `.tess/core/commands/*.md` source is already base_sha-pinned by
the claude-code surface's own `.claude/commands/**` entries).

It does **not** render `.codex/hooks.json` (the onboarding hook is inline in
`.codex/config.toml`, so a `hooks.json` you write stays yours; Codex merges
both and warns) and translates none of the Claude PreToolUse gate hooks. See
[`../CONFORMANCE.md`](../CONFORMANCE.md) for what that means for enforcement
(Codex is Partial).

## Roles, onboarding and brain capture in Codex (v0.2.1)

Checked live on 2026-09-29 with codex-cli 0.145.0 and `gpt-5.5` (`codex exec`)
against a fresh clone-source instance; transcripts are summarised in the
v0.2.1 Codex parity PR.

- **Roles.** Codex spawns a custom agent when the user asks or when
  `AGENTS.md` or a skill tells it to
  ([subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents.md)).
  `AGENTS.md` ("Roles and Dispatch") names the installed roles, computed from
  `tess.lock` by `_worker_roles_line()`, and tells the top-level session to call
  `spawn_agent` with `agent_type` set to the role name, without
  `fork_context` (0.145 rejects `agent_type` on a full-history fork with
  "Full-history forked agents inherit the parent agent type"), and to
  `wait_agent` before `close_agent`. Small tasks are still done directly; a
  spawned role never spawns again. If a role will not start, the session must
  say so and do the work itself under that role's file, never pass a generic
  agent off as the role.
- **Trust.** In the 0.145 runs, `.codex/agents/*.toml` loaded (the spawned
  thread's developer message carried the role body) in a project that was
  not trusted, while the docs say an untrusted project skips the project
  `.codex/` config, hooks and rules. Treat role loading without trust as
  observed, not documented.
- **Onboarding.** The `AGENTS.md` BOOT block starts onboarding with no setup
  (every live run asked step 1). The SessionStart hook adds the same
  `ONBOARDING PENDING` line Claude Code gets, but Codex runs a project hook
  only in a trusted project and only after you approve it in `/hooks`;
  approval is pinned to the hook's hash, so re-approve after an update.
  For Codex only, the hook line adds "do the task first with the tools it
  needs": without it, 1 of 3 live runs answered only the onboarding question
  and dropped the operator's task.
- **Brain capture.** Decisions and saves follow the shared BOOT rules. Once
  onboarding was complete, Codex wrote `brain/decisions/D-<YYYYMMDD-HHMM>-<slug>.md`
  with the operator's exact words and linked it from `brain/START-HERE.md`
  and the decision indexes, matching Claude Code. Before onboarding is
  complete both runtimes hold the decision and ask the setup question.

### Retired: `.codex/prompts/`

Before v0.2.0 this target mirrored the commands into `.codex/prompts/*.md`.
Codex never loads a project-scoped prompts directory — the feature request
was closed as not planned
([openai/codex#9848](https://github.com/openai/codex/issues/9848)) — so those
files did nothing. They are no longer rendered or owned. `CodexRenderTarget.
retired_paths()` lists them, and `tessctl render` prints one `retired` line
while any still exist and drops their `tess.lock` `render_outputs` records.
Nothing deletes the files: remove them yourself once the skills work for
you.

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
  git root down to cwd, up to `project_doc_max_bytes` in total (32 KiB by
  default) including your own
  `~/.codex/AGENTS.md`
  ([AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md.md)).
  The rendered worker profile stays at or under 12,000 bytes and under 100 lines
  (`tests/test_brain_bootstrap.py`), which leaves about 20 KiB of the default
  cap for your own `~/.codex/AGENTS.md` and nested client briefs.
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
`owned_globs` yourself — `tessctl` never rewrites your manifest (the line
`render` prints reads `NOTE  codex: 52 output(s) not written — outside
owned_globs. Add ".agents/skills/tess-*/**" ...`):

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

Tier B (adapters/README.md "Capability tiers"). Codex documents its own
subagents (`.codex/agents/*.toml`, the `spawn_agent` tool —
[subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents.md)),
and since v0.2.1 this target renders the installed roster there and
`AGENTS.md` tells a Codex session how and when to spawn a role. It is still
Tier B: nothing Tess ships can block a Codex tool call, and the conductor
doctrine (always hand work to a role) is not mounted — a Codex session works
directly by default and uses a role when asked.

## Doctrine profile (G3, 2026-07-08)

`CodexRenderTarget.doctrine_profile == "worker"` (see `adapters/README.md`
"Doctrine profile"). `AGENTS.md`'s payload is deliberately lean (~40-60
rendered lines): environment/gate facts + the ~5-line hard floor, zero
orchestration doctrine (no Rule Zero, no outcome-orchestrator routing, no
26-row command table) — a 2026-07-07 proving-ground benchmark measured that
exact payload as harmful when mounted into a single-agent harness like
Codex. `_check_worker_profile_denylist()` (wired into `doctor`/`verify`/
`lock --check`) fails loud if orchestration doctrine ever leaks back in.
