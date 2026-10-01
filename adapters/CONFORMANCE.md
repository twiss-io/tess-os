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

Claude Code is the reference runtime, where Tess's gates run as designed.
Since v1.0 Codex also runs a Tess gate of its own (after a one-time trust and
`/hooks` approval); it covers different ground from the Claude hooks, as the
Codex row says. Every other runtime is weaker, and this page says how. It is
not a parity claim.

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
| Claude Code | `claude-code` | Enforced | `CLAUDE.md` (plus cwd ancestors, `.claude/rules/`), `.claude/agents/`, `.claude/commands/`, `.claude/skills/`, and the hooks in `.claude/settings.json`. | Reference runtime. All shipped hooks run natively (PreToolUse on `Task\|Agent`, on `Bash\|Edit\|Write` and, since v1.0, the Tess safety gate on `Bash\|Edit\|Write\|MultiEdit\|NotebookEdit`; PostToolUse, SessionEnd, UserPromptSubmit); exit 2 or `permissionDecision: "deny"` blocks, `"ask"` asks the user. `dispatch-guard.sh` only warns by design. Since v1.0 Tess's PreToolUse safety gate (`.claude/hooks/tess-gate.py`, sha-pinned, run through `run-pinned.py --on-fail block`) runs on every `Bash`, `Edit`, `Write`, `MultiEdit` and `NotebookEdit` call and blocks edits to Tess's security-tier and enforcement files, `--no-verify`/`core.hooksPath` bypasses, `gh auth token`, secret-shaped values in commands, and a push of brain/ or clients/ data to a public or unverifiable remote; force pushes, remote changes and visibility changes ask you first (denied in `bypassPermissions`/`dontAsk` mode, which cannot ask). Checked live with Claude Code 2.1.284 in a fresh install on 2026-09-29: `git commit --no-verify` and an Edit to `conductor/guardrails.md` were blocked by the Tess gate (its decision log recorded both). The hooks also run in `claude -p` in a folder that was never trusted, but the project's tool allow list does not (see docs/brain/ONBOARDING.md). The shell checks read the command text: an inline `python -c`/`node -e`/`perl -e` program (or a heredoc fed to one) that names a protected path and calls a write-shaped API is denied best effort, and so are `GIT_CONFIG_*` assignments and git `include.*`/`includeIf.*`/`alias.*` config writes; a script file an interpreter runs and commands assembled at run time are not seen. An agent cannot fake a terminal or type `accept v<N>` to answer `tessctl update` or `tessctl approve` for the operator. The ship gate in git and CI stays the wall. It reads `AGENTS.md` only when no `CLAUDE.md` exists, so in a Tess install it ignores `AGENTS.md`. It does not read `.agents/skills/`. | [memory](https://code.claude.com/docs/en/memory.md), [hooks](https://code.claude.com/docs/en/hooks.md), [skills](https://code.claude.com/docs/en/skills.md), [sub-agents](https://code.claude.com/docs/en/sub-agents.md) |
| OpenAI Codex CLI | `codex` | Enforced | `AGENTS.md` (root to cwd, one file per directory, `project_doc_max_bytes` cap, 32 KiB by default), the installed roles as custom agents in `.codex/agents/<role>.toml` (spawned with `spawn_agent` + `agent_type` when the operator asks for a role; `AGENTS.md` names the roles and the spawn rules), the 26 commands as `.agents/skills/tess-*/SKILL.md` (explicit-only via `agents/openai.yaml`, run with `$tess-<command>`), `.codex/config.toml` (`approval_policy = "on-request"`, `sandbox_mode = "workspace-write"`, the SessionStart onboarding hook, and the v1.0 PreToolUse safety gate), and `.codex/rules/tess.rules` (prefix-rule backstop). | **Enforced once the project is trusted and Tess hooks are approved in `/hooks`** (the one-time setup below). The README and STATUS runtime tables must agree with this row (`tests/test_v02_readme_conformance_levels.py`). Doctrine and roles load natively. Since v1.0 a Tess PreToolUse hook runs on every shell command (`Bash`, covering shell and `exec_command`), file edit (`apply_patch`), subagent spawn (`spawn_agent`) and MCP tool call. It runs `.claude/hooks/tess-gate.py` through the sha-pinned `run-pinned.py --on-fail block`, so a missing, edited or unpinned script blocks the call. It denies: secret-shaped values in commands and dispatches; edits to Tess's security-tier and enforcement files; `--no-verify`, `git commit -n` and `core.hooksPath` bypasses; `gh auth token`; and a push that would publish brain/ or clients/ data to a public or unverifiable remote (the pre-push guard's own check). Codex cannot ask from a hook (an "ask" fails the hook and runs the command), so force pushes, remote changes and visibility changes are denied with a message telling the user to run them. Checked live with codex-cli 0.158.0 and `gpt-6-astra` on 2026-09-29: `git commit --no-verify` and an `apply_patch` to `conductor/guardrails.md` were blocked, and a normal edit and commit went through ([codex/README.md](codex/README.md)). **One-time setup**: Codex runs project hooks and rules only in a trusted project, and only after the operator approves the Tess hooks in `/hooks`; approval is pinned to the hook's hash, so re-approve after a Tess update. Until then Codex's sandbox and approval settings apply, and nothing Tess ships blocks a call. **Limits**: the shell checks read the command text. Since the v1.0.0 security review they also deny `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM`/`GIT_CONFIG_PARAMETERS` assignments, git `include.*`/`includeIf.*`/`alias.*` config writes, writes after a `cd` into a protected directory (the working directory is tracked across `cd`), and, best effort, an inline `python -c`/`node -e`/`perl -e` program (or a heredoc fed to one) that names a protected path and calls a write-shaped API; a script file an interpreter runs, commands assembled at run time and other interpreter writes are still not seen. Codex `write_stdin` (typed input sent into an already-open unified-exec shell) does not run PreToolUse again, so anything typed into a shell the gate already allowed is never checked. A PreToolUse hook that times out (the gate's limit is 120 s) or crashes in the host fails OPEN in Codex for that call; `run-pinned.py --on-fail block` covers a missing or edited script, not a hook the host itself gives up on. Hosted tools (web search) skip hooks; the Claude-only warn hooks (dispatch-guard, task locks, UTC context) are not rendered because the Codex target uses the worker profile; the docs call Codex hooks "a useful guardrail, not a complete enforcement boundary". The ship gate in git and CI stays the wall. | [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md.md), [subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents.md), [skills](https://learn.chatgpt.com/docs/build-skills.md), [hooks](https://learn.chatgpt.com/docs/hooks.md), [rules](https://learn.chatgpt.com/docs/agent-configuration/rules.md), [config](https://learn.chatgpt.com/docs/config-file/config-reference.md), [openai/codex#9848](https://github.com/openai/codex/issues/9848) |
| Any AGENTS.md reader (generic) | `generic` | Advisory | `AGENTS.md` plus a plain `prompts/<command>.md` mirror with no harness-specific frontmatter. | Text only: nothing in the generic output can block a tool call. Use it for runtimes with no Tess target. | [agents.md](https://agents.md/) |
| GitHub Copilot CLI | none (reads `claude-code` output) | Partial | Loads `CLAUDE.md`, `AGENTS.md`, `.github/instructions`, `.claude/agents`, `.claude/commands`, `.claude/skills`, `.agents/skills` and the hooks in `.claude/settings.json`. | Tess's Claude hooks run. Command `preToolUse` hooks fail closed on a crash or non-zero exit, but timeouts always fail open. The Copilot cloud agent reads only `.github/hooks/*.json`, which Tess does not render. It merges `CLAUDE.md` and `AGENTS.md`, so doctrine loads twice. | [custom instructions](https://docs.github.com/en/copilot/reference/custom-instructions-support), [hooks](https://docs.github.com/en/copilot/reference/hooks-reference), [CLI config](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference) |
| Cursor (IDE and CLI) | none (reads `claude-code` output) | Partial | `CLAUDE.md` (always applied) and `AGENTS.md`, `.claude/agents`, `.claude/skills`, `.agents/skills`, and the hooks in `.claude/settings.json` ("Include Third-Party Plugins, Skills, and Other Configs", on by default). | Claude hooks map onto 8 Cursor events; Notification and PermissionRequest are unsupported and Glob is unmapped. Exit 2 blocks, but crashes, timeouts and other non-zero exits fail open unless `failClosed: true`, which exists only in the native `.cursor/hooks.json`. Whether hook payloads carry Claude tool names is unverified. Doctrine loads twice. | [rules](https://cursor.com/docs/rules.md), [third-party hooks](https://cursor.com/docs/reference/third-party-hooks.md), [hooks](https://cursor.com/docs/hooks.md), [skills](https://cursor.com/docs/skills.md) |
| OpenCode | none (reads `AGENTS.md`) | Advisory | `AGENTS.md` walking up from cwd (`CLAUDE.md` only when there is no `AGENTS.md`); skills from `.agents/skills`. | Hooks are JS/TS plugins (`tool.execute.before`); Claude `settings.json` hooks are not read and no Tess plugin exists. | [rules](https://opencode.ai/docs/rules/), [plugins](https://opencode.ai/docs/plugins/), [skills](https://opencode.ai/docs/skills/) |
| Amp | none (reads `AGENTS.md`) | Advisory | `AGENTS.md` in cwd and parents (falls back to `AGENT.md` or `CLAUDE.md`); skills from `.agents/skills`. | No declarative hooks; tool approval is a TS plugin (`amp.on('tool.call')`) and no Tess plugin exists. | [AGENTS.md](https://ampcode.com/docs/markdown/customize/agents-md), [plugins](https://ampcode.com/docs/markdown/customize/plugins), [skills](https://ampcode.com/docs/markdown/customize/skills) |
| Devin Desktop (formerly Windsurf Cascade) | none (reads `AGENTS.md`) | Advisory | Root `AGENTS.md` becomes an always-on rule; a subdirectory `AGENTS.md` becomes a glob rule. | Its own `.devin/hooks.json` format with `pre_*` events and no subagent event; Tess does not render it. A 12,000-character limit applies to workspace rules; whether it also truncates `AGENTS.md` is unverified. | [AGENTS.md](https://docs.devin.ai/desktop/cascade/agents-md.md), [hooks](https://docs.devin.ai/desktop/cascade/hooks.md), [memories and rules](https://docs.devin.ai/desktop/cascade/memories.md) |
| Google Jules | none (reads `AGENTS.md`) | Advisory | `AGENTS.md` at the repository root. | Cloud agent with no documented hooks, commands or custom agents. | [docs](https://jules.google/docs/) |
| Aider | none (needs one config line) | Advisory | Never reads `AGENTS.md` automatically. Add `read: [AGENTS.md]` to `.aider.conf.yml`, or run `aider --read AGENTS.md`. | No hooks, custom agents or user commands. | [conventions](https://aider.chat/docs/usage/conventions.html) |
| Kiro | none (reads `AGENTS.md`) | Advisory | `AGENTS.md` is always included, at the root and in subdirectories. | Its own JSON hooks and agents; Tess renders neither. Checked through a summarising fetch, medium confidence. | [steering](https://kiro.dev/docs/steering/), [hooks](https://kiro.dev/docs/hooks/) |
| Qwen Code | none (reads `AGENTS.md`) | Advisory | Reads `AGENTS.md` alongside `QWEN.md`. | Claude-style `settings.json` hooks exist, but Tess renders no Qwen settings and the similarity is untested. | [Qwen Code docs](https://github.com/QwenLM/qwen-code/tree/main/docs) (features: memory, hooks) |
| Google Gemini CLI | `gemini` | Advisory | `GEMINI.md`, rendered as a short header plus an `@./AGENTS.md` import, so the worker doctrine loads through Gemini's own import syntax; the 26 commands as `.gemini/commands/tess/<command>.toml`, run as `/tess:<command>`. Skills also load from `.agents/skills`. Project context and commands load only in a trusted folder, and folder trust is on by default in 0.61.0. | Doctrine and commands are native, but nothing Tess ships can block a tool call: no Tess hook is translated (Gemini hooks must print only JSON on stdout and the Tess hooks print text), Gemini reads hooks only from `.gemini/settings.json`, which Tess does not render, and the project policy tier is documented as non-functional ([gemini-cli#18186](https://github.com/google-gemini/gemini-cli/issues/18186)). Checked with an install, `--version`, `--help` and `skills list` smoke on 0.61.0 and the CLI's own command and memory loaders; no live model run. Details: [`gemini/README.md`](gemini/README.md). | [GEMINI.md](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/gemini-md.md), [custom commands](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/custom-commands.md), [hooks](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/hooks/reference.md), [trusted folders](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/trusted-folders.md), [configuration](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/reference/configuration.md) |
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
  directory from the git root down to cwd, root first, up to
  `project_doc_max_bytes` in total (32 KiB by default).
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
  The `gemini` target renders a `GEMINI.md` that imports `AGENTS.md` with
  `@./AGENTS.md`, so do not also list `AGENTS.md` in `context.fileName`:
  the doctrine would load twice.
- **Aider** reads nothing automatically; add `read: [AGENTS.md]` to
  `.aider.conf.yml` ([conventions](https://aider.chat/docs/usage/conventions.html)).

### Commands as Agent Skills

The `codex` target renders the 26 commands as `.agents/skills/tess-<command>/`
(see [`codex/README.md`](codex/README.md)). Codex, Gemini CLI, Cursor, the
Copilot CLI, OpenCode and Amp all read `.agents/skills/`
([Codex](https://learn.chatgpt.com/docs/build-skills.md),
[Gemini](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/skills.md),
[Cursor](https://cursor.com/docs/skills.md),
[OpenCode](https://opencode.ai/docs/skills/),
[Amp](https://ampcode.com/docs/markdown/customize/skills)). Claude Code does
not; it uses `.claude/commands/`. Cursor and the Copilot CLI read both
`.claude/commands/` and `.agents/skills/`, so a codex-enabled install shows
each command twice there. The `agents/openai.yaml` explicit-only policy is a
Codex setting; other runtimes may still pick a skill implicitly from its
description.

### What does not translate

These six areas are Claude Code features or have no common format. Apart
from the Codex safety gate in item 1, nothing in this release renders them for
another runtime.

1. **Safety-gate hooks.** Tess's gates are Claude `PreToolUse` hooks; since
   v1.0 the same `.claude/hooks/tess-gate.py` runs in Claude Code
   (`--runtime claude`, where an "ask" asks). The
   `codex` target is the one exception: since v1.0 it renders its own
   PreToolUse gate (`.claude/hooks/tess-gate.py`) that reads Codex's payloads
   (`apply_patch` input carries the patch text, not a `file_path`, so the gate
   parses the patch's file headers) and sends every "ask" as "deny", because
   Codex fails an "ask" open. Codex also fails open when a hook times out
   or crashes, and `write_stdin` input to an already-running unified-exec
   shell never reaches PreToolUse. Hosted tools still skip hooks
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
2. **External notification channels.** The base harness has none: every
   runtime reports in its own session (see the Communication Channel section
   of `AGENTS.md`). A channel an operator adds is outside these levels.
3. **Permissions.** Every runtime has its own format: Claude allow/deny rules,
   Codex sandbox and approval settings, Cursor `cli.json`, Copilot CLI flags,
   OpenCode `permission`, Amp `mcpPermissions`. Gemini's project policy tier
   is documented as non-functional
   ([policy engine](https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/policy-engine.md)).
   Tess renders only Claude's settings and Codex's `config.toml` and
   `.codex/rules/tess.rules`.
4. **Commands.** There is no universal slash-command format. Agent Skills are
   the closest shared unit ([agentskills.io](https://agentskills.io)), and
   manual-only invocation is runtime-specific (`disable-model-invocation` in
   Claude, `allow_implicit_invocation` in Codex). The `gemini` target also
   writes Gemini's own TOML command files.
5. **Size and loading.** Codex caps the whole `AGENTS.md` chain at 32 KiB,
   shared with the user's global file; Devin Desktop limits a workspace rule to
   12,000 characters. The lean worker `AGENTS.md` is kept at or under 12,000
   bytes for that reason.
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
- Gemini CLI — C2 manual-gated compatibility preview
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
