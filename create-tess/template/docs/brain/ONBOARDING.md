# Onboarding: install, open, say "hi"

Onboarding turns a fresh Tess OS instance into the operator's second brain.
It runs inside the agent session, in any supported runtime, and it starts by
itself: the first reply to the operator's first message is the first
onboarding question. Background: [SECOND_BRAIN.md](SECOND_BRAIN.md). Modes and
the trees they create: [MODES.md](MODES.md).

## 1. Install

| Path | Command | Notes |
|---|---|---|
| Recommended | `npm create tess@latest my-brain` | Uses the bundled offline template and installs the gate hooks. |
| Plain copy | `npx degit twiss-io/tess-os/create-tess/template my-brain` | No wizard; run `git init` yourself. |
| Git clone | `git clone https://github.com/twiss-io/tess-os my-brain`, then say "convert this clone" | See section 6. The clone carries the framework's development tree. |

Requirements: git, python3 3.9 or newer, and one runtime CLI. The brain tools
(`scripts/brain/*.py`) use only the Python standard library. No API keys: each
runtime uses its own login. Nothing is written to your global config.

## 2. Open the folder in a runtime and say "hi"

```
cd my-brain
claude        # or: codex, gemini, kimi
```

Or use the launcher, which also passes the start prompt while onboarding is
pending: `scripts/tess claude|codex|gemini` (`--print-cmd` shows the command
without running it).

### The one trust step per runtime

| Runtime | Step | What it enables | Works without it |
|---|---|---|---|
| Claude Code | one workspace-trust click (`claude -p` counts as trusted; `--bare` skips hooks) | brain hooks (the onboarding reminder), tool permissions for the brain scripts | `CLAUDE.md` + BOOT, commands, skills |
| Codex CLI | none to start; optional: trust the project and approve the hooks in `/hooks` (approval is pinned to the hook text: re-approve after an update) | per-turn hooks | `AGENTS.md` + BOOT, `.agents/skills` |
| Gemini CLI | one folder-trust click (an untrusted headless run exits 55) | `GEMINI.md` (imports `AGENTS.md`) and the `/tess:*` commands | `.agents/skills` |
| Kimi and other AGENTS.md tools | tool-specific | nothing from Tess | `AGENTS.md` only |

### How onboarding starts itself

| Layer | Claude Code | Codex CLI | Gemini CLI | Label |
|---|---|---|---|---|
| BOOT rule in the entry file ("if `brain/brain.json` is missing or onboarding is not complete, your first reply is the next onboarding question") | `CLAUDE.md` | `AGENTS.md` | `GEMINI.md` -> `AGENTS.md` | I |
| `brain-onboard` skill, whose description starts "START HERE when brain/brain.json is missing or onboarding is not complete" | `.claude/skills/` | `.agents/skills/` | `.agents/skills/` | I |
| SessionStart hook line `ONBOARDING PENDING (step k/7): ...` from `onboard.py hook session-start` | after trust | v0.2.1 | v0.2.1 | M/T |
| Launcher start prompt (`claude "/brain-onboard"`, `codex '$brain-onboard'`, `gemini -i "Use the brain-onboard skill."`) | yes | yes | yes | M |

The hook is silent in the Tess OS source repo, once onboarding is complete or
skipped, while it is deferred, and under `TESS_BRAIN_QUIET=1` or
`TESS_HEADLESS=1`.

## 3. The interview: seven steps, one question per turn

Each answer is saved the moment it is given, with the operator's exact words
as its quote:
`python3 scripts/brain/onboard.py answer --step N --field K --value V --quote "..."`.

| Step | Question | Fields |
|---|---|---|
| 1 Mode | Who is this brain for? (a) just me: personal, (b) my firm, serving outside clients: agency, (c) an organisation with a team and roles: organisation. More than one is fine. | `mode` |
| 2 Preset | agency: `solo-consultant` or none; organisation: `startup` or none | `preset` |
| 3 Identity | your name and how to address you; my name (default Tess); your timezone (detected, then confirmed) | `operator_name`, `address_as`, `assistant_name`, `timezone` |
| 4 Principals | Besides you, whose words count as decisions here, and for what? | `principals` (name + scope) |
| 5 Seed entities | agency: name, one line on what you sell, up to 3 clients. organisation: name, your seat, up to 5 seats or units, do you serve outside clients? personal: areas and up to 3 projects | mode-specific |
| 6 Memory and privacy | journal policy: `commit-redacted`, `stub-only` or `local`; health and money are always private; what the model provider sees | `journal` |
| 7 Remote and runtimes | a private git remote or "later"; push after save (yes/no); which CLIs you use | `remote_url`, `autopush`, `runtimes` |

Rules the skill follows: never invent or paraphrase an answer; never fill a
field the operator did not answer; never record a suggestion, a question or a
hypothetical as an answer. Re-answering a field overwrites it.

`status --json` reports `pending`, `in_progress` (with the step), `complete`,
`deferred`, `skipped` or `source-repo`, plus `next_question` and the fields
still `missing`.

## 4. Apply

`python3 scripts/brain/onboard.py apply` (exit 3 until every step is answered):

- creates the mode tree under `brain/`, create-only: an existing file is
  reported `skipped (exists)` and its bytes are never changed;
- writes `brain/decisions/D-<YYYYMMDD-HHMM>-brain-mode.md` with status
  `pending-verification` and the step-1 answer as the quote;
- seeds `brain/probe.json`, `brain/.private/` (self-ignoring) and the managed
  `.gitignore` block;
- aligns `operator/profile.json` with the names given in step 3;
- commits: one seed commit if the repository has no commits yet, otherwise a
  path-scoped commit of `brain/` and `memory/projects/`, through the installed
  gate hooks. It never pushes.

A second `apply` changes nothing. `--dry-run` shows what would be created.

## 5. Resume, defer, skip

- **Resume.** State lives in tracked `brain/brain.json`, so any runtime on any
  machine resumes at the saved step, and a clone never re-onboards.
- **Defer.** "later": `onboard.py defer --days 7`. The reminder returns when
  `remind_after` passes.
- **Skip.** "skip onboarding": `onboard.py skip --quote "..."` sets up the
  personal layer with defaults and records the skip.

## 6. Converting a git clone

A plain `git clone` of the framework is the source repo: onboarding is off
there (`status` says `source-repo`, `apply` exits 3, the hook is silent). Say
"convert this clone", or run:

```
python3 scripts/brain/onboard.py convert-clone          # shows the plan
python3 scripts/brain/onboard.py convert-clone --yes
git remote add origin <your PRIVATE repository URL>
```

It renames `origin` to `upstream` when `origin` points at the public
framework repository, and writes `brain/brain.json` with status `pending`.

## 7. After onboarding

| Need | Command |
|---|---|
| a new client, person, project, area, unit or seat | `onboard.py add client "Name"` (agency projects: `add project "Name" --in <client-slug>`) |
| another mode | `onboard.py add-mode organisation --quote "..."` (nothing moves; a decision is recorded) |
| a fresh clone lacks `operator/profile.json` | `onboard.py restore` |
| check the brain answers from files alone | `python3 scripts/brain/probe.py --static` |

`add` writes the index row first, creates only, and prints `skipped (exists)`
for anything already there.

## 8. The one-time seed push

The instance's ship-gate refuses the first push, because a new instance has no
verifier keys. After reading `git log`, the operator runs once:

```
git push --no-verify -u origin main
```

Tess never runs `--no-verify` and never pushes brain content to the public
framework repository.
