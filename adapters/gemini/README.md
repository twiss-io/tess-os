# Adapter — Gemini CLI (`gemini` render target)

> **Level: Advisory** (the [CONFORMANCE](../CONFORMANCE.md) scale). Tess
> doctrine and commands load natively in Gemini CLI, but nothing Tess ships
> can block a Gemini tool call: no Tess hook is translated. (Partial on that
> scale needs some enforcement that Tess renders, as Codex gets its sandbox
> and approval settings; Gemini gets none.)
> The ship-gate is still enforced at git pre-push and in CI, like for every
> runtime. The target was verified against Gemini CLI **0.61.0** (docs at
> tag `v0.61.0`, identical to `main` on 2026-09-24) with an install, help and
> config smoke plus the CLI's own loaders. **No model run against a
> rendered project was made.**
> Compared with Claude Code this target is not at parity, and nothing here
> claims it is.

Implementation: `GeminiRenderTarget` in `.tess/bin/tessctl` (the
"GEMINI TARGET" block). Template: `.tess/core/templates/gemini/GEMINI.md.tpl`.
Conformance row: [`../CONFORMANCE.md`](../CONFORMANCE.md). Advisory record:
[`../manifests/gemini.adapter-manifest.json`](../manifests/gemini.adapter-manifest.json).

## What `tessctl render --target gemini` writes

| Path | What it is | Source |
|---|---|---|
| `AGENTS.md` | The worker-profile doctrine digest. Byte-identical to what the `codex` and `generic` targets write. | `render_agents_md()` |
| `GEMINI.md` | A short header plus one `@./AGENTS.md` import line. | `.tess/core/templates/gemini/GEMINI.md.tpl` |
| `.gemini/commands/tess/<name>.toml` | One Gemini custom command per `.tess/core/commands/<name>.md` (26 today), invoked as `/tess:<name>`. | the command bodies |

It never writes `.gemini/settings.json`, `.gemini/policies/**`, `.gemini/agents/**`
or any hook. `tess.manifest.json` owns exactly `GEMINI.md` and
`.gemini/commands/tess/**` (plus the shared `AGENTS.md`), so an operator's own
`.gemini/commands/**`, settings and policies stay out of reach.

## Context route: GEMINI.md imports AGENTS.md

Gemini CLI's default context file is `GEMINI.md`. It loads it from the
workspace directories and their parents
([gemini-md.md L3](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/gemini-md.md#L3),
[L23-L26](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/gemini-md.md#L23-L26)).
It does not read `AGENTS.md` unless settings `context.fileName` names it
([gemini-md.md L94-L98](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/gemini-md.md#L94-L98),
[configuration.md L1690-L1694](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/reference/configuration.md#L1690-L1694);
default `undefined`; source: `DEFAULT_CONTEXT_FILENAME = 'GEMINI.md'` in
[memoryTool.ts L11](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/packages/core/src/tools/memoryTool.ts#L11)).

Two routes were possible:

1. **Chosen: `GEMINI.md` with `@./AGENTS.md`.** `GEMINI.md` supports
   `@file.md` imports with relative paths
   ([gemini-md.md L71-L74](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/gemini-md.md#L71-L74),
   [memport.md L31-L33](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/reference/memport.md#L31-L33)).
   Tess owns only a file it fully generates.
2. Rejected: a rendered `.gemini/settings.json` with
   `{"context": {"fileName": ["AGENTS.md"]}}`. That file also holds the
   operator's hooks, MCP servers and other settings
   ([hooks/index.md L94-L99](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/hooks/index.md#L94-L99)),
   so rendering it would take ownership of a user-edited file.

Only one route is rendered. Rendering both would load the doctrine twice.
If an operator adds `AGENTS.md` to `context.fileName` themselves, it also
loads twice; the generated `GEMINI.md` says so.

**Import hazard, guarded by a test.** Gemini's import scanner treats any `@`
at the start of a line or after whitespace, followed by a path starting with
`.`, `/` or a letter, as an import, except inside backtick code spans
([memoryImportProcessor.ts L103-L153](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/packages/core/src/utils/memoryImportProcessor.ts#L103-L153),
code spans [L167-L177](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/packages/core/src/utils/memoryImportProcessor.ts#L167-L177)).
A missing file becomes an error comment in the loaded text
([memport.md L106-L109](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/reference/memport.md#L106-L109)).
`tests/test_v02_gemini_target.py` ports that scanner and fails if the
rendered `AGENTS.md` ever contains such a token, or if `GEMINI.md` contains
anything but the one `@./AGENTS.md` import.

### Trusted folders: both routes need one

In 0.61.0 folder trust is **on by default**
([configuration.md L1978-L1982](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/reference/configuration.md#L1978-L1982):
`security.folderTrust.enabled`, default `true`). The trusted-folders page
still says the feature is disabled by default
([trusted-folders.md L10](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/trusted-folders.md#L10)).
The CLI's behaviour matches the configuration reference: a headless run in a
folder it has not been told to trust exits with code 55 and "Gemini CLI is
not running in a trusted directory".

In an untrusted folder:

| Artifact | Loaded? | Evidence |
|---|---|---|
| `.gemini/settings.json` (route 2) | No | [trusted-folders.md L77-L79](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/trusted-folders.md#L77-L79) |
| Project `GEMINI.md` (route 1) | No | the docs only say memory loading is restricted ([trusted-folders.md L90-L91](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/trusted-folders.md#L90-L91)); the source skips workspace context files when the folder is untrusted ([memoryContextManager.ts L50-L60](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/packages/core/src/context/memoryContextManager.ts#L50-L60)) |
| `.gemini/commands/**` | No | [trusted-folders.md L96-L98](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/trusted-folders.md#L96-L98), [FileCommandLoader.ts L215-L225](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/packages/cli/src/services/FileCommandLoader.ts#L215-L225) |

So neither route works untrusted. Tess under Gemini CLI needs the project
folder trusted (interactively, or `--skip-trust` /
`GEMINI_CLI_TRUST_WORKSPACE=true` for one session,
[trusted-folders.md L110-L118](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/trusted-folders.md#L110-L118)).

## Commands

| Tess command file | Gemini custom command | Evidence |
|---|---|---|
| `.tess/core/commands/wake.md` | `.gemini/commands/tess/wake.toml`, run as `/tess:wake` | a subdirectory becomes a namespace, [custom-commands.md L25-L31](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/custom-commands.md#L25-L31); project commands live in `<project>/.gemini/commands/`, [L14-L17](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/custom-commands.md#L14-L17) |
| frontmatter `description:` | `description` (string) | [custom-commands.md L49-L54](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/custom-commands.md#L49-L54) |
| body | `prompt` (required string) | [custom-commands.md L44-L47](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/custom-commands.md#L44-L47) |
| `$ARGUMENTS` | `{{args}}`, replaced raw with the text typed after the command | [custom-commands.md L62-L84](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/custom-commands.md#L62-L84) |
| no `$ARGUMENTS` | nothing to map: Gemini appends the typed command to the prompt | [custom-commands.md L115-L126](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/custom-commands.md#L115-L126) |

Rendering rules:

- **No shell or file injection.** Gemini executes `!{...}` in a command
  prompt as a shell command and inlines `@{...}` as file content
  ([custom-commands.md L165-L186](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/custom-commands.md#L165-L186),
  [L223-L246](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/custom-commands.md#L223-L246);
  triggers `!{` and `@{` in
  [types.ts L44-L54](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/packages/cli/src/services/prompt-processors/types.ts#L44-L54)).
  There is no escape syntax, so the renderer breaks either trigger with a
  space (`! {`, `@ {`). No shipped body contains one today; a test proves a
  hostile body cannot produce one.
- **Escaping.** The prompt is a TOML multi-line literal string (`'''`), so the
  body is kept exactly. If the body contains `'''`, ends in `'` or has a
  control character, the renderer uses a basic multi-line string (`"""`)
  with every backslash, double quote and control character escaped. Gemini
  parses these files with `@iarna/toml`
  ([FileCommandLoader.ts L9](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/packages/cli/src/services/FileCommandLoader.ts#L9)).
- **Links.** Command bodies link doctrine relative to `.claude/commands/`
  (`../../conductor/x.md`). A Gemini prompt is plain text read from the
  project root, so those links become root-relative (`conductor/x.md`).
- **Command bodies are mirrored, not re-scoped.** Like the Codex prompts,
  the 26 bodies still carry orchestrator wording; only the always-loaded
  `AGENTS.md` digest is worker-profile. Auditing the bodies is separate work.

If the `codex` target renders Tess commands as Agent Skills under
`.agents/skills/`, Gemini CLI discovers those too (workspace skills alias,
[skills.md L46-L53](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/skills.md#L46-L53)).
The skills are model-activated; the `/tess:<name>` commands are
user-invoked.

## Hooks: none translated

A Gemini hook must print only JSON on stdout. Plain text breaks parsing, and
the CLI then allows the action and shows the text to the user as a
`systemMessage`
([hooks/index.md L56-L65](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/hooks/index.md#L56-L65),
[hooks/reference.md L8-L17](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/hooks/reference.md#L8-L17)).
Hooks are configured only in `settings.json`
([hooks/index.md L92-L99](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/hooks/index.md#L92-L99)),
which this target does not own.

| Tess hook (Claude Code event) | Closest Gemini event | Translated? | Why not |
|---|---|---|---|
| `utc-local-context.sh` (UserPromptSubmit) | `BeforeAgent` ([reference.md L145-L161](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/hooks/reference.md#L145-L161)) | No | The script prints plain text. Gemini would show it to the user instead of adding it to the model's context; only `hookSpecificOutput.additionalContext` JSON is added. |
| `dispatch-guard.sh` (PreToolUse Bash/Edit/Write) | `BeforeTool` | No | Different tool names (`run_shell_command`, `write_file`, `replace`) and output contract; the Rule Zero guard does not apply to a worker-profile runtime. |
| `task-lock-set.sh`, `task-lock-clear.sh`, `vault-dispatch-scan.py` (Task/Agent) | none | No | Tess renders no Gemini subagents to dispatch. |

No `.gemini/policies/**` is rendered either: the workspace policy tier does
not work in Gemini CLI today
([policy-engine.md L127-L131](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/reference/policy-engine.md#L127-L131),
[issue #18186](https://github.com/google-gemini/gemini-cli/issues/18186), open
on 2026-09-24).

## Enabling it

- **New installs** (`npm create tess` from this manifest): `gemini` is in
  `render_targets.enabled`, and `GEMINI.md` plus `.gemini/commands/tess/**`
  are owned globs.
- **Existing installs** keep their own manifest, which lacks both, so no
  Gemini file is written by `tessctl update`. To opt in, add `"gemini"` to
  `render_targets.enabled` and `"GEMINI.md"`, `".gemini/commands/tess/**"` to
  `owned_globs` in `tess.manifest.json`, then run
  `tessctl render --target gemini`. If you already have a hand-written
  `GEMINI.md`, move its content elsewhere first.

## Customising the rendered files

`render` and `doctor --fix` keep a hand edit to `GEMINI.md` or to a
`.gemini/commands/tess/*.toml` file and report it as a "hand-edited render
output". `doctor` fails on it until you choose one of these:

- **Keep your version:** `tessctl publish GEMINI.md` (or the `.toml` path).
  Its status becomes `user-published` and `render` stops writing it.
- **Instructions for all your projects:** put them in `~/.gemini/GEMINI.md`,
  the global context file Gemini loads before the workspace one
  ([gemini-md.md L18-L21](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/gemini-md.md#L18-L21)).
  Tess never writes it.
- **Your own commands:** put them anywhere under `.gemini/commands/` except
  `tess/`. Tess owns only `.gemini/commands/tess/**`.
- **Discard the edit:** delete the file and run `tessctl render`.

The hint that `render` and `doctor` print also suggests `GEMINI.local.md`
(and `AGENTS.local.md` for `AGENTS.md`). **In v0.2.0 that route does not
work for these two files.** The gemini and generic targets do not merge a
`.local.md` file, and Gemini CLI loads only the names in `context.fileName`
(default `GEMINI.md`;
[gemini-md.md L94-L98](https://github.com/google-gemini/gemini-cli/blob/v0.61.0/docs/cli/gemini-md.md#L94-L98)).
An edit moved there has no effect, and nothing warns you. Checked on
2026-09-24: after writing both files and running `tessctl render`, neither
line appeared in `GEMINI.md` or `AGENTS.md`.

## Verification (2026-09-24)

- **Docs:** every claim above cites the v0.61.0 docs or source by line.
- **Install smoke**, all under a scratch prefix and a scratch `HOME`, never
  a real `~/.gemini`, with no Gemini credentials in the environment:
  `npm i --prefix <scratch>/gemini-cli @google/gemini-cli@0.61.0`, then
  `gemini --version` (prints `0.61.0`), `gemini --help` and, in a scaffold
  rendered with this target, `gemini skills list` (a listing command that
  needs no auth). The exact commands and output are in the PR.
- **The CLI's own loaders:** the bundled `FileCommandLoader` loads all 26
  `.gemini/commands/tess/*.toml` as `tess:*` workspace commands with their
  descriptions, `/tess:add-mission <text>` substitutes the text for
  `{{args}}`, and the bundled memory loader finds `GEMINI.md` and expands
  `@./AGENTS.md` without an import error. No model call is involved.
- **Not verified:** a live Gemini session following the doctrine. That needs
  a Google login or API key and is outside this release.
