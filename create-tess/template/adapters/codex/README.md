# Codex render target — pilot

> This is a shipped Tess OS render target, not certified native-parity support.
> The driver has not been live-tested against Codex event samples. The v1.0
> safety gate was checked against live codex-cli 0.158 hook payloads (see
> "Safety gate in Codex"). Treat the other files below as a project-level
> pilot and confirm current Codex behavior in your environment before relying
> on them. See
> [Support and status](../../docs/STATUS.md).

Implementation: `CodexRenderTarget` in `.tess/bin/tessctl`
(`name = "codex"`, registered in `RENDER_TARGETS`).

## What it renders

| Live path | Compiled from |
|---|---|
| `AGENTS.md` | `render_agents_md()` — SHARED with the `generic` target (see below) |
| `.agents/skills/tess-<name>/SKILL.md` | one Agent Skill per `.tess/core/commands/*.md` command body (the same 26 files the claude-code target restores to `.claude/commands/*.md`) — `render_agent_skill_md()`: frontmatter `name` (`tess-<name>`, equal to the directory name) and `description` (the command's own), then the body through `apply_token_sub()` with relative links rebased onto the skill directory |
| `.agents/skills/tess-<name>/agents/openai.yaml` | `render_agent_skill_openai_yaml()` — `policy: allow_implicit_invocation: false`, so Codex runs a Tess command only when the user names it (`$tess-<name>`), the way a Claude Code slash command works |
| `.codex/config.toml` | `.tess/core/templates/agents-md/codex-config.toml.tpl` — `approval_policy = "on-request"`, `sandbox_mode = "workspace-write"`, one inline `[[hooks.SessionStart]]` that runs `scripts/brain/onboard.py hook session-start --runtime codex` (v0.2.1), and one inline `[[hooks.PreToolUse]]`, the Tess safety gate (v1.0, see below) |
| `.codex/rules/tess.rules` | `.tess/core/templates/agents-md/codex-tess.rules.tpl` — `render_codex_rules()`: Codex prefix rules, the backstop behind the gate (v1.0) |
| `.codex/agents/<role>.toml` | one Codex custom agent per INSTALLED role in `.tess/core/agents-dispatch/` (`_render_codex_agent_bytes()`): `name`, `description`, `sandbox_mode` (from the role's `sandbox:`; anything but `workspace-write` becomes `read-only`), `developer_instructions` = the role body. Removed when a role is benched; files you author in the same directory are never touched |

`CodexRenderTarget.expected_live_bytes()` and `render_generated_paths()`
implement the interface's drift-checking hooks for all of them; see
`_check_untracked_render_generated()` in `.tess/bin/tessctl` for how the
skills get drift-checked without an individual `tess.lock` entry (the
underlying `.tess/core/commands/*.md` source is already base_sha-pinned by
the claude-code surface's own `.claude/commands/**` entries).

It does **not** render `.codex/hooks.json`: both Tess hooks are inline in
`.codex/config.toml`, so a `hooks.json` you write stays yours (Codex loads
both and warns "prefer a single representation for this layer"). See
[`../CONFORMANCE.md`](../CONFORMANCE.md) for the enforcement level: Enforced
once the project is trusted and Tess hooks are approved in `/hooks` (the
one-time setup below).

## Safety gate in Codex (v1.0)

### Do this once

1. Trust the project when Codex asks (or set `trust_level = "trusted"` for it
   in your own `~/.codex/config.toml`). Codex ignores a project's
   `.codex/config.toml`, hooks and rules until you do.
2. **Required:** start `codex` in the project, type `/hooks`, and approve the Tess hooks
   (`Tess: safety check`, `Tess: checking onboarding`, `Tess: loading the
   brain` and the three learning-loop hooks). Codex pins your approval to
   each hook's hash, so after a Tess update that changes a hook, `/hooks`
   asks again; until you re-approve, that hook does not run. Without this
   step Tess's safety checks are off: the assistant's first reply says so
   (`python3 scripts/tess hooks-status`) and `./tessctl doctor` warns.
3. The first time Tess saves your brain, Codex asks to run
   `python3 scripts/brain/tessbrain.py save` outside its sandbox (the
   default sandbox keeps `.git` read-only, so a commit cannot run inside it).
   One click: choose "Yes, proceed", or "Yes, and don't ask again for
   commands that start with" it so later saves do not ask. The brain-save
   skill and the `AGENTS.md` harness note tell Codex to ask for this
   approval rather than fail; if you say no, Tess reports the work as not
   saved.

Until both are done, nothing Tess ships blocks a Codex tool call; only
Codex's own sandbox and approval settings apply. The `AGENTS.md` harness note
tells the Codex session this, so it can remind you.

### What the gate checks

One PreToolUse hook, matcher `^(Bash|apply_patch|Edit|Write|Agent|spawn_agent|mcp__.*)$`,
runs `.claude/hooks/tess-gate.py --runtime codex` through
`.claude/hooks/run-pinned.py --on-fail block`. The launcher checks the
script against the sha pinned in `.tess/core/pinned-scripts.sha256` (itself
pinned by `.tess/tess.lock`); a missing, edited or unpinned script blocks
the call rather than skipping the check. So do a missing `python3` and a
session started outside a Tess project (the hook walks up from the session
cwd to the nearest `.tess/tess.lock`).

| Codex event / tool (0.158) | Can the hook block it? | Tess check wired |
|---|---|---|
| PreToolUse `Bash` (shell and `exec_command`; payload `tool_input.command` is the command string) | Yes: `permissionDecision: "deny"` or exit 2 | Secret-shaped values (PEM, GitHub, Stripe, Slack, AWS, age formats); `--no-verify` and `git commit -n`; `core.hooksPath` via `-c`, `--config-env`, `git config`, `GIT_CONFIG_*` or `export`; shell writes (`>`, `tee`, `sed -i`, `rm`, `mv`, `cp`, `git rm`, ...) to protected files and under `.git/hooks`; `gh auth token`; `git push` of brain/ or clients/ data to a public or unverifiable remote (runs `tessctl doctor --publish-remote`, the pre-push guard's own check). Ask, sent as deny: force push, `git remote add/set-url/rename/remove`, visibility changes (`gh repo edit --visibility`, `gh repo create --public`, `gh api ... visibility=`). Nested `bash -c`, `sh -c` and `eval` are read too. |
| PreToolUse `apply_patch` (also matched as `Edit`/`Write`; payload `tool_input.command` is the patch text, absolute paths) | Yes | Every `*** Add/Update/Delete File:` and `*** Move to:` path is resolved (symlinks, `..`, case) and checked against the protected list; a patch whose files cannot be read is denied. |
| PreToolUse `spawn_agent` (matched as `Agent`) | Yes | The full `vault-dispatch-scan.py` pattern set over the whole dispatch, the same scan Claude runs on `Task`/`Agent`. |
| PreToolUse `mcp__*` | Yes | A write-shaped MCP tool (name contains write, edit, create, move, delete, ...) aimed at a protected path. |
| PreToolUse on hosted tools (web search) | No: hosted tools skip hooks | None. |
| PermissionRequest | Yes (allow/deny an approval prompt) | Not used. The PreToolUse gate runs first. |
| SessionStart | Adds context only | Onboarding check (`scripts/brain/onboard.py`), unchanged from v0.2.1. |
| UserPromptSubmit, PostToolUse, SessionEnd | UserPromptSubmit and PostToolUse can block; SessionEnd cannot | Not rendered: Claude's UTC context, task-lock and warn-only dispatch-guard hooks serve the conductor profile, and the Codex target uses the worker profile. |

Protected files are every `.tess/tess.lock` entry tagged `tier: security`
plus `PROTECTED_GLOBS` in the gate: the security-tier doctrine, `core/policy/**`,
`core/contracts/**`, `.tess/bin/**`, `.tess/core/**`, `.tess/tess.lock`,
`.tess/keys/**`, `.tess/gate/**`, `.github/workflows/**`, `.claude/hooks/**`,
`.claude/settings.json`, `scripts/brain/**`, `CLAUDE.md`, `AGENTS.md`,
`GEMINI.md`, `.codex/config.toml`, `.codex/hooks.json`, `.codex/rules/**`,
`.git/hooks/**`, `.git/config` and `.gitleaks.toml`. Reading them is fine.
To change one, do it yourself outside the agent; the ship gate still asks for
a signed verdict.

Why deny instead of ask: Codex parses `permissionDecision: "ask"` but does not
support it; the hook fails and the command runs
([hooks](https://learn.chatgpt.com/docs/hooks.md), "Unsupported PreToolUse
features"). A payload with `turn_id` is treated as Codex even without
`--runtime codex`. Every deny and ask is appended, redacted, to
`~/.cache/tess/gate-decisions.log` (`TESS_GATE_LOG` overrides).

### Rules backstop

`.codex/rules/tess.rules` forbids `git <commit|push|merge|rebase|am|cherry-pick|revert|pull> --no-verify`,
`git commit -n` and `gh auth token`, and prompts for `git -c`, `git config`
hook and scope changes, `git remote add/set-url/rename/remove`,
`gh repo edit/create/rename/delete/archive` and force pushes. Rules match only
a command prefix (`git commit -m x --no-verify` is not caught), and Codex loads
them only in a trusted project, so they are a backstop for an unapproved hook,
not the guard. Check one with
`codex execpolicy check --pretty --rules .codex/rules/tess.rules -- <command>`.

### Live check (2026-09-29, codex-cli 0.158.0, `gpt-6-astra`)

A fresh clone of this branch, run with `codex exec --json
--dangerously-bypass-hook-trust --dangerously-bypass-approvals-and-sandbox
-c 'projects."<path>".trust_level="trusted"'` (so no sandbox or approval
prompt could stand in for the gate), plus a throwaway project `hooks.json`
that recorded each payload:

| Prompt | Result |
|---|---|
| Run `git commit --allow-empty --no-verify -m ...` | Blocked; no commit. The Tess gate logged a deny for the call. On the test machine a user-level git guard also denied it and its message is the one Codex showed. |
| `apply_patch` a line onto `conductor/guardrails.md` | Blocked with `TESS GATE: blocked because it edits .../conductor/guardrails.md, a protected Tess path`; file unchanged; the model reported the block and did not retry another way. |
| `apply_patch` a new `notes/e2e-normal.md`, then `git add` and `git commit` | Both allowed; the commit landed. The gate returned nothing on all 9 calls in the run. |

Payloads seen: `tool_name` `Bash` with `tool_input.command` a string, and
`apply_patch` with `tool_input.command` the patch text; every payload carried
`turn_id` and `permission_mode` (`bypassPermissions` in these runs).
Unit and command-level tests: `tests/test_codex_gate.py`.

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
Tier B: since v1.0 the Tess safety gate can block a Codex tool call (after
the one-time setup above), but the conductor doctrine (always hand work to a
role) is not mounted — a Codex session works directly by default and uses a
role when asked.

## Doctrine profile (G3, 2026-07-08)

`CodexRenderTarget.doctrine_profile == "worker"` (see `adapters/README.md`
"Doctrine profile"). `AGENTS.md`'s payload is deliberately lean (~40-60
rendered lines): environment/gate facts + the ~5-line hard floor, zero
orchestration doctrine (no Rule Zero, no outcome-orchestrator routing, no
26-row command table) — a 2026-07-07 proving-ground benchmark measured that
exact payload as harmful when mounted into a single-agent harness like
Codex. `_check_worker_profile_denylist()` (wired into `doctor`/`verify`/
`lock --check`) fails loud if orchestration doctrine ever leaks back in.
