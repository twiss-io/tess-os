# The Tess second brain

A Tess OS instance keeps the operator's working memory in plain files under
`brain/`. Every agent runtime that opens the folder (Claude Code, Codex CLI,
Gemini CLI, and other tools that read `AGENTS.md`) reads the same brain, so
what one session learns, the next session knows.

This page covers what the brain is and how it is kept honest. Related pages:
[ONBOARDING.md](ONBOARDING.md) (first run), [MODES.md](MODES.md) (personal,
agency, organisation), [COMPONENTS.md](COMPONENTS.md) (what each part of Tess OS
does in each runtime). The learning loop (journal, decisions, preferences) is
documented in `LEARNING.md` and the runtime matrix in `RUNTIMES.md`, both in
this folder when the learning tools are installed.

## What it is

- **Files, not a database.** Markdown with flat YAML front matter, plus one
  config file, `brain/brain.json`. It opens as an Obsidian vault and survives
  leaving Tess: delete `scripts/`, `.claude/`, `.agents/`, `.codex/` and the
  rendered entry files, and a plain Markdown brain remains.
- **One brain root.** Everything the operator owns lives under `brain/`, plus
  project state cards in `memory/projects/`. Both paths are tracked by git and
  pass the instance's pre-commit gate. Framework paths (`conductor/`, `agents/`,
  `.claude/`, ...) belong to Tess OS and are refreshed by updates; `brain/` is
  never touched by an update (checked by `tests/test_brain_upgrade_safety.py`).
- **Runtime memories are caches.** New installs turn Claude Code's auto memory
  off at project level (`"autoMemoryEnabled": false` in `.claude/settings.json`),
  so there is one brain, not two. Codex memories and Gemini Auto Memory are off
  by default.
- **Routing, not recall.** A zero-context agent reaches every fact the same
  way: the BOOT block in `CLAUDE.md` / `AGENTS.md`, then `brain/START-HERE.md`
  (the map), then the entity's `AGENTS.md` (which starts with `# START HERE`),
  then the records it links to. `scripts/brain/probe.py --static` checks, on a
  fresh clone, that this route answers five basic questions.

## Always-on layer, whatever the mode

| Path | What |
|---|---|
| `brain/brain.json` | config and onboarding state (schema v1) |
| `brain/START-HERE.md` | the map: modes, operator, principals, where things go, every entity |
| `brain/decisions/` | `D-YYYYMMDD-HHMM-<slug>.md`, each with the decider's exact words |
| `brain/profile/`, `brain/profile.md` | preferences and corrections, and their generated summary |
| `brain/loops/`, `brain/open-loops.md` | open loops and their generated summary |
| `brain/facts/` | facts not owned by a single entity |
| `brain/journal/YYYY/MM/DD/` | one file per conversation session |
| `brain/learned.md` | generated changelog of what the brain learned |
| `brain/kb/{raw,research,wiki}/` | research and knowledge; `raw/` is for humans only |
| `brain/inbox/`, `brain/reviews/`, `brain/skills-drafts/` | candidates awaiting verification or review |
| `brain/probe.json` | the fresh-clone probe questions |
| `brain/.private/` | local only, never committed (it carries its own `.gitignore` of `*`) |

Each mode then adds its own entities (`brain/life/`, `brain/agency/` +
`brain/clients/<slug>/`, or `brain/org/`); see [MODES.md](MODES.md).

## What "saved" means

A piece of work is saved only when all four are true:

1. it is in its owning folder under `brain/` (or `memory/projects/`);
2. it is linked from that entity's START HERE, or from a generated index;
3. it is committed;
4. it is pushed to the instance's private remote.

When the learning tools are installed, `python3 scripts/brain/tessbrain.py status`
checks all four and names what is missing; the `brain-save` skill runs it
before an agent says "saved".

## Principals and quotes

`brain/brain.json` lists the **principals**: the operator (scope `**`) and
anyone else whose words count as decisions, each with a scope relative to
`brain/` (for example `clients/northwind-studio/**`). Everyone else's words are
recorded as facts about what they said, never as decisions.

Every durable record carries a verbatim quote that a script can find in the
source conversation. Onboarding's own first decision is written as
`pending-verification` until its quote is matched against the operator's real
turn. Agents never invent a quote, and never record their own suggestion, a
question or a hypothetical as someone's decision.

## Never in the brain

Secrets and credentials, government ID numbers, pay, health or HR records, and
contract files. Write a pointer instead ("the signed SOW is in the shared
drive, folder X, owner Y"). Agency client folders have an `admin/README.md`
for exactly these pointers; everything else in `admin/` is gitignored.

Anything an agent reads, including `brain/.private/`, is sent to that
runtime's model provider. Onboarding says so.

## How reliable each part is, per runtime

Labels used across these docs:

| Label | Meaning |
|---|---|
| M | mechanical: runs whether or not the model cooperates |
| M/T | mechanical after the runtime's one-time trust step |
| M/S | mechanical, by sweeping the runtime's own transcript files |
| I | instruction-dependent: the model is told to, and may forget |
| U | unverified |

| Part | Claude Code | Codex CLI | Gemini CLI | Other AGENTS.md tools |
|---|---|---|---|---|
| BOOT block loads | M | M | M/T (GEMINI.md imports AGENTS.md) | U |
| Onboarding starts on "hi" | M/T hook line + I | I (BOOT + skill description) | I | I |
| Brain files tracked and gate-clean | M | M | M | M |
| Update never touches `brain/` | M | M | M | M |
| Fresh-clone probe | M (script) | M (script) | M (script) | M (script) |

Conversation capture, decision capture and verification are covered in
`LEARNING.md` / `RUNTIMES.md` when the learning tools are installed.

## Known gaps in v0.2.0

- **Seed push.** The first push of a new instance is refused by the ship-gate
  (`COVERING_APPROVAL_MISSING`: instances have no verifier keys). The operator
  runs `git push --no-verify -u origin main` once, after reading `git log`.
  Tess never runs `--no-verify`. Later brain pushes pass, because brain paths
  are outside the gate's approval requirement.
- **Placement rows.** The file-placement tables in `CLAUDE.md` and `AGENTS.md`
  still say `kb/` and `clients/<Client>/kb/`. The BOOT block overrides them
  (`brain/kb/`, `brain/clients/<slug>/kb/`), because the old paths are refused
  at commit. The doctrine fix is v0.2.1.
- **RULE ZERO notice.** When the conductor runs a brain tool in the main Claude
  Code session, the dispatch guard prints a notice to the operator. The model
  never sees it and it never blocks.
- **Personal mode** still carries the crew doctrine and the Telegram text in
  `CLAUDE.md` until the mode-aware render lands (v0.2.1).
- **Do not run `tessctl update`** until the v0.2.0 lock pin is released: an
  older pin can downgrade `settings-core.json` and drop the brain hook lines.
  The brain data is safe either way.
- **Brain tool code is not updated over the air yet.** `scripts/brain/**` and
  the `brain-*` skills are not covered by `tess.lock`; v0.2.1 moves them under
  `.tess/core/`.
