# Adapter conformance

Tess OS is provider-neutral in its governance model, not automatically
provider-complete. This page answers two separate questions:

1. **Runtime enforcement.** What does each coding-agent runtime actually do
   with the files Tess renders? Does it load the doctrine, and can Tess's
   in-session gates block a tool call there? Levels: Enforced, Partial,
   Advisory, or `unverified` when this release did not check the runtime's
   documentation.
2. **Adapter manifests.** The C0–C4 status records in
   [`manifests/`](manifests/). They record evidence and limits and never
   grant permissions or change the gate.

Claude Code is the reference runtime and the only one where Tess's gates run
as designed. Every other runtime is weaker, and this page says how. It is not
a parity claim.

## 1. Runtime enforcement

### Levels

| Level | Meaning |
|---|---|
| Enforced | The runtime loads the Tess doctrine natively AND runs Tess's shipped hooks natively; a hook that blocks stops the tool call. |
| Partial | The runtime loads the doctrine natively. Some enforcement exists (the runtime's own sandbox/approval settings rendered by Tess, or Tess's Claude hooks read as a third party), with documented gaps or fail-open cases. |
| Advisory | The runtime can read the doctrine as text (natively or with one line of config). Nothing Tess ships can block a tool call there. |
| unverified | This release did not verify the runtime against its own documentation. No level is claimed. |
| not rendered | Tess ships no render target for this runtime in this build. |

**Scope of a level.** A level describes in-session enforcement only. The
ship-gate (`tessctl gate` in CI via `.github/workflows/tess-gate.yml`, and
the pre-push hook where installed) runs in git and CI, outside every runtime,
so it applies to a change whatever tool produced it. A level also never covers
model quality: the same runtime can route to different models.

### Per-runtime table

"Tess target" names the `RENDER_TARGETS` key (in `.tess/bin/tessctl`) whose
output the runtime reads. A runtime that reads another target's output as a
third party says so in the "How it reads Tess" column. Each row was checked
against the linked documentation on 2026-09-24 for the v0.2.0 release;
runtimes change quickly, so re-check before relying on a row.

| Runtime | Tess target | Level | How it reads Tess | Why this level (limits) | Docs |
|---|---|---|---|---|---|
| Claude Code | `claude-code` | Enforced | `CLAUDE.md` (plus cwd ancestors, `.claude/rules/`), `.claude/agents/`, `.claude/commands/`, `.claude/skills/`, and the hooks in `.claude/settings.json`. | Reference runtime. All shipped hooks run natively (PreToolUse on the Telegram reply/edit tools, on `Task\|Agent`, on `Bash\|Edit\|Write`; PostToolUse, SessionEnd, UserPromptSubmit); exit 2 or `permissionDecision: "deny"` blocks. `dispatch-guard.sh` only warns by design. It reads `AGENTS.md` only when no `CLAUDE.md` exists, so in a Tess install it ignores `AGENTS.md`. It does not read `.agents/skills/`. | [memory](https://code.claude.com/docs/en/memory.md), [hooks](https://code.claude.com/docs/en/hooks.md), [skills](https://code.claude.com/docs/en/skills.md), [sub-agents](https://code.claude.com/docs/en/sub-agents.md) |
| OpenAI Codex CLI | `codex` | Partial | `AGENTS.md` (root to cwd, one file per directory, 32 KiB cap), the 26 commands as `.agents/skills/tess-*/SKILL.md` (explicit-only via `agents/openai.yaml`, run with `$tess-<command>`), and `.codex/config.toml` (`approval_policy = "on-request"`, `sandbox_mode = "workspace-write"`). | Doctrine loads natively. Enforcement is Codex's own sandbox and approval policy from the rendered `.codex/config.toml`, which Codex loads only for a trusted project. Tess renders no `.codex/hooks.json` in this release, so no Tess hook runs. Codex hooks exist but require hash-based trust review, fail open for unsupported outputs, and the docs call them "a useful guardrail, not a complete enforcement boundary". A project-scoped `.codex/prompts/` is never loaded, which is why the commands are skills. | [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md.md), [skills](https://learn.chatgpt.com/docs/build-skills.md), [hooks](https://learn.chatgpt.com/docs/hooks.md), [config](https://learn.chatgpt.com/docs/config-file/config-reference.md), [openai/codex#9848](https://github.com/openai/codex/issues/9848) |
| Any AGENTS.md reader (generic) | `generic` | Advisory | `AGENTS.md` plus a plain `prompts/<command>.md` mirror with no harness-specific frontmatter. | Text only: nothing in the generic output can block a tool call. Use it for runtimes with no Tess target. | [agents.md](https://agents.md/) |
| GitHub Copilot CLI | none (reads `claude-code` output) | Partial | Loads `CLAUDE.md`, `AGENTS.md`, `.github/instructions`, `.claude/agents`, `.claude/commands`, `.claude/skills`, `.agents/skills` and the hooks in `.claude/settings.json`. | Tess's Claude hooks run. Command `preToolUse` hooks fail closed on a crash or non-zero exit, but timeouts always fail open. The Copilot cloud agent reads only `.github/hooks/*.json`, which Tess does not render. It merges `CLAUDE.md` and `AGENTS.md`, so doctrine loads twice. | [custom instructions](https://docs.github.com/en/copilot/reference/custom-instructions-support), [hooks](https://docs.github.com/en/copilot/reference/hooks-reference), [CLI config](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference) |
| Cursor (IDE and CLI) | none (reads `claude-code` output) | Partial | `CLAUDE.md` (always applied) and `AGENTS.md`, `.claude/agents`, `.claude/skills`, `.agents/skills`, and the hooks in `.claude/settings.json` ("Include Third-Party Plugins, Skills, and Other Configs", on by default). | Claude hooks map onto 8 Cursor events; Notification and PermissionRequest are unsupported and Glob is unmapped. Exit 2 blocks, but crashes, timeouts and other non-zero exits fail open unless `failClosed: true`, which exists only in the native `.cursor/hooks.json`. Whether hook payloads carry Claude tool names is unverified. Doctrine loads twice. | [rules](https://cursor.com/docs/rules.md), [third-party hooks](https://cursor.com/docs/reference/third-party-hooks.md), [hooks](https://cursor.com/docs/hooks.md), [skills](https://cursor.com/docs/skills.md) |
| OpenCode | none (reads `AGENTS.md`) | Advisory | `AGENTS.md` walking up from cwd (`CLAUDE.md` only when there is no `AGENTS.md`); skills from `.agents/skills`. | Hooks are JS/TS plugins (`tool.execute.before`); Claude `settings.json` hooks are not read and no Tess plugin exists. | [rules](https://opencode.ai/docs/rules/), [plugins](https://opencode.ai/docs/plugins/), [skills](https://opencode.ai/docs/skills/) |
| Amp | none (reads `AGENTS.md`) | Advisory | `AGENTS.md` in cwd and parents (falls back to `AGENT.md` or `CLAUDE.md`); skills from `.agents/skills`. | No declarative hooks; tool approval is a TS plugin (`amp.on('tool.call')`) and no Tess plugin exists. | [AGENTS.md](https://ampcode.com/docs/markdown/customize/agents-md), [plugins](https://ampcode.com/docs/markdown/customize/plugins), [skills](https://ampcode.com/docs/markdown/customize/skills) |
| Devin Desktop (formerly Windsurf Cascade) | none (reads `AGENTS.md`) | Advisory | Root `AGENTS.md` becomes an always-on rule; a subdirectory `AGENTS.md` becomes a glob rule. | Its own `.devin/hooks.json` format with `pre_*` events and no subagent event; Tess does not render it. A 12,000-character limit applies to workspace rules; whether it also truncates `AGENTS.md` is unverified. | [AGENTS.md](https://docs.devin.ai/desktop/cascade/agents-md.md), [hooks](https://docs.devin.ai/desktop/cascade/hooks.md), [memories and rules](https://docs.devin.ai/desktop/cascade/memories.md) |
| Google Jules | none (reads `AGENTS.md`) | Advisory | `AGENTS.md` at the repository root. | Cloud agent with no documented hooks, commands or custom agents. | [docs](https://jules.google/docs/) |
| Aider | none (needs one config line) | Advisory | Never reads `AGENTS.md` automatically. Add `read: [AGENTS.md]` to `.aider.conf.yml`, or run `aider --read AGENTS.md`. | No hooks, custom agents or user commands. | [conventions](https://aider.chat/docs/usage/conventions.html) |
| Kiro | none (reads `AGENTS.md`) | Advisory | `AGENTS.md` is always included, at the root and in subdirectories. | Its own JSON hooks and agents; Tess renders neither. Checked through a summarising fetch, medium confidence. | [steering](https://kiro.dev/docs/steering/), [hooks](https://kiro.dev/docs/hooks/) |
| Qwen Code | none (reads `AGENTS.md`) | Advisory | Reads `AGENTS.md` alongside `QWEN.md`; never `CLAUDE.md`. In the runtime smoke it also listed the 26 `.agents/skills/tess-*` skills as project skills, although its docs name only `.qwen/skills/`. | Hooks live in `.qwen/settings.json`, which Tess does not render and which an untrusted folder ignores, so no Tess gate runs. | [memory: features › memory.md](https://github.com/QwenLM/qwen-code/tree/main/docs), [skills: features › skills.md](https://github.com/QwenLM/qwen-code/tree/main/docs), [hooks: features › hooks.md](https://github.com/QwenLM/qwen-code/tree/main/docs), [trusted folders: configuration › trusted-folders.md](https://github.com/QwenLM/qwen-code/tree/main/docs) |
| Grok Build (xAI) | none (reads `claude-code` and `codex` output) | Advisory | In a trusted folder: `CLAUDE.md` **and** `AGENTS.md`, `.claude/rules/`, `.claude/agents/`, `.claude/commands/`, `.claude/skills/`, `.agents/skills/`, the hooks and permission rules in `.claude/settings.json`, and a project `.mcp.json`. In an untrusted folder, none of the instructions, skills or hooks load. | The Claude hooks fire, but with Grok's own tool names (`spawn_subagent`, `run_terminal_command`, `search_replace`), so `vault-dispatch-scan.py`, the one shipped hook that blocks, never matches: the runtime smoke saw a secret-shaped subagent prompt reach the subagent. Hook crashes and timeouts fail open. It loads the conductor profile (`CLAUDE.md`) and the worker profile (`AGENTS.md`) together. | [project rules](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/12-project-rules.md), [hooks](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/10-hooks.md), [skills](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/08-skills.md), [permissions](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/22-permissions-and-safety.md) |
| Kimi Code (Moonshot) | none (reads `codex` output) | Advisory | `AGENTS.md` (plus `.kimi-code/AGENTS.md`) from the git root down to cwd, never `CLAUDE.md`; the 26 `.agents/skills/tess-*` skills. | Hooks are user-level only (`~/.kimi-code/config.toml`) and fail open, so a project cannot ship one. `kimi -p` runs in auto mode and never asks for approval; only static deny rules apply. Subagents come from `.kimi-code/agents/` or `.agents/agents/`, which Tess does not render. | [instruction files](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/customization/agents.md), [skills](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/customization/skills.md), [hooks](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/customization/hooks.md), [`kimi` command](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/reference/kimi-command.md) |
| DeepSeek Harness (developer preview) | none (reads `claude-code` and `codex` output) | Advisory | `AGENTS.md` and `CLAUDE.md` (plus `.local.md` overlays) from the project root down, within a 65,536-byte baseline budget; skills from `.agents/skills/`. | Its Claude Code hook bridge is an opt-in plugin that neither default bundle mounts, so no Tess hook runs by default. Developer preview: its README warns of breaking changes. | [instructions](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/context/agent-instructions/README.md), [hook bridge](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/hooks/hooks-claude-code/README.md), [skills](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.md), [CLI](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/README.md) |
| Antigravity CLI (Google) | none (reads `AGENTS.md`) | Advisory | Documented: `GEMINI.md` and `AGENTS.md` in the workspace, skills from `.agents/skills/`, hooks from `.agents/hooks.json`, MCP from `.agents/mcp_config.json`. Tess renders none of the `.agents/` configs except the skills. | An open bug reports that nothing under a workspace `.agents/` loads under `agy -p` ([antigravity-cli#1052](https://github.com/google-antigravity/antigravity-cli/issues/1052)). Not smoke-tested here, and never run live: see the subscription table below. | [migrating from Gemini CLI](https://antigravity.google/docs/cli/gcli-migration/), [headless](https://antigravity.google/docs/cli/headless) |
| Google Gemini CLI | none on this branch | not rendered | Reads `GEMINI.md` by default and ignores `AGENTS.md` unless `context.fileName` names it. Hand-apply `.gemini/settings.json`: `{"context": {"fileName": ["AGENTS.md", "GEMINI.md"]}}`. Skills load from `.agents/skills`. | No Tess render target in this build. Different hook event names and output keys; the project policy tier is documented as non-functional ([gemini-cli#18186](https://github.com/google-gemini/gemini-cli/issues/18186)). | [GEMINI.md](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/gemini-md.md), [hooks](https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md), [trusted folders](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/trusted-folders.md) |
| Cline | none | unverified | Its docs say it detects `AGENTS.md`; hooks defer to SDK plugin docs. | Not verified for this release; treat as AGENTS.md-only. | [rules](https://docs.cline.bot/features/cline-rules) |
| Roo Code | none | unverified | Its docs say it reads `AGENTS.md` when `useAgentRules` is on (default). | Not verified for this release; treat as AGENTS.md-only. | [custom instructions](https://roocodeinc.github.io/Roo-Code/features/custom-instructions) |
| Any other runtime | none | unverified | Try the `generic` target. | Not checked. | [agents.md](https://agents.md/) |

### Which instruction file each runtime loads

A Tess install ships both `CLAUDE.md` (the full conductor doctrine, for the
`claude-code` target) and `AGENTS.md` (the lean worker profile, for `codex`
and `generic`). Runtimes resolve the pair differently:

- **Claude Code** reads `CLAUDE.md` and ignores `AGENTS.md` whenever a
  `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` exists in cwd or
  above it (the default `claude-md-or-agents-md` mode). It never reads
  `AGENTS.override.md` or `.agents/`
  ([memory](https://code.claude.com/docs/en/memory.md)).
- **Codex** reads `AGENTS.override.md` or `AGENTS.md`, one file per
  directory from the git root down to cwd, root first, up to 32 KiB in total.
  A user `~/.codex/AGENTS.md` counts toward the same cap
  ([AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md.md)).
- **Cursor and the Copilot CLI** load both files, so the doctrine appears
  twice ([Cursor rules](https://cursor.com/docs/rules.md),
  [Copilot instructions](https://docs.github.com/en/copilot/reference/custom-instructions-support)).
- **OpenCode and Amp** prefer `AGENTS.md` and fall back to `CLAUDE.md`
  ([OpenCode](https://opencode.ai/docs/rules/),
  [Amp](https://ampcode.com/docs/markdown/customize/agents-md)).
- **Gemini CLI** reads `GEMINI.md` unless `context.fileName` is set
  ([GEMINI.md](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/gemini-md.md)).
- **Grok Build** loads every recognised file in each directory, so it reads
  `CLAUDE.md` and `AGENTS.md` together: the conductor profile and the worker
  profile at once. Only in a trusted folder; no size cap
  ([project rules](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/12-project-rules.md)).
- **Kimi Code** reads `AGENTS.md` (and `.kimi-code/AGENTS.md`) from the git
  root down, plus `~/.kimi-code/AGENTS.md` and `~/.agents/AGENTS.md`, and never
  `CLAUDE.md`. Above 32 KiB in total it only warns
  ([instruction files](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/customization/agents.md),
  [loader](https://github.com/MoonshotAI/kimi-code/blob/main/packages/agent-core-v2/src/agent/profile/context.ts)).
- **Qwen Code** reads `QWEN.md` and `AGENTS.md`, not `CLAUDE.md`
  ([memory: features › memory.md](https://github.com/QwenLM/qwen-code/tree/main/docs)).
- **DeepSeek Harness** reads `AGENTS.md` and `CLAUDE.md` from the project root
  down; a `CLAUDE.md` identical to its `AGENTS.md` renders once. The base
  profile caps the rendered pair at 65,536 bytes, dropping broader files first
  ([agent instructions](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/context/agent-instructions/README.md)).
- **Antigravity CLI** reads the workspace `GEMINI.md` and `AGENTS.md`
  ([migration guide](https://antigravity.google/docs/cli/gcli-migration/)).
- **Aider** reads nothing automatically; add `read: [AGENTS.md]` to
  `.aider.conf.yml` ([conventions](https://aider.chat/docs/usage/conventions.html)).

### Commands as Agent Skills

The `codex` target renders the 26 commands as `.agents/skills/tess-<command>/`
(see [`codex/README.md`](codex/README.md)). Codex, Gemini CLI, Cursor, the
Copilot CLI, OpenCode, Amp, Grok Build, Kimi Code and DeepSeek Harness all read
`.agents/skills/`
([Codex](https://learn.chatgpt.com/docs/build-skills.md),
[Gemini](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/skills.md),
[Cursor](https://cursor.com/docs/skills.md),
[OpenCode](https://opencode.ai/docs/skills/),
[Amp](https://ampcode.com/docs/markdown/customize/skills),
[Grok Build](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/08-skills.md),
[Kimi Code](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/customization/skills.md),
[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.md)); Qwen Code
listed them too in the runtime smoke, although its docs name only
`.qwen/skills/`. Antigravity CLI documents `.agents/skills/`, but see
[antigravity-cli#1052](https://github.com/google-antigravity/antigravity-cli/issues/1052).
Claude Code does not; it uses `.claude/commands/`.

Each runtime has its own way to run a skill by name, and the rendered
`AGENTS.md` names them: Codex `$tess-<name>`, Kimi Code `/skill:tess-<name>`
([skills](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/customization/skills.md)), Grok Build and Qwen Code
`/tess-<name>` ([Grok](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/08-skills.md), [Qwen: features › skills.md](https://github.com/QwenLM/qwen-code/tree/main/docs)). Cursor and the Copilot CLI read both
`.claude/commands/` and `.agents/skills/`, so a codex-enabled install shows
each command twice there; so does Grok Build (`/add-mission` and
`/tess-add-mission`). The `agents/openai.yaml` explicit-only policy is a
Codex setting; other runtimes may still pick a skill implicitly from its
description.

### Subscriptions, headless use and known gaps

Tess OS never reads, stores or passes on a vendor login token. It works with a
subscription only by running the vendor's own, unmodified CLI, signed in
through the vendor's own flow. Where the vendor offers no such path, the only
route is an API key. "Allowed" below means the vendor documents or invites
this use. Plan limits and terms still apply, and they change: re-check before
relying on a row. The level column repeats the table above.

| Runtime | Level | Subscription path | Headless command | Loads from a Tess install | Known gaps |
|---|---|---|---|---|---|
| Claude Code | Enforced ([hooks](https://code.claude.com/docs/en/hooks)) | **Allowed, with conditions**: the unmodified `claude` binary, the user's own sign-in, and "ordinary, individual usage". `--bare` never reads the subscription login ([legal and compliance](https://code.claude.com/docs/en/legal-and-compliance), [headless](https://code.claude.com/docs/en/headless)) | `claude -p "<task>"` ([headless](https://code.claude.com/docs/en/headless)) | `CLAUDE.md`, `.claude/` commands, agents, skills and hooks ([memory](https://code.claude.com/docs/en/memory.md)) | A `PreToolUse` command hook that times out does not block ([hooks](https://code.claude.com/docs/en/hooks)) |
| OpenAI Codex CLI | Partial ([hooks](https://learn.chatgpt.com/docs/hooks.md)) | **Allowed**: `codex exec` reuses a saved ChatGPT sign-in (Plus or above), on trusted private runners, one `auth.json` per runner ([non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), [CI/CD auth](https://learn.chatgpt.com/docs/auth/ci-cd-auth)) | `codex exec "<task>"` ([non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)) | `AGENTS.md`, `.agents/skills/tess-*`, `.codex/config.toml` ([AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md.md)) | Hooks an admin does not manage are skipped until trusted ([hooks](https://learn.chatgpt.com/docs/hooks.md)) |
| Grok Build | Advisory ([hooks](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/10-hooks.md)) | **Allowed**: included with SuperGrok and X Premium+; xAI presents `-p` as "for scripts and automations" ([launch post](https://x.ai/news/grok-build-cli)). xAI still recommends an API key for CI ([authentication](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/02-authentication.md)) | `grok -p "<task>" --trust` (the grant is recorded under `~/.grok`); `GROK_FOLDER_TRUST=0` lifts the trust gate without recording one. ACP: `grok agent stdio` ([headless](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/14-headless-mode.md), [hooks](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/10-hooks.md)) | `CLAUDE.md` + `AGENTS.md`; the 26 `tess-*` skills plus `.claude/commands` and `.claude/skills`; `.claude/agents`; `.claude/settings.json` hooks and permissions ([project rules](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/12-project-rules.md), [skills](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/08-skills.md)) | The conductor and worker profiles load together. The vault gate does not block ([runtime smoke](#runtime-smoke-2026-09-24)). An allowing `UserPromptSubmit` hook's output is discarded, so the time-context hook adds nothing ([hooks](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/10-hooks.md)). An untrusted folder loads none of this |
| Kimi Code | Advisory ([hooks](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/customization/hooks.md)) | **Allowed**: a Kimi membership signed in with `kimi login` (device code); product or team use belongs on the Kimi Open Platform ([membership guide](https://www.kimi.com/en/help/kimi-code/membership-guide), [`kimi login`](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/reference/kimi-command.md)) | `kimi -p "<task>"`: always auto mode, and cannot be combined with `--plan`, `--yolo` or `--auto`. ACP: `kimi acp` ([`kimi` command](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/reference/kimi-command.md), [ACP](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/reference/kimi-acp.md)) | `AGENTS.md` and the 26 `tess-*` skills; no `CLAUDE.md`, subagents, hooks or MCP ([instruction files](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/customization/agents.md), [skills](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/customization/skills.md)) | Never asks for approval under `-p`, so run it in a scratch worktree or give it no write task ([`kimi` command](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/reference/kimi-command.md)). The worker profile names the conductor only as the Claude Code session, so asked who it is, Kimi does not answer with the conductor's name ([runtime smoke](#runtime-smoke-2026-09-24)) |
| Qwen Code | Advisory ([hooks: features › hooks.md](https://github.com/QwenLM/qwen-code/tree/main/docs)) | **Allowed with Alibaba Cloud Coding Plan**: a fixed monthly plan with an `sk-sp-` key. The Qwen OAuth free tier ended on 2026-04-15 ([authentication: configuration › auth.md](https://github.com/QwenLM/qwen-code/tree/main/docs)) | `qwen "<task>"` (`-p` is deprecated) with `--approval-mode`; ACP: `qwen --acp` ([headless: features › headless.md](https://github.com/QwenLM/qwen-code/tree/main/docs)) | `AGENTS.md` and, observed, the 26 `tess-*` skills ([memory: features › memory.md](https://github.com/QwenLM/qwen-code/tree/main/docs), [runtime smoke](#runtime-smoke-2026-09-24)) | Hooks and MCP come only from `.qwen/settings.json`, which an untrusted folder ignores and Tess does not render ([trusted folders: configuration › trusted-folders.md](https://github.com/QwenLM/qwen-code/tree/main/docs)) |
| DeepSeek Harness | Advisory ([hook bridge](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/hooks/hooks-claude-code/README.md)) | **Not available**: API key only. Providers that sign in with OAuth are not supported, and no DeepSeek consumer subscription was found ([providers](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/providers.md)) | `dsh --profile headless "<task>"`; ACP: `dsh --profile acp` ([CLI](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/README.md)) | `AGENTS.md` + `CLAUDE.md` and the 26 `tess-*` skills ([instructions](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/context/agent-instructions/README.md), [skills](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.md)) | Developer preview with announced breaking changes ([README](https://github.com/deepseek-ai/deepseek-harness)). The Claude hook bridge is opt-in and reads one config per process ([hook bridge](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/hooks/hooks-claude-code/README.md)) |
| Antigravity CLI | Advisory ([migration guide](https://antigravity.google/docs/cli/gcli-migration/)) | **Not available to Tess**: `agy` runs on its cached Google sign-in, but its terms treat use "in connection with products not provided by us" as abuse, and Google has not answered whether a single-user wrapper is allowed ([terms](https://antigravity.google/terms), [forum question](https://discuss.ai.google.dev/t/question-about-personal-wrapper-around-official-antigravity-cli-headless-mode/178472)). A Gemini API key is documented for headless use ([install](https://antigravity.google/docs/cli/install/)); whether the terms clause also covers an API-key run is unverified | `agy -p "<task>"`; tools that need approval are soft-denied ([headless](https://antigravity.google/docs/cli/headless)) | `GEMINI.md` and `AGENTS.md`, documented, not smoke-tested ([migration guide](https://antigravity.google/docs/cli/gcli-migration/)) | Workspace `.agents/` content reportedly never loads under `agy -p` ([antigravity-cli#1052](https://github.com/google-antigravity/antigravity-cli/issues/1052)) |
| Gemini CLI | As in the Gemini CLI row above ([GEMINI.md](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/gemini-md.md)) | **Gemini API key or Vertex AI only.** Google ended consumer "Login with Google" for Gemini CLI on 2026-06-18 ([Gemini Code Assist FAQ](https://developers.google.com/gemini-code-assist/resources/faqs), updated 2026-09-02). The CLI's own [authentication page](https://github.com/google-gemini/gemini-cli/blob/main/docs/get-started/authentication.mdx) still describes Pro/Ultra sign-in; the FAQ is the later statement | `gemini -p "<task>"`; an untrusted folder exits with `FatalUntrustedWorkspaceError` unless `--skip-trust` is passed ([trusted folders](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/trusted-folders.md)) | The 26 `tess-*` skills in a trusted folder ([skills](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/skills.md), [runtime smoke](#runtime-smoke-2026-09-24)); `AGENTS.md` only through `context.fileName` or a `GEMINI.md` import ([GEMINI.md](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/gemini-md.md)) | Different hook events and output contract; the project policy tier does not work ([gemini-cli#18186](https://github.com/google-gemini/gemini-cli/issues/18186)) |

So the accurate one-line claim is: **native on Claude Code and Codex; loads
through Claude-compatible files on Grok Build and DeepSeek Harness; through
`AGENTS.md` on Kimi Code and other `AGENTS.md` tools; Gemini CLI with a Gemini
API key.** It is not a claim about every frontier model, and "loads" is not
"enforces": only Claude Code runs Tess's gates as designed.

### Runtime smoke (2026-09-24)

[`tools/runtime-smoke/`](../tools/runtime-smoke/README.md) scaffolds a fresh
install with a random conductor name and checks each CLI without logging in.
It points the CLI at a local mock model endpoint (or its own `inspect`/`skills
list` command) and reads what the CLI would have sent to the model. A live run
happens only with `--live`, only with a CLI already on the operator's PATH, and
only if that CLI is already signed in.

| Runtime | Version | What reached the model, offline | Gate probe | Live |
|---|---|---|---|---|
| Grok Build | 1.0.41 | Trusted folder: `AGENTS.md` + `CLAUDE.md`, the conductor name, 26 `tess-*` skills, Claude hooks and agents. Untrusted: none of it | The mock returned a `spawn_subagent` call with a secret-shaped prompt; the prompt reached the subagent unblocked | Not run: not signed in on the test machine |
| Kimi Code | 2.1.0 (npm), 0.38.0 (native) | `AGENTS.md` only, the conductor name, 26 `tess-*` skills | No project hooks exist | 0.38.0, signed in: it answered as Kimi Code working in a Tess OS project and listed all 26 skills, but did not give the conductor's name. With the previous `AGENTS.md` it offered Codex's `$tess-<name>` syntax; with this release's it offers `/skill:tess-<name>` |
| Qwen Code | 0.24.4 | `AGENTS.md` only, the conductor name, 26 `tess-*` skills | No project hooks rendered | Not run: not installed for the operator |
| DeepSeek Harness | 0.1.5-rc.3 | `AGENTS.md` + `CLAUDE.md`, the conductor name, 26 `tess-*` skills | Bridge not mounted | Not run: no API key |
| Gemini CLI | 0.61.0 | `skills list`, trusted folder: 26 `tess-*` skills; no `GEMINI.md` on this branch | No hook translated | Not run: no Gemini API key |
| Antigravity CLI | not installed | UNVERIFIED | UNVERIFIED | Never run by the smoke (terms) |

### What does not translate

These six areas are Claude Code features or have no common format. Nothing in
this release renders them for another runtime.

1. **Safety-gate hooks.** Tess's gates are Claude `PreToolUse` hooks. Codex
   matches `Edit|Write` to `apply_patch`, whose input carries the patch text,
   not a `file_path`, so path allowlists do not port unchanged; unsupported
   outputs fail open and hosted tools skip hooks
   ([Codex hooks](https://learn.chatgpt.com/docs/hooks.md)). Gemini uses
   different event names, tool names and a `decision` key, with no subagent
   events ([Gemini hooks](https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md)).
   Cursor fails open on crashes and timeouts
   ([Cursor](https://cursor.com/docs/reference/third-party-hooks.md)), and
   Copilot fails open on timeouts
   ([Copilot](https://docs.github.com/en/copilot/reference/hooks-reference)).
   OpenCode and Amp need JS/TS plugins; Devin Desktop has its own `pre_*`
   events. Grok Build runs Tess's `.claude/settings.json` hooks with its own
   tool names, so the `Task|Agent` gate sees `spawn_subagent` and lets it
   through, and failures fail open ([Grok hooks](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/10-hooks.md)). Kimi Code
   reads hooks only from the user's config and fails open
   ([Kimi hooks](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/customization/hooks.md)); Qwen Code reads them from
   `.qwen/settings.json`; DeepSeek Harness runs Claude hooks only through an
   opt-in bridge ([bridge](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/hooks/hooks-claude-code/README.md)).
2. **The Telegram channel.** It is a Claude Code plugin, and the hooks match
   its tool names (`mcp__plugin_telegram_telegram__*`), which match nothing
   elsewhere. Worker runtimes report through their own channel (see the
   Communication Channel section of `AGENTS.md`).
3. **Permissions.** Every runtime has its own format: Claude allow/deny rules,
   Codex sandbox and approval settings, Cursor `cli.json`, Copilot CLI flags,
   OpenCode `permission`, Amp `mcpPermissions`. Gemini's project policy tier
   is documented as non-functional
   ([policy engine](https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/policy-engine.md)).
   Tess renders only Claude's settings and Codex's `config.toml`.
4. **Commands.** There is no universal slash-command format. Agent Skills are
   the closest shared unit ([agentskills.io](https://agentskills.io)), and
   manual-only invocation is runtime-specific (`disable-model-invocation` in
   Claude, `allow_implicit_invocation` in Codex).
5. **Size and loading.** Codex caps the whole `AGENTS.md` chain at 32 KiB,
   shared with the user's global file; Devin Desktop limits a workspace rule to
   12,000 characters. Kimi Code warns above 32 KiB of `AGENTS.md` in total;
   DeepSeek Harness truncates its `AGENTS.md` + `CLAUDE.md` baseline at
   65,536 bytes; Grok Build has no cap but loads `CLAUDE.md` as well. The lean
   worker `AGENTS.md` is kept at or under 12,000 bytes for that reason.
6. **Model- and harness-specific features.** Subagent `effort`,
   `isolation: worktree`, `memory`, forked context and `${CLAUDE_*}`
   substitutions are Claude Code only
   ([sub-agents](https://code.claude.com/docs/en/sub-agents.md),
   [skills](https://code.claude.com/docs/en/skills.md)).

## 2. Adapter manifests (C0–C4)

Every platform is also described by a versioned local manifest and a support
level. A manifest records evidence and limits; it never grants permissions or
changes the gate.

### Levels

| Level | Meaning | Public claim allowed |
|---|---|---|
| C0 | No adapter or driver exists. | Not supported. |
| C1 | A bounded, read-only research worker may return cited material. | Research-worker preview only. |
| C2 | Instructions or local artifacts can support a human/manual gate; an unproven local driver may exist. | Manual-gated compatibility preview. |
| C3 | A managed/reference adapter has documented lifecycle evidence beyond C2. | Managed-adapter preview, never protected delivery. |
| C4 | Certified protected workflow. | Only after independent conformance evidence and external admission controls. |

`adapter-manifest.v1` deliberately accepts **C0–C3 only**. A self-authored
JSON file cannot assert C4. C4 requires independent evidence of capability
mapping, artifact provenance, denied actions, version-drift handling,
isolation, and required external enforcement. It also depends on the
production prerequisites in [Support and status](../docs/STATUS.md).

The distinction between C2 and C3 is evidence, not whether a local driver is
present. Codex can expose a local process-driver at C2 while its lifecycle and
native-parity evidence remain incomplete. C3 is the managed/reference-preview
bar; neither level is protected delivery.

### Manifest contract

The advisory schema is
[`contracts/adapter-manifest.schema.json`](contracts/adapter-manifest.schema.json).
Records live in [`manifests/`](manifests/):

- Claude Code — C3 managed-adapter preview
- Codex — C2 manual-gated compatibility preview
- Generic AGENTS.md host — C2 manual-gated compatibility preview
- Perplexity — C0, no adapter or driver

The schema is intentionally outside `core/contracts/`, is not accepted by
`tessctl validate`, and is never a gate, policy, signing, key, verifier, or
approval input. It is validated by a dependency-free offline test harness;
the harness performs no provider calls and writes no repository state. It
checks schema shape plus repository-local evidence-pointer containment and
existence; it does not certify a provider's live behavior.

### Local advisory check

From a source checkout, run:

```sh
python3 -m tools.validate_adapter_manifests --root . --json
```

The result is stable JSON with `"advisory": true`, `"valid"`, and a sorted
`"findings"` list. Exit `0` means the local advisory records are structurally
consistent; exit `1` means they are not. The checker accepts exactly the
canonical manifests, rejects duplicate JSON keys, symlink/non-regular inputs
and evidence, and compares the fixed claims to literal registry keys parsed
from `.tess/bin/tessctl` with Python AST—without importing or executing that
source.

It is strictly read-only and offline: no provider calls, credentials,
subprocesses, writes, mutation flag, runtime integration, policy decision, or
gate integration exists. A passing result is neither an approval nor C4
certification. It proves literal-declaration parity and reports detected direct
reflective access; it does not prove arbitrary runtime data flow or semantic
behavior.

### Promotion rule

Promotion changes documentation and evidence first; it does not change a
trust boundary by itself. A C4 proposal must be a separate protected change
with independent evidence and the external, human-owned trust-root decision.
Until then, platform labels remain exact descriptions of the artifact surface
that is actually present.
