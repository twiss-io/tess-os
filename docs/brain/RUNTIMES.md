# Runtimes: what the brain does in each one, and how reliably

Tess OS is plain files, so the same brain works in every agent runtime. What
differs between runtimes is what happens mechanically and what depends on the
model following an instruction. This page states that honestly for v0.2.0.
[LEARNING.md](LEARNING.md) explains the mechanism itself.

**Labels:**

| Label | Meaning |
|---|---|
| **M** | Mechanical: a script or hook does it, whatever the model does. |
| **M/T** | Mechanical once the runtime's one-time trust step is done. |
| **M/S** | Mechanical, by sweeping the runtime's own transcript files. |
| **I** | Depends on the model following an instruction; it may forget. |
| **U** | Unverified. |

## Matrix (v0.2.0)

Versions tested: Claude Code 2.1.281, Codex CLI 0.145.0 and Gemini CLI 0.61.0.
Kimi Code and other AGENTS.md tools were checked against their docs only.

### Claude Code 2.1.281

| Area | Behaviour | Label |
|---|---|---|
| Loads | `CLAUDE.md` with the BOOT block. An entity's `CLAUDE.md` (`@AGENTS.md`) loads on demand | M load, I follow |
| Skills | `.claude/skills/brain-*` and the Tess commands | |
| Onboarding trigger | SessionStart hook line, plus BOOT and the skill | M/T, then I |
| Conversation capture | Async Stop hook, plus a 7-day backfill at SessionStart and `turns.jsonl` for the current turn | M/T |
| Decisions, preferences, corrections | Cue pass and the prompt nudge, plus `brain-distill` | M/T, plus I for distill |
| Verify, promote, caps | the tools | M |
| Native memory | Turned off at project level (`autoMemoryEnabled: false`) | |
| Known gaps | `--bare` skips hooks and CLAUDE.md; transcripts are cleaned up after 30 days | |

### Codex CLI 0.145.0

| Area | Behaviour | Label |
|---|---|---|
| Loads | `AGENTS.md` from the git root down to the working directory, with BOOT. Works untrusted. Codex silently cuts the chain at 32 KiB | M load, I follow |
| Skills | `.agents/skills/{tess,brain}-*` (`$name`) | |
| Onboarding trigger | BOOT and the skill | I |
| Onboarding trigger, after the hooks are approved in `/hooks` | hook line | M/T |
| Conversation capture | Sweep of `$CODEX_HOME/sessions` | M/S |
| Conversation capture, after the hooks are approved in `/hooks` | Stop hook, per turn | M/T |
| Decisions, preferences, corrections | Cue pass at the sweep, plus distill | M/S, plus I |
| Verify, promote, caps | the tools, run from the shell | M |
| Native memory | Memories are off by default | |
| Known gaps | A fresh clone's first session runs no hooks. The rollout format is "not a stable interface". On the test machine the model is pinned with `-m gpt-5.5` | |

### Gemini CLI 0.61.0

| Area | Behaviour | Label |
|---|---|---|
| Loads | `GEMINI.md` imports `@./AGENTS.md` with BOOT (trusted folders) | M/T load, I follow |
| Skills | `.agents/skills` and `/tess:*` (trusted) | |
| Onboarding trigger | BOOT through the import, plus the skill | I |
| Conversation capture | Sweep of `~/.gemini/tmp/<project>/chats` (verified 2026-09-24) | M/S |
| Decisions, preferences, corrections | Cue pass at the sweep | M/S |
| Verify, promote, caps | the tools, run from the shell | M |
| Native memory | Auto Memory is off by default | |
| Known gaps | No brain hooks. An untrusted headless run exits 55 | |

### Kimi and other AGENTS.md tools

| Area | Behaviour | Label |
|---|---|---|
| Loads | `AGENTS.md`, if the tool reads it | U |
| Skills | `.agents/skills` (per Kimi's docs) | U |
| Onboarding trigger | BOOT | I |
| Conversation capture | `tessbrain.py journal note` | I |
| Decisions, preferences, corrections | the skills | I |
| Verify, promote, caps | the tools, if the tool can run a shell | M |
| Native memory | tool-specific | |
| Known gaps | instruction only | |

### Consumer apps

ChatGPT, the Gemini app, Grok, Kimi web and Claude.ai are not Tess runtimes.
They load nothing from Tess and have no skills, capture or onboarding trigger;
they keep their own provider memory. Importing their exports is v0.2.1.

## Per runtime

### Claude Code

- **Hooks** (wired by `.claude/settings.json`). Every command is a guarded
  `sh -c` line that does nothing when the script is absent:
  - SessionStart (`startup|resume|clear|compact`) prints the brain snapshot:
    what was learned since the last session, review items, unsaved or
    unpushed work, un-journaled sessions, misplaced files, budgets and
    errors. The snapshot is at most 4 KB and takes at most 2 s. It also
    starts a detached, locked 7-day backfill.
  - UserPromptSubmit appends the redacted prompt to `turns.jsonl` and prints
    at most 2 nudge lines.
  - Stop (`async`) starts a detached `sync` of that transcript and returns at
    once.
- **Trust.** One workspace-trust click. `claude -p` runs project hooks. On
  the test machine, an untrusted `-p` run printed "Ignoring N
  permissions.allow entries" but still ran the hooks.
- **Verified live on 2026-09-24** (`tests/smoke/brain_learn_live.sh claude`,
  on a create-tess scaffold with the v0.2 onboarding wiring, `--model haiku`):
  - the Stop hook journaled the session with no manual sync;
  - after `sync`, the decision, preference, correction and open loop were
    recorded with verbatim quotes;
  - no MongoDB decision was recorded, and the planted token was absent;
  - the SessionStart snapshot reached the model (the nonce test).

### Codex CLI

- **Mechanical without any setup: the sweep.** `tessbrain.py sync` (and
  `status`, `brain-save`, and the Claude SessionStart backfill) reads
  `$CODEX_HOME/sessions/**/rollout-*.jsonl` (default `~/.codex/sessions`). It
  keeps the rollouts whose `session_meta.cwd` realpath is inside this repo,
  or inside a path in `capture.also_cwd`. User text comes from `event_msg`
  `user_message`, and unknown record types are skipped.
- **Per-turn, after trust.** `.codex/hooks.json` has SessionStart,
  UserPromptSubmit and Stop, each `sh -c 'exec python3 "$(git rev-parse
  --show-toplevel)/scripts/brain/tessbrain.py" hook <event> --runtime codex'`.
  Codex runs project hooks only in a trusted project, after the operator
  approves them in `/hooks`. The approval is hash-pinned, so these lines never
  change.
- **Verified live on 2026-09-24:**
  - `smoke codex`: `codex exec -m gpt-5.5 -s read-only` with a scratch
    `CODEX_HOME`, then `sync --runtime codex`. All capture checks passed.
  - `smoke codex-hooks`: a trusted scratch project run with
    `--dangerously-bypass-hook-trust`, from the repo root and from a
    subdirectory. Both runs returned the SessionStart nonce, and the Stop hook
    wrote the `-codex-` journal with no manual sync.

### Gemini CLI

- **Mechanical without any setup: the sweep, M/S.** It was verified against a
  real Gemini CLI 0.61.0 run in a scratch HOME on 2026-09-24:
  - `~/.gemini/projects.json` maps the project root to a short name;
  - `~/.gemini/tmp/<name>/.project_root` holds the root;
  - sessions are `chats/session-<time>-<id>.jsonl`: a header line
    (`sessionId`, `projectHash` = sha256 of the root, `startTime`), then
    `user`/`gemini` records and `$set` updates.

  The sweep also accepts the older `tmp/<sha256>/` layout. The injected
  `<session_context>` preamble is skipped.
- **Verified live on 2026-09-24:** `smoke gemini` (scratch HOME, API-key
  login): the journal note, the verbatim decision with a clean lint, and no
  planted token.
- **No brain hooks in v0.2.0.** Gemini hooks are v0.2.1.

### Kimi Code and other AGENTS.md tools

These are instruction-only. The `brain-save` skill tells the agent to run
`tessbrain.py journal note --text "<the operator's words>"`. A hand-written
note is never auto-promoted: the agent writes it, not the runtime, so the
operator confirms it in review.

## Trust steps (the only configuration)

| Runtime | Step | What it enables | What works without it |
|---|---|---|---|
| Claude Code | One workspace-trust click | project hooks and `permissions.allow` | CLAUDE.md + BOOT, commands, skills |
| Codex CLI | Optional: trust the project, then approve 3 hooks in `/hooks`; re-approve after any hook change | per-turn capture and the SessionStart snapshot | AGENTS.md + BOOT, skills; capture by sweep |
| Gemini CLI | One folder-trust click | GEMINI.md and `/tess:*` | `.agents/skills`; capture by sweep |

## Hermetic test recipes (no global config written)

```
Claude:  cd <fx> && CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 claude -p "<probe>" --model haiku --setting-sources project,local [--no-session-persistence] < /dev/null
Codex:   cd <fx> && codex exec --ephemeral --ignore-user-config -m gpt-5.5 -s read-only "<probe>" < /dev/null
Codex + capture: CODEX_HOME=<scratch>/ch (auth.json symlinked to ~/.codex/auth.json; config.toml: model = "gpt-5.5") codex exec -m gpt-5.5 -s read-only "<probe>"
Codex + hooks:   add [projects."<abs fx>"] trust_level = "trusted" to the scratch config.toml and pass --dangerously-bypass-hook-trust
Gemini:  HOME=<scratch>/ghome GEMINI_CLI_TRUST_WORKSPACE=true gemini -p "<probe>" < /dev/null
```

**Proof method:**

1. Plant a `[A-Z]+-NONCE-[A-Z0-9]+` token in hook output (`TESS_BRAIN_TEST_NONCE`).
2. Ask the model to list every such token it sees.
3. Never trust the model's own account of what it read.

`tests/smoke/brain_learn_live.sh <claude|codex|gemini|codex-hooks|probe> <scratch-dir> [framework-dir]`
runs all of this. The `probe` mode is the zero-context test: it commits,
pushes and clones the brain, then asks a fresh Claude and a fresh Codex 5
questions from the files alone. A clone taken before the conversation is the
negative control. The smokes delete their scratch homes, and the one Claude
project folder they create, afterwards.

## Known gaps in v0.2.0

- Claude Code under `--bare` runs no hooks and loads no CLAUDE.md.
- Codex's first session in a fresh clone runs no hooks, so it is captured by
  the sweep.
- Gemini has no brain hooks.
- Kimi and other AGENTS.md tools are instruction-only.
- Distilling implicit decisions depends on the model in every runtime.
- Claude and Gemini delete transcripts after about 30 days, so capture must
  run inside that window: any `sync`, `status` or new Claude session does it.
