# Tess OS components: what runs where, how reliably, and what v0.2 does about it

Every instruction file, doctrine page, hook, command, skill, agent, workflow,
config file, engine subcommand, installer feature, CI gate and doc in Tess OS,
assessed for the v0.2 rework: which runtimes it applies to, whether it runs by
mechanism or only by instruction, whether it was shown to work, whether it is
essential, and what v0.2 does with it.

- **Baseline.** The verdicts describe the v0.1.x tree that installs shipped
  before v0.2.0, as probed on 2026-09-24 with Claude Code 2.1.281, Codex CLI
  0.145.0 and Gemini CLI 0.61.0 in scratch installs. The "v0.2 action" column
  is the plan; rows marked `add` are components that did not exist yet.
- **Where v0.2.0 lands.** v0.2.0 ships the parts of the plan that make a fresh
  install a working second brain: the BOOT block in `CLAUDE.md` / `AGENTS.md`,
  the `brain/` root, self-starting onboarding and the `brain-onboard` skill
  ([ONBOARDING.md](ONBOARDING.md)), the modes ([MODES.md](MODES.md)), the
  upgrade-safety and fresh-clone checks ([SECOND_BRAIN.md](SECOND_BRAIN.md)),
  and, when installed, the learning loop (`LEARNING.md`, `RUNTIMES.md`). Rows
  whose action is `rework` or `defer` and are not covered there are v0.2.1+.
- **v0.2.0 onboarding, as built.** The onboarding CLI is mechanical (M):
  it refuses an answer without a quote, an answer for a step not reached
  yet, and `apply` before every step is answered. Running the interview is
  instruction-dependent (I): whether the model asks one question per turn,
  records the operator's words verbatim and reports honestly depends on the
  model (a small model was seen making malformed calls). In Codex, asking
  the first question when the first message is a task was 2 of 3 runs (I).
  `brain/START-HERE.md` has a 150-line / 12 KiB budget: `onboard.py add`
  warns when it is over, and `tessbrain.py lint` (learning loop) is the
  enforcement point.
- **Evidence.** The public table keeps the verdicts only. The probe notes
  behind each row stay with the maintainers. A runtime cell is a short verdict
  (what that runtime does with the component), never a quote.
- **One row per component.** Rows that several breakdowns listed under
  different names or the same path are merged, so the counts below are
  lower than the raw assessment count.

**Runtime columns:** CC = Claude Code, CX = Codex CLI, GM = Gemini CLI, AM =
other tools that read only `AGENTS.md` (from their docs; not probed). A cell
says in a few words what the runtime does with the component; `n/a` means it
does not apply there.

**Mechanism:** `mechanical` runs without the model choosing to; `instruction`
depends on the model following text (it may forget); `mixed`; `ci`; `none`.

**Reliability:** `proven` (a probe or test run showed it working), `likely`
(tests exist in CI, not re-run), `unproven` (instruction only, or never
exercised), `broken` (shown not to work as documented).

**Essential:** `essential` (a second brain does not work without it),
`useful`, `optional`, `cut` (remove).

**Status:** `current`, `outdated`, `wrong` (says or does something false),
`missing`. **v0.2 action:** `keep`, `rework`, `add`, `cut`, `defer`.

**Planned for:** the release the v0.2 plan puts the work in: `v0.2.0`,
`v0.2.0 + v0.2.1` (a first part now, the rest later), `v0.2.1+`, or `-`
(nothing to do). It is the plan, not a record of what merged: check
`CHANGELOG.md` for what a release actually contains.

## Summary

314 components after removing duplicates.

### Essential x reliability

| ess \ rel | proven | likely | unproven | broken | total |
|---|---|---|---|---|---|
| essential | 36 | 4 | 22 | 19 | 81 |
| useful | 57 | 27 | 28 | 9 | 121 |
| optional | 32 | 24 | 36 | 10 | 102 |
| cut | 5 | 1 | 2 | 2 | 10 |
| total | 130 | 56 | 88 | 40 | 314 |

### Status x v0.2 action

| status \ action | keep | rework | add | cut | defer | total |
|---|---|---|---|---|---|---|
| current | 105 | 10 | 0 | 5 | 27 | 147 |
| outdated | 4 | 74 | 0 | 16 | 2 | 96 |
| wrong | 0 | 42 | 0 | 4 | 0 | 46 |
| missing | 0 | 0 | 20 | 0 | 5 | 25 |
| total | 109 | 126 | 20 | 25 | 34 | 314 |

### Essential components that were broken, wrong, unproven or missing

| # | Component | Kind | Reliability | Status | v0.2 action | Planned for |
|---|---|---|---|---|---|---|
| 1 | Client brief template (clients/_template/CLAUDE.md) | Instruction files (auto-loaded entry points and injected zones) | broken | outdated | rework | v0.2.0 + v0.2.1 |
| 2 | Fragment: directory.md (directory tree + KB framework) | Instruction files (auto-loaded entry points and injected zones) | broken | wrong | rework | v0.2.0 |
| 3 | Fragment: session-memory.md (shared memory pointer) | Instruction files (auto-loaded entry points and injected zones) | broken | outdated | rework | v0.2.0 |
| 4 | Fragment: hard-floor.md (Doctrine Gates + Verification/Retry + Rule 18 floor) | Instruction files (auto-loaded entry points and injected zones) | unproven | current | rework | v0.2.0 + v0.2.1 |
| 5 | MISSING: @AGENTS.md import in CLAUDE.md (shared core for Claude) | Instruction files (auto-loaded entry points and injected zones) | unproven | missing | add | v0.2.0 + v0.2.1 |
| 6 | MISSING: First-run onboarding (in-session, every runtime) | Instruction files (auto-loaded entry points and injected zones) | unproven | missing | add | v0.2.0 |
| 7 | MISSING: Per-entity START HERE index template | Instruction files (auto-loaded entry points and injected zones) | unproven | missing | add | v0.2.0 |
| 8 | MISSING: Worker override for dispatched subagents | Instruction files (auto-loaded entry points and injected zones) | unproven | missing | add | v0.2.1+ |
| 9 | CLAUDE.md (entry doctrine) | Instruction files (auto-loaded entry points and injected zones) | proven | wrong | rework | v0.2.0 |
| 10 | conductor/guardrails.md (18 rules; security tier) | Doctrine (conductor/, playbooks, KB and memory conventions) | broken | wrong | rework | v0.2.0 + v0.2.1 |
| 11 | conductor/verification-routing.md (security tier) | Doctrine (conductor/, playbooks, KB and memory conventions) | broken | wrong | rework | v0.2.0 + v0.2.1 |
| 12 | kb/ knowledge-base scaffold | Doctrine (conductor/, playbooks, KB and memory conventions) | broken | outdated | rework | v0.2.0 |
| 13 | conductor/channel-guardrails.md (security tier) | Doctrine (conductor/, playbooks, KB and memory conventions) | unproven | outdated | rework | v0.2.0 + v0.2.1 |
| 14 | conductor/daily-operating-behavior.md | Doctrine (conductor/, playbooks, KB and memory conventions) | unproven | outdated | rework | v0.2.0 + v0.2.1 |
| 15 | conductor/memory-model.md | Doctrine (conductor/, playbooks, KB and memory conventions) | unproven | outdated | rework | v0.2.0 + v0.2.1 |
| 16 | Decisions register | Doctrine (conductor/, playbooks, KB and memory conventions) | unproven | missing | add | v0.2.0 |
| 17 | Internal KB skeleton (kb/wiki index/log, raw/, lint/) | Doctrine (conductor/, playbooks, KB and memory conventions) | unproven | outdated | rework | v0.2.0 |
| 18 | MISSING: Agency mode pack (clients as entities) | Doctrine (conductor/, playbooks, KB and memory conventions) | unproven | missing | add | v0.2.0 |
| 19 | MISSING: Learning-loop doctrine (always smarter, never wrong) | Doctrine (conductor/, playbooks, KB and memory conventions) | unproven | missing | add | v0.2.0 |
| 20 | MISSING: Organisation mode pack | Doctrine (conductor/, playbooks, KB and memory conventions) | unproven | missing | add | v0.2.0 |
| 21 | MISSING: Personal mode pack | Doctrine (conductor/, playbooks, KB and memory conventions) | unproven | missing | add | v0.2.0 |
| 22 | MISSING: Save contract / File Placement Contract | Doctrine (conductor/, playbooks, KB and memory conventions) | unproven | missing | add | v0.2.0 |
| 23 | Conversation capture pipeline (every conversation noted) | Hooks | unproven | missing | add | v0.2.0 |
| 24 | MISSING: SessionStart unsaved-work warning | Hooks | unproven | missing | add | v0.2.0 |
| 25 | /close | Commands | broken | wrong | rework | v0.2.0 + v0.2.1 |
| 26 | /wake | Commands | broken | wrong | rework | v0.2.0 + v0.2.1 |
| 27 | /feedback | Commands | unproven | outdated | rework | v0.2.0 + v0.2.1 |
| 28 | .agents/skills/tess-* (commands as cross-runtime skills) | Skills | unproven | missing | add | v0.2.0 |
| 29 | Mandatory verifiers (Reid, Quinn, Cyra, Verity, Maialen, Lysandra) | Agents (subagent definitions and roster) | broken | wrong | rework | v0.2.1+ |
| 30 | .tess/tess.lock framework pin | Config and state files | broken | wrong | rework | v0.2.0 + v0.2.1 |
| 31 | Release public key (.tess/keys/twiss-release-key.asc) | Config and state files | broken | wrong | rework | v0.2.1+ |
| 32 | MISSING: GEMINI.md entry / .gemini/settings.json context.fileName | Config and state files | unproven | missing | add | v0.2.0 |
| 33 | Instance .gitignore (template copy of the framework's) | Config and state files | proven | wrong | rework | v0.2.0 |
| 34 | tessctl render | Engine (tessctl subcommands, drivers, render targets, tools) | broken | wrong | rework | v0.2.0 |
| 35 | tessctl rollback | Engine (tessctl subcommands, drivers, render targets, tools) | broken | wrong | rework | v0.2.0 |
| 36 | tessctl self-update | Engine (tessctl subcommands, drivers, render targets, tools) | broken | wrong | rework | v0.2.0 + v0.2.1 |
| 37 | tessctl update (signed OTA) | Engine (tessctl subcommands, drivers, render targets, tools) | broken | wrong | rework | v0.2.0 + v0.2.1 |
| 38 | MISSING: Memory index budget guard | Engine (tessctl subcommands, drivers, render targets, tools) | unproven | missing | add | v0.2.0 |
| 39 | Mode scaffolds (personal / agency / organisation + presets) | Engine (tessctl subcommands, drivers, render targets, tools) | unproven | missing | add | v0.2.0 |
| 40 | tessctl approve | Engine (tessctl subcommands, drivers, render targets, tools) | proven | wrong | rework | v0.2.0 |
| 41 | tessctl memory adopt | Engine (tessctl subcommands, drivers, render targets, tools) | proven | wrong | rework | v0.2.1+ |
| 42 | Agency mode scaffold (clients/_template) | Installer (create-tess) and scaffolds | broken | outdated | rework | v0.2.0 |
| 43 | Python/PyYAML preflight (ensurePython3) | Installer (create-tess) and scaffolds | broken | wrong | rework | v0.2.1+ |
| 44 | writeProfile (operator/profile.json) | Installer (create-tess) and scaffolds | broken | wrong | rework | v0.2.0 |
| 45 | .tess/state/memory/ shared memory store | Other repo content | broken | outdated | rework | v0.2.1+ |

## 1. Instruction files (auto-loaded entry points and injected zones) (28)

Essential 15 / useful 7 / optional 5 / cut 1. Reliability proven 7 / likely 4 / unproven 12 / broken 5.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action | Planned for |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Client brief template (clients/_template/CLAUDE.md) | `clients/_template/CLAUDE.md (source .tess/core/templates/client/_template/CLAUDE.md)` | Loaded lazily when Claude reads files in that client folder | Never read | Never read | Never read | instruction | broken | essential | outdated | rework | v0.2.0 + v0.2.1 |
| Fragment: directory.md (directory tree + KB framework) | `.tess/core/templates/claude-md/directory.md` | Rendered into CLAUDE.md | n/a | n/a | n/a | instruction | broken | essential | wrong | rework | v0.2.0 |
| Fragment: session-memory.md (shared memory pointer) | `.tess/core/templates/agents-md/session-memory.md` | n/a | In AGENTS.md | n/a | In AGENTS.md | instruction | broken | essential | outdated | rework | v0.2.0 |
| Fragment: hard-floor.md (Doctrine Gates + Verification/Retry + Rule 18 floor) | `.tess/core/templates/claude-md/hard-floor.md` | Rendered into CLAUDE.md | Hard-floor portion delivered separately via worker-hard-floor.md in AGENTS.md | n/a | n/a | instruction | unproven | essential | current | rework | v0.2.0 + v0.2.1 |
| MISSING: @AGENTS.md import in CLAUDE.md (shared core for Claude) | (new) CLAUDE.md first line | import AGENTS.md with '@AGENTS.md' | n/a | n/a | n/a | mechanical | unproven | essential | missing | add | v0.2.0 + v0.2.1 |
| MISSING: First-run onboarding (in-session, every runtime) | (new) shared core in AGENTS.md + onboarding skill/command | Instruction in shared core | AGENTS.md instruction + SessionStart hook in .codex/hooks.json | Loaded via context.fileName + SessionStart hook | AGENTS.md instruction only | mixed | unproven | essential | missing | add | v0.2.0 |
| MISSING: Per-entity START HERE index template | (new) top section of every entity CLAUDE.md/AGENTS.md | Lazy-loaded with entity CLAUDE.md | Per-folder AGENTS.md | Via context.fileName | Per-folder AGENTS.md | instruction | unproven | essential | missing | add | v0.2.0 |
| MISSING: Worker override for dispatched subagents | (new) block in dispatch defs or omitClaudeMd:true | custom subagents load CLAUDE.md unless omitClaudeMd is set | n/a | n/a | n/a | mechanical | unproven | essential | missing | add | v0.2.1+ |
| CLAUDE.md (rendered conductor entry point) | `CLAUDE.md` | Auto-loaded at session start | n/a | n/a | n/a | mixed | likely | essential | outdated | rework | v0.2.0 |
| AGENTS.md (rendered worker profile) | `AGENTS.md` | Not read by default because CLAUDE.md exists | Auto-loaded git-root→cwd, 32 KiB default cap | NOT loaded | Read natively per AGENTS.md convention | mixed | proven | essential | outdated | rework | v0.2.0 |
| AGENTS.md (worker digest) | `AGENTS.md (render_agents_md, .tess/core/templates/agents-md/)` | Not read while CLAUDE.md exists | Loaded natively | Only if .gemini/settings.json context.fileName includes AGENTS.md — not shipped | Loaded natively | instruction | proven | essential | outdated | rework | v0.2.0 |
| AGENTS.md.tpl (worker template) | `.tess/core/templates/agents-md/AGENTS.md.tpl` | n/a | Rendered by `tessctl render --target codex` | n/a | Rendered by generic target | mechanical | proven | essential | outdated | rework | v0.2.0 |
| CLAUDE.md (entry doctrine) | `CLAUDE.md (rendered from .tess/core/templates/claude-md/*)` | Auto-loaded as project instructions | Not read | Not read | n/a | instruction | proven | essential | wrong | rework | v0.2.0 |
| CLAUDE.md.tpl (entry-point template) | `.tess/core/templates/CLAUDE.md.tpl` | Rendered to CLAUDE.md by `tessctl render` | n/a | n/a | n/a | mechanical | proven | essential | outdated | rework | v0.2.0 |
| Fragment: worker-hard-floor.md | `.tess/core/templates/agents-md/worker-hard-floor.md` | n/a | In AGENTS.md | n/a until Gemini reads AGENTS.md | In AGENTS.md | instruction | proven | essential | current | keep | v0.2.0 + v0.2.1 |
| Fragment: rule-zero.md (Always dispatch, never execute solo) | `.tess/core/templates/claude-md/rule-zero.md` | Rendered to CLAUDE.md top | n/a | n/a | n/a | mixed | unproven | useful | outdated | rework | v0.2.1+ |
| Fragment: system-laws.md (7 System Laws table) | `.tess/core/templates/claude-md/system-laws.md` | Rendered into CLAUDE.md | n/a | n/a | n/a | instruction | unproven | useful | outdated | rework | v0.2.0 + v0.2.1 |
| operator/user-profile.md (profile stub) | `operator/user-profile.md` | inject:false by default → renders empty | n/a | n/a | n/a | instruction | unproven | useful | outdated | rework | v0.2.0 |
| Fragment: commands.md (command table) | `.tess/core/templates/claude-md/commands.md` | Rendered into CLAUDE.md | n/a | n/a | n/a | instruction | likely | useful | outdated | rework | v0.2.0 + v0.2.1 |
| Fragment: gate-compliance.md (ship-gate facts) | `.tess/core/templates/agents-md/gate-compliance.md` | n/a | In AGENTS.md | n/a | In AGENTS.md | mixed | likely | useful | outdated | rework | v0.2.0 |
| Fragment: shared-tasks.md (cross-harness task board) | `.tess/core/templates/agents-md/shared-tasks.md` | n/a | In AGENTS.md | n/a | In AGENTS.md, but hardcodes --harness codex / --lane codex for every reader | mixed | likely | useful | outdated | rework | v0.2.0 |
| operator/identity-stub.md | `operator/identity-stub.md` | Injected into CLAUDE.md | n/a | n/a | n/a | mechanical | proven | useful | current | keep | v0.2.0 |
| Fragment: harness-note.md (command mirrors note) | `.tess/core/templates/agents-md/harness-note.md` | n/a | In AGENTS.md | n/a | In AGENTS.md | instruction | broken | optional | wrong | rework | v0.2.0 |
| Fragment: orchestrators.md (Outcome Orchestrator Layer) | `.tess/core/templates/claude-md/orchestrators.md` | Rendered into CLAUDE.md | n/a | n/a | n/a | instruction | broken | optional | wrong | rework | v0.2.0 + v0.2.1 |
| operator/build-facts-stub.md | `operator/build-facts-stub.md` | n/a | inject:false → empty in AGENTS.md | n/a | inject:false | instruction | unproven | optional | current | keep | v0.2.0 |
| operator/org-channels.md (channel map stub) | `operator/org-channels.md` | inject:false → empty | n/a | n/a | n/a | instruction | unproven | optional | outdated | rework | v0.2.1+ |
| Pathway personas (5: chief-of-staff, co-founder, strategist, guide, operator) | `.tess/core/personas/*.md` | Rendered into conductor/personality.md, which CLAUDE.md only links | n/a | n/a | n/a | instruction | unproven | optional | outdated | rework | v0.2.1+ |
| starter/ third-party kit instructions (starter/CLAUDE.md, starter/global-claude-md/CLAUDE.md) | `starter/` | starter/CLAUDE.md loads when Claude reads files under starter/ | n/a | n/a | n/a | instruction | unproven | cut | outdated | cut | v0.2.0 |

## 2. Doctrine (conductor/, playbooks, KB and memory conventions) (57)

Essential 14 / useful 21 / optional 21 / cut 1. Reliability proven 1 / likely 3 / unproven 47 / broken 6.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action | Planned for |
|---|---|---|---|---|---|---|---|---|---|---|---|
| conductor/guardrails.md (18 rules; security tier) | `conductor/guardrails.md` | Not auto-loaded | Linked from AGENTS.md | n/a | Linked from AGENTS.md | mixed | broken | essential | wrong | rework | v0.2.0 + v0.2.1 |
| conductor/verification-routing.md (security tier) | `conductor/verification-routing.md` | Not auto-loaded | Linked from AGENTS.md ship-gate | n/a | Linked from AGENTS.md | mixed | broken | essential | wrong | rework | v0.2.0 + v0.2.1 |
| kb/ knowledge-base scaffold | `kb/{raw,wiki/{concepts,missions,people,synthesis},lint}, kb/wiki/{index,log}.md` | Read/write via tools | Same | Same | Same | instruction | broken | essential | outdated | rework | v0.2.0 |
| conductor/channel-guardrails.md (security tier) | `conductor/channel-guardrails.md` | Not auto-loaded | n/a | n/a | n/a | instruction | unproven | essential | outdated | rework | v0.2.0 + v0.2.1 |
| conductor/daily-operating-behavior.md | `conductor/daily-operating-behavior.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | essential | outdated | rework | v0.2.0 + v0.2.1 |
| conductor/memory-model.md | `conductor/memory-model.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | essential | outdated | rework | v0.2.0 + v0.2.1 |
| Decisions register | `(missing)` | decide skill + capture hook | skill + AGENTS.md rule | skill | AGENTS.md rule | mixed | unproven | essential | missing | add | v0.2.0 |
| Internal KB skeleton (kb/wiki index/log, raw/, lint/) | `kb/` | Read on demand | Not referenced by AGENTS.md | n/a | Not referenced | instruction | unproven | essential | outdated | rework | v0.2.0 |
| MISSING: Agency mode pack (clients as entities) | (new) mode pack: agency | Subdirectory CLAUDE.md lazy load | Per-folder AGENTS.md | GEMINI.md/AGENTS.md per folder via context.fileName | Per-folder AGENTS.md | instruction | unproven | essential | missing | add | v0.2.0 |
| MISSING: Learning-loop doctrine (always smarter, never wrong) | (new) conductor/learning-loop.md + shared core summary | Instruction + Stop hook nudge | Instruction + Stop hook | Instruction + AfterAgent hook | Instruction only | mixed | unproven | essential | missing | add | v0.2.0 |
| MISSING: Organisation mode pack | (new) mode pack: organisation | Rendered tree + per-entity START HERE | Per-folder AGENTS.md | Via context.fileName | Per-folder AGENTS.md | instruction | unproven | essential | missing | add | v0.2.0 |
| MISSING: Personal mode pack | (new) mode pack: personal | Rendered tree + START HERE | Same via AGENTS.md | Same via context.fileName | Same via AGENTS.md | instruction | unproven | essential | missing | add | v0.2.0 |
| MISSING: Save contract / File Placement Contract | (new) shared core section | Instruction | Instruction | Instruction | Instruction | instruction | unproven | essential | missing | add | v0.2.0 |
| memory/ open-projects registry (README, registry.md, projects/EXAMPLE.md) | `memory/` | Not referenced by CLAUDE.md | Not referenced by AGENTS.md | n/a | Not referenced | mixed | likely | essential | outdated | rework | v0.2.1+ |
| Client KB skeleton (kb/wiki index+log, lint-log, research/, branding/DESIGN.md) | `clients/_template/kb/**, clients/_template/branding/DESIGN.md` | Files read on demand | Files read on demand | Files read on demand | Files read on demand | instruction | broken | useful | outdated | rework | v0.2.0 + v0.2.1 |
| conductor/hook-testing-protocol.md | `conductor/hook-testing-protocol.md` | Not auto-loaded | n/a | n/a | n/a | instruction | broken | useful | outdated | rework | v0.2.0 + v0.2.1 |
| agents/README.md (roster overview) | `agents/README.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | useful | current | keep | - |
| conductor/commands.md (command catalogue) | `conductor/commands.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | outdated | rework | v0.2.0 + v0.2.1 |
| conductor/dispatch-brief.md (security tier) | `conductor/dispatch-brief.md` | Not auto-loaded | Not referenced | n/a | Not referenced | mixed | unproven | useful | outdated | rework | v0.2.0 + v0.2.1 |
| conductor/doctrine.md (dependency gates, Simple Task Path) | `conductor/doctrine.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | outdated | rework | v0.2.0 + v0.2.1 |
| conductor/identity.md (rendered) | `conductor/identity.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | current | keep | v0.2.0 + v0.2.1 |
| conductor/mission-states.md | `conductor/mission-states.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | outdated | rework | v0.2.0 + v0.2.1 |
| conductor/output-framework.md (System Law) | `conductor/output-framework.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | current | keep | v0.2.0 + v0.2.1 |
| conductor/personality.md (rendered + active pathway) | `conductor/personality.md` | Not auto-loaded | n/a | n/a | n/a | instruction | unproven | useful | outdated | rework | v0.2.0 + v0.2.1 |
| conductor/README.md (doctrine index) | `conductor/README.md` | Not auto-loaded | Not referenced by AGENTS.md | n/a | Not referenced | instruction | unproven | useful | outdated | rework | v0.2.0 + v0.2.1 |
| conductor/review-output-standards.md (System Law) | `conductor/review-output-standards.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | current | keep | v0.2.0 + v0.2.1 |
| conductor/subagent-failure-protocol.md | `conductor/subagent-failure-protocol.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | current | rework | v0.2.0 + v0.2.1 |
| conductor/user-profile.md | `conductor/user-profile.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | wrong | rework | v0.2.0 |
| conductor/verdict-signing.md | `conductor/verdict-signing.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | wrong | rework | v0.2.0 + v0.2.1 |
| Eva hiring framework + portfolio (agents/eva/*, 9 files) | `agents/eva/` | Read by Eva subagent on demand | n/a | n/a | n/a | instruction | unproven | useful | current | keep | - |
| MISSING: Extra presets (candidates; research pending) | (new) presets | Preset overlays on a base mode | Same | Same | Same | instruction | unproven | useful | missing | defer | v0.2.0 + v0.2.1 |
| playbooks/founder-decision-memo.md | `conductor/playbooks/founder-decision-memo.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | useful | current | keep | v0.2.0 + v0.2.1 |
| conductor/vault.md | `conductor/vault.md` | Not auto-loaded | Not referenced | n/a | Not referenced | mixed | likely | useful | outdated | rework | v0.2.0 + v0.2.1 |
| memory/ open-projects registry (L1) | `memory/README.md, memory/registry.md, memory/projects/*.md` | Read on demand | Read on demand | Read on demand | Read on demand | mixed | likely | useful | current | keep | - |
| Conductor pathways (5 personas) | `.tess/core/personas/{chief-of-staff,co-founder,strategist,guide,operator}.md` | Via rendered CLAUDE.md/personality.md | Not in AGENTS.md worker profile | n/a | n/a | mixed | proven | useful | current | keep | - |
| conductor/orchestra-model.md | `conductor/orchestra-model.md` | Not auto-loaded | Not referenced | n/a | Not referenced | mixed | broken | optional | wrong | rework | v0.2.0 + v0.2.1 |
| client-experience-orchestrator.md (doctrine) | `conductor/outcome-orchestrators/client-experience-orchestrator.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer | v0.2.0 + v0.2.1 |
| conductor/agent-lifecycle.md (System Law) | `conductor/agent-lifecycle.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | current | keep | v0.2.0 + v0.2.1 |
| conductor/cross-guild-coordination.md (System Law) | `conductor/cross-guild-coordination.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | current | defer | v0.2.0 + v0.2.1 |
| conductor/founders-office.md (System Law) | `conductor/founders-office.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | outdated | rework | v0.2.0 + v0.2.1 |
| conductor/mission-control.md | `conductor/mission-control.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | outdated | cut | v0.2.0 + v0.2.1 |
| conductor/outcome-orchestrators/integration.md (System Law) | `conductor/outcome-orchestrators/integration.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | current | defer | v0.2.0 + v0.2.1 |
| conductor/outcome-orchestrators/README.md | `conductor/outcome-orchestrators/README.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | current | defer | v0.2.0 + v0.2.1 |
| conductor/playbooks/README.md | `conductor/playbooks/README.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | outdated | keep | v0.2.0 + v0.2.1 |
| conductor/soul.md | `conductor/soul.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | current | keep | v0.2.0 + v0.2.1 |
| founders-office-orchestrator.md (doctrine) | `conductor/outcome-orchestrators/founders-office-orchestrator.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer | v0.2.0 + v0.2.1 |
| Guild/governance docs (20 *-guild.md / *-governance.md / coding-team.md / intelligence-staffing.md) | `agents/*.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer | v0.2.1+ |
| operational-reliability-orchestrator.md (doctrine) | `conductor/outcome-orchestrators/operational-reliability-orchestrator.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer | v0.2.0 + v0.2.1 |
| playbooks/event-launch-orchestration.md | `conductor/playbooks/event-launch-orchestration.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer | v0.2.0 + v0.2.1 |
| playbooks/investor-fundraising-prep.md | `conductor/playbooks/investor-fundraising-prep.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer | v0.2.0 + v0.2.1 |
| playbooks/product-build-mission.md | `conductor/playbooks/product-build-mission.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer | v0.2.0 + v0.2.1 |
| playbooks/revenue-diagnosis.md | `conductor/playbooks/revenue-diagnosis.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer | v0.2.0 + v0.2.1 |
| product-delivery-orchestrator.md (doctrine) | `conductor/outcome-orchestrators/product-delivery-orchestrator.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer | v0.2.0 + v0.2.1 |
| revenue-orchestrator.md (doctrine) | `conductor/outcome-orchestrators/revenue-orchestrator.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer | v0.2.0 + v0.2.1 |
| Rule Zero dispatch discipline (cross-cutting) | `CLAUDE.md banner, guardrails Rule 1/1a, dispatch-guard.sh` | Instruction | Excluded by design from AGENTS.md | n/a | Excluded | instruction | unproven | optional | outdated | rework | v0.2.0 + v0.2.1 |
| strategic-growth-orchestrator.md (doctrine) | `conductor/outcome-orchestrators/strategic-growth-orchestrator.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | outdated | defer | v0.2.0 + v0.2.1 |
| playbooks/l99-merge-discipline.md | `conductor/playbooks/l99-merge-discipline.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | cut | wrong | cut | v0.2.0 + v0.2.1 |

## 3. Hooks (10)

Essential 2 / useful 5 / optional 0 / cut 3. Reliability proven 4 / likely 0 / unproven 4 / broken 2.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action | Planned for |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Conversation capture pipeline (every conversation noted) | `(missing; the reference instance keeps conversation logs by hand)` | Stop/SessionEnd/PreCompact provide transcript_path | SessionEnd/Stop hooks | SessionEnd/AfterAgent hooks | Instruction only | mixed | unproven | essential | missing | add | v0.2.0 |
| MISSING: SessionStart unsaved-work warning | (new) SessionStart hook for Claude/.codex/hooks.json/.gemini/settings.json | SessionStart stdout added as context | SessionStart stdout added as developer context | SessionStart supports context injection | n/a | mechanical | unproven | essential | missing | add | v0.2.0 |
| anti-fabrication-guard.sh | `.claude/hooks/anti-fabrication-guard.sh` | Fires only with a dispatch lock | n/a | n/a | n/a | mechanical | broken | useful | wrong | rework | v0.2.0 + v0.2.1 |
| Codex hooks (.codex/hooks.json) | `(absent)` | n/a | Codex loads <repo>/.codex/hooks.json or [hooks] in config.toml | n/a | n/a | none | unproven | useful | missing | add | v0.2.0 |
| Output-path / placement guard | `(missing; the reference instance has a local output-path guard)` | PreToolUse Write\\|Edit | PreToolUse apply_patch | BeforeTool | n/a | mechanical | unproven | useful | missing | defer | v0.2.1+ |
| utc-local-context.sh | `.claude/hooks/utc-local-context.sh` | UserPromptSubmit, plain stdout reaches the model | n/a | n/a | n/a | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| vault-dispatch-scan.py | `.claude/hooks/vault-dispatch-scan.py (NOT in .tess/core/hooks, NOT in tess.lock)` | Blocks | n/a | n/a | n/a | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| dispatch-guard.sh | `.claude/hooks/dispatch-guard.sh` | Fires on every main-session Bash/Edit/Write | n/a | n/a | n/a | mechanical | broken | cut | wrong | cut | v0.2.0 + v0.2.1 |
| task-lock-clear.sh | `.claude/hooks/task-lock-clear.sh` | Fires | n/a | n/a | n/a | mechanical | proven | cut | outdated | cut | v0.2.1+ |
| task-lock-set.sh | `.claude/hooks/task-lock-set.sh` | Fires | n/a | n/a | n/a | mechanical | proven | cut | outdated | cut | v0.2.1+ |

## 4. Commands (30)

Essential 3 / useful 8 / optional 17 / cut 2. Reliability proven 0 / likely 19 / unproven 2 / broken 9.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action | Planned for |
|---|---|---|---|---|---|---|---|---|---|---|---|
| /close | `.claude/commands/close.md` | Registered | Not loaded | n/a | on request | instruction | broken | essential | wrong | rework | v0.2.0 + v0.2.1 |
| /wake | `.claude/commands/wake.md` | Registered | Not loaded | n/a | on request | instruction | broken | essential | wrong | rework | v0.2.0 + v0.2.1 |
| /feedback | `.claude/commands/feedback.md` | Registered | Not loaded | n/a | on request | instruction | unproven | essential | outdated | rework | v0.2.0 + v0.2.1 |
| /add-agent | `.claude/commands/add-agent.md` | Registered | Not loaded | n/a | on request | instruction | likely | useful | current | keep | - |
| /add-mission | `.claude/commands/add-mission.md` | Slash command registered | Not loaded | n/a | prompts/add-mission.md on request | instruction | likely | useful | outdated | rework | v0.2.1+ |
| /brainstorm | `.claude/commands/brainstorm.md` | Registered | Not loaded | n/a | on request | instruction | likely | useful | outdated | keep | - |
| /code-red | `.claude/commands/code-red.md` | Registered | Not loaded | n/a | on request | instruction | likely | useful | wrong | rework | v0.2.1+ |
| /finalize | `.claude/commands/finalize.md` | Registered | Not loaded | n/a | on request | instruction | likely | useful | outdated | keep | - |
| /help | `.claude/commands/help.md` | Registered | Not loaded | n/a | on request | instruction | likely | useful | outdated | rework | v0.2.1+ |
| /list-agents | `.claude/commands/list-agents.md` | Registered | Not loaded | n/a | on request | instruction | likely | useful | current | keep | v0.2.0 |
| /summary | `.claude/commands/summary.md` | Registered | Not loaded | n/a | on request | instruction | likely | useful | current | rework | v0.2.1+ |
| .codex/prompts/*.md Codex command mirrors (26 files) | `.codex/prompts/` | n/a | Not discovered from the project | n/a | n/a | instruction | broken | optional | outdated | rework | v0.2.0 |
| /cx-mode | `.claude/commands/cx-mode.md` | Registered | Not loaded | n/a | on request | instruction | broken | optional | wrong | rework | v0.2.1+ |
| /ops-mode | `.claude/commands/ops-mode.md` | Registered | Not loaded | n/a | on request | instruction | broken | optional | wrong | rework | v0.2.1+ |
| /product-mode | `.claude/commands/product-mode.md` | Registered | Not loaded | n/a | on request | instruction | broken | optional | wrong | rework | v0.2.1+ |
| /strategic-mode | `.claude/commands/strategic-mode.md` | Registered | Not loaded | n/a | on request | instruction | broken | optional | wrong | rework | v0.2.1+ |
| prompts/*.md generic command mirrors (26 files) | `prompts/` | n/a | n/a | n/a | Not auto-loaded | instruction | broken | optional | wrong | rework | v0.2.0 |
| prompts/** (generic mirrors) | `prompts/*.md` | n/a | Not auto-loaded | Not auto-loaded | Readable only if the model is told to open one | instruction | unproven | optional | outdated | cut | v0.2.0 |
| /founder-mode | `.claude/commands/founder-mode.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | rework | v0.2.1+ |
| /remove-agent | `.claude/commands/remove-agent.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | keep | - |
| /reset | `.claude/commands/reset.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | keep | - |
| /revenue-mode | `.claude/commands/revenue-mode.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | rework | v0.2.1+ |
| /review-mission | `.claude/commands/review-mission.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | outdated | rework | v0.2.1+ |
| /route-mission | `.claude/commands/route-mission.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | cut | v0.2.1+ |
| /show-active-guilds | `.claude/commands/show-active-guilds.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | cut | v0.2.1+ |
| /show-next-moves | `.claude/commands/show-next-moves.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | cut | v0.2.1+ |
| /show-owner | `.claude/commands/show-owner.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | cut | v0.2.1+ |
| /show-risks | `.claude/commands/show-risks.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | cut | v0.2.1+ |
| .codex/prompts/** (26 command mirrors) | `.codex/prompts/*.md` | n/a | NOT loaded | n/a | n/a | none | broken | cut | wrong | cut | v0.2.0 |
| /initiate | `.claude/commands/initiate.md` | Registered | Not loaded | n/a | on request | instruction | likely | cut | outdated | cut | v0.2.1+ |

## 5. Skills (8)

Essential 1 / useful 0 / optional 7 / cut 0. Reliability proven 7 / likely 0 / unproven 1 / broken 0.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action | Planned for |
|---|---|---|---|---|---|---|---|---|---|---|---|
| .agents/skills/tess-* (commands as cross-runtime skills) | `(missing; manifest never_touch has .agents/**)` | n/a | Discovers .agents/skills from cwd up to repo root | Workspace .agents/skills alias | Varies | instruction | unproven | essential | missing | add | v0.2.0 |
| 3d-web-experience skill | `.claude/skills/3d-web-experience/SKILL.md` | Registered | n/a | n/a | n/a | instruction | proven | optional | wrong | cut | v0.2.1+ |
| design-taste-frontend skill | `.claude/skills/design-taste-frontend/SKILL.md` | Registered | n/a | n/a | n/a | instruction | proven | optional | outdated | cut | v0.2.1+ |
| full-output-enforcement skill | `.claude/skills/full-output-enforcement/SKILL.md` | Registered | n/a | n/a | n/a | instruction | proven | optional | current | defer | v0.2.1+ |
| high-end-visual-design skill | `.claude/skills/high-end-visual-design/SKILL.md` | Registered | n/a | n/a | n/a | instruction | proven | optional | outdated | cut | v0.2.1+ |
| industrial-brutalist-ui skill | `.claude/skills/industrial-brutalist-ui/SKILL.md` | Registered | n/a | n/a | n/a | instruction | proven | optional | outdated | cut | v0.2.1+ |
| minimalist-ui skill | `.claude/skills/minimalist-ui/SKILL.md` | Registered | n/a | n/a | n/a | instruction | proven | optional | outdated | cut | v0.2.1+ |
| redesign-existing-projects skill | `.claude/skills/redesign-existing-projects/SKILL.md` | Registered | n/a | n/a | n/a | instruction | proven | optional | outdated | cut | v0.2.1+ |

## 6. Agents (subagent definitions and roster) (13)

Essential 1 / useful 3 / optional 9 / cut 0. Reliability proven 0 / likely 9 / unproven 3 / broken 1.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action | Planned for |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Mandatory verifiers (Reid, Quinn, Cyra, Verity, Maialen, Lysandra) | `.tess/core/agents-dispatch/{reid,quinn,cyra,verity,maialen,lysandra}.md` | founders install | n/a | n/a | n/a | instruction | broken | essential | wrong | rework | v0.2.1+ |
| Clio session scribe (dispatch def + persona) | `.tess/core/agents-dispatch/clio.md; agents/clio/README.md` | Dispatchable only if installed | n/a | n/a | n/a | instruction | unproven | useful | outdated | rework | v0.2.1+ |
| eva (HR/crew design) | `.claude/agents/eva.md` | Subagent registered | n/a | n/a | n/a | instruction | likely | useful | current | keep | - |
| leah (Senior Researcher) | `.claude/agents/leah.md` | Subagent registered | n/a | n/a | n/a | instruction | likely | useful | current | keep | - |
| Persona prose specs + guild files (agents/ 165 entries, 3.2 MB; mirror .tess/core/agents 3.2 MB) | `agents/<name>/{README,identity,personality,soul,capabilities}.md, agents/*-guild.md` | Not auto-loaded | n/a | n/a | n/a | none | unproven | optional | current | defer | v0.2.1+ |
| Roster persona prose specs (144 persona dirs, 736 files, 3.2 MB; mirrored in .tess/core/agents) | `agents/<name>/**` | Read only on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer | v0.2.1+ |
| apolline (Chief Sales) | `.claude/agents/apolline.md` | Subagent registered | n/a | n/a | n/a | instruction | likely | optional | current | keep | - |
| athena (Chief Strategy) | `.claude/agents/athena.md` | Subagent registered | n/a | n/a | n/a | instruction | likely | optional | current | keep | - |
| Benched orchestrators (4: product-delivery, client-experience, strategic-growth, operational-reliability) | `.tess/core/agents-dispatch/*-orchestrator.md` | Only after recruit/path install | n/a | n/a | n/a | instruction | likely | optional | wrong | rework | v0.2.1+ |
| Benched specialist roster (144 dispatch definitions) | `.tess/core/agents-dispatch/*.md (150 incl. 6 orchestrators; 102 sonnet, 47 opus, 1 haiku)` | Installed into .claude/agents via tessctl recruit / path | n/a | n/a | n/a | instruction | likely | optional | current | defer | v0.2.1+ |
| founders-office-orchestrator | `.claude/agents/founders-office-orchestrator.md` | Subagent registered | n/a | n/a | n/a | instruction | likely | optional | current | keep | - |
| revenue-orchestrator | `.claude/agents/revenue-orchestrator.md` | Subagent registered | n/a | n/a | n/a | instruction | likely | optional | current | keep | - |
| zelie (Deck design) | `.claude/agents/zelie.md` | Subagent registered | n/a | n/a | n/a | instruction | likely | optional | current | keep | - |

## 7. Workflows (1)

Essential 0 / useful 0 / optional 1 / cut 0. Reliability proven 0 / likely 0 / unproven 1 / broken 0.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action | Planned for |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Saved workflows (.claude/workflows) | `(none in tess-os; saved workflows exist only in private instances)` | Workflow tool only | n/a | n/a | n/a | mechanical | unproven | optional | missing | defer | v0.2.1+ |

## 8. Config and state files (13)

Essential 8 / useful 5 / optional 0 / cut 0. Reliability proven 5 / likely 4 / unproven 1 / broken 3.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action | Planned for |
|---|---|---|---|---|---|---|---|---|---|---|---|
| .tess/tess.lock framework pin | `.tess/tess.lock` | Engine data | Engine data | Engine data | Engine data | mechanical | broken | essential | wrong | rework | v0.2.0 + v0.2.1 |
| Release public key (.tess/keys/twiss-release-key.asc) | `.tess/keys/twiss-release-key.asc` | Engine data | Engine data | Engine data | Engine data | mechanical | broken | essential | wrong | rework | v0.2.1+ |
| MISSING: GEMINI.md entry / .gemini/settings.json context.fileName | (new) GEMINI.md or .gemini/settings.json | n/a | n/a | Default context file is GEMINI.md | n/a | mechanical | unproven | essential | missing | add | v0.2.0 |
| .claude/settings.json / settings-core.json (hook wiring) | `.claude/settings.json, .tess/core/settings-core.json` | Loaded | n/a | n/a | n/a | mechanical | proven | essential | outdated | rework | v0.2.0 |
| .tess/state/ cross-harness state root | `.tess/state/{memory,tasks,ledger,locks,skills,receipts}` | Via tessctl | Via tessctl | Via tessctl | Via tessctl | mechanical | proven | essential | outdated | rework | v0.2.1+ |
| Instance .gitignore (template copy of the framework's) | `.gitignore; create-tess/template/.gitignore (identical)` | git | git | git | git | mechanical | proven | essential | wrong | rework | v0.2.0 |
| operator/profile.json | `operator/profile.json` | Read by tessctl render | Same | n/a | n/a | mechanical | proven | essential | outdated | rework | v0.2.0 |
| tess.manifest.json render_targets | `tess.manifest.json` | claude-code enabled | codex enabled | No gemini target exists in RENDER_TARGETS | generic not enabled | mechanical | proven | essential | outdated | rework | v0.2.1+ |
| missions/ records | `missions/<id>/` | Via tessctl mission | Same | Same | Same | mechanical | broken | useful | outdated | rework | v0.2.1+ |
| .codex/config.toml | `.codex/config.toml` | n/a | Loaded only for a trusted project | n/a | n/a | mechanical | likely | useful | current | keep | - |
| codex-config.toml.tpl → .codex/config.toml | `.tess/core/templates/agents-md/codex-config.toml.tpl` | n/a | Loaded only when the project is trusted | n/a | n/a | mechanical | likely | useful | current | keep | v0.2.0 |
| core/policy/policy.yaml (ship-gate policy) | `core/policy/policy.yaml` | Enforced by tessctl gate via git hooks/CI | Same | Same | Same | mechanical | likely | useful | current | keep | - |
| operator/ stubs | `operator/{profile.json,user-profile.md,identity-stub.md,org-channels.md,build-facts-stub.md}` | Rendered into CLAUDE.md only when inject:true | Not in AGENTS.md | n/a | n/a | mechanical | likely | useful | outdated | rework | v0.2.0 |

## 9. Engine (tessctl subcommands, drivers, render targets, tools) (94)

Essential 19 / useful 49 / optional 26 / cut 0. Reliability proven 71 / likely 12 / unproven 5 / broken 6.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action | Planned for |
|---|---|---|---|---|---|---|---|---|---|---|---|
| tessctl render | `.tess/bin/tessctl:2841 cmd_render; _render_enabled_targets 2825` | Produces CLAUDE.md and settings.json, which Claude Code auto-loads | Produces AGENTS.md | Nothing rendered for Gemini | Produces AGENTS.md | mechanical | broken | essential | wrong | rework | v0.2.0 |
| tessctl rollback | `.tess/bin/tessctl:5323 cmd_rollback; _prune_snapshots 1566` | CLI | CLI | CLI | CLI | mechanical | broken | essential | wrong | rework | v0.2.0 |
| tessctl self-update | `.tess/bin/tessctl:6407 cmd_self_update` | CLI | CLI | CLI | CLI | mechanical | broken | essential | wrong | rework | v0.2.0 + v0.2.1 |
| tessctl update (signed OTA) | `.tess/bin/tessctl:4527 cmd_update` | CLI | CLI | CLI | CLI | mechanical | broken | essential | wrong | rework | v0.2.0 + v0.2.1 |
| MISSING: Memory index budget guard | (new) tessctl doctor check + SessionStart warn | Auto memory loads 'first 200 lines or 25KB' | AGENTS.md combined cap 32 KiB by default | Concatenates all context files | Tool-specific | mechanical | unproven | essential | missing | add | v0.2.0 |
| Mode scaffolds (personal / agency / organisation + presets) | `(absent; clients/_template is the only entity template)` | Files + CLAUDE.md START HERE | Files + AGENTS.md pointer | Files + AGENTS.md pointer | Files + AGENTS.md pointer | mechanical | unproven | essential | missing | add | v0.2.0 |
| tessctl update | `.tess/bin/tessctl (cmd_update)` | CLI | CLI | CLI | CLI | mechanical | likely | essential | current | keep | v0.2.0 + v0.2.1 |
| render target: claude-code | `.tess/bin/tessctl:2323 ClaudeCodeRenderTarget` | Auto-loaded CLAUDE.md plus .claude/* | n/a | n/a | n/a | mechanical | proven | essential | current | keep | v0.2.0 |
| render target: codex | `.tess/bin/tessctl:2397 CodexRenderTarget` | n/a | AGENTS.md is loaded natively | n/a | AGENTS.md | mechanical | proven | essential | outdated | rework | v0.2.0 |
| tessctl approve | `.tess/bin/tessctl:5763 cmd_approve` | CLI | CLI | CLI | CLI | mechanical | proven | essential | wrong | rework | v0.2.0 |
| tessctl doctor | `.tess/bin/tessctl (cmd_doctor)` | CLI | CLI | CLI | CLI | mechanical | proven | essential | current | rework | v0.2.1+ |
| tessctl doctor (incl. --fix, --publish-clean) | `.tess/bin/tessctl:3133 cmd_doctor; 3076 publish-clean` | CLI | CLI | CLI | git hook fires on commit | mechanical | proven | essential | outdated | rework | v0.2.0 |
| tessctl gate | `.tess/bin/tessctl (cmd_gate: pre-commit/pre-push/ci/install-hooks/signoff/clear)` | CLI + git hooks | Same | Same | Same | ci | proven | essential | current | keep | - |
| tessctl log append | `.tess/bin/tessctl:17136; LEDGER_EVENTS 15592` | CLI | CLI | CLI | CLI | mechanical | proven | essential | outdated | rework | v0.2.1+ |
| tessctl mcp serve (MCP server) | `.tess/bin/tessctl:20158 _mcp_serve; tools 19780-19942` | Would load via .mcp.json, but none ships | Would load via [mcp_servers] in .codex/config.toml | Would load via .gemini/settings.json mcpServers | Depends on the tool | mechanical | proven | essential | outdated | rework | v0.2.1+ |
| tessctl memory adopt | `.tess/bin/tessctl:19563; DEFAULT_MEMORY_ADOPT_HARNESS 18703` | Default harness | 'no well-known default memory path for harness codex' rc 1 | Unsupported | Unsupported | mechanical | proven | essential | wrong | rework | v0.2.1+ |
| tessctl root shim + Python engine runtime | `tessctl; .tess/bin/tessctl (21,325 lines)` | Bash tool | shell | shell tool, if the model knows to call it | shell where the tool has one | mechanical | proven | essential | current | rework | v0.2.1+ |
| tessctl roster apply | `.tess/bin/tessctl:6741 _roster_apply` | Installs .claude/agents/*.md, which Claude Code loads as subagents | No Codex agent equivalent rendered | No Gemini agent equivalent | n/a | mechanical | proven | essential | current | keep | - |
| tessctl verify | `.tess/bin/tessctl (cmd_verify)` | CLI | CLI | CLI | CLI | mechanical | proven | essential | current | keep | - |
| tessctl capture | `.tess/bin/tessctl:3534 cmd_capture` | CLI | CLI | CLI | CLI | mechanical | broken | useful | wrong | rework | v0.2.0 |
| tessctl publish | `.tess/bin/tessctl:5117 cmd_publish` | CLI | CLI | CLI | CLI | mechanical | broken | useful | wrong | rework | v0.2.0 |
| tessctl identity | `.tess/bin/tessctl (cmd_identity)` | CLI | CLI | CLI | CLI | mechanical | likely | useful | current | keep | - |
| tessctl init | `.tess/bin/tessctl (cmd_init)` | CLI via Bash | CLI via shell | CLI via run_shell_command | If the tool has a shell | mechanical | likely | useful | outdated | rework | v0.2.0 |
| tessctl override | `.tess/bin/tessctl (cmd_override)` | CLI | CLI | CLI | CLI | mechanical | likely | useful | current | keep | v0.2.0 |
| tessctl reset | `.tess/bin/tessctl (cmd_reset)` | CLI | CLI | CLI | CLI | mechanical | likely | useful | current | keep | v0.2.0 |
| tessctl resolve | `.tess/bin/tessctl (cmd_resolve)` | CLI | CLI | CLI | CLI | mechanical | likely | useful | current | keep | - |
| tessctl validate | `.tess/bin/tessctl (cmd_validate)` | CLI | CLI | CLI | CLI | mechanical | likely | useful | current | keep | - |
| tessctl vault | `.tess/bin/tessctl (cmd_vault: init/set/get/list/rm/rotate/exec/doctor/scan)` | CLI | CLI | CLI | CLI | mechanical | likely | useful | outdated | rework | v0.2.1+ |
| core/contracts/*.schema.json + README (11 files) | `core/contracts/` | Used by tessctl validate/gate/run, not loaded into context | Same | Same | Same | mechanical | proven | useful | current | keep | - |
| tessctl bench | `.tess/bin/tessctl (cmd_bench)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl diff | `.tess/bin/tessctl:5405 cmd_diff` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl gate ci | `.tess/bin/tessctl:11539` | n/a | n/a | n/a | n/a | ci | proven | useful | current | keep | - |
| tessctl gate clear | `.tess/bin/tessctl:13349` | CLI | CLI | CLI | CLI | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| tessctl gate install-hooks | `.tess/bin/tessctl:12088` | Run by create-tess activateGate | same | same | same | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| tessctl gate pre-commit | `.tess/bin/tessctl:11472` | Runs on any git commit | Same git hook | Same git hook | Same git hook | mechanical | proven | useful | current | keep | - |
| tessctl gate pre-push (ship-gate) | `.tess/bin/tessctl:11502` | git pre-push hook | Same git hook | Same git hook | Same git hook | mechanical | proven | useful | wrong | rework | v0.2.1+ |
| tessctl lock | `.tess/bin/tessctl (cmd_lock)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl lock (--check / --regen) | `.tess/bin/tessctl:6231 cmd_lock` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl log | `.tess/bin/tessctl (cmd_log append/view/verify)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | rework | v0.2.1+ |
| tessctl log verify | `.tess/bin/tessctl:17187` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl log view | `.tess/bin/tessctl:17153` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl mcp serve | `.tess/bin/tessctl (cmd_mcp)` | Usable as an MCP server | MCP supported | MCP supported | Where MCP is supported | mechanical | proven | useful | current | rework | v0.2.1+ |
| tessctl mission | `.tess/bin/tessctl (cmd_mission new/status)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| tessctl mission new | `.tess/bin/tessctl:13245` | CLI | CLI | CLI | CLI | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| tessctl mission status | `.tess/bin/tessctl:13275` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl pathway | `.tess/bin/tessctl (cmd_pathway)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl recruit | `.tess/bin/tessctl (cmd_recruit)` | Writes .claude/agents/<n>.md | No Codex agent output | n/a | n/a | mechanical | proven | useful | current | keep | - |
| tessctl rename | `.tess/bin/tessctl (cmd_rename)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl restore | `.tess/bin/tessctl (cmd_restore)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | v0.2.0 |
| tessctl retry check | `.tess/bin/tessctl:13672` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl retry log | `.tess/bin/tessctl:13698` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl roster | `.tess/bin/tessctl (cmd_roster)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl roster list | `.tess/bin/tessctl:6814 _roster_list` | CLI | CLI | CLI | CLI | mechanical | proven | useful | outdated | rework | v0.2.0 |
| tessctl set-operator | `.tess/bin/tessctl (cmd_set_operator)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl skill from-task | `.tess/bin/tessctl (cmd_skill)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| tessctl tasks | `.tess/bin/tessctl (cmd_tasks new/set/claim/release/block/pull/render/handoff)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| tessctl tasks block | `.tess/bin/tessctl:16834` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl tasks new | `.tess/bin/tessctl:16519` | CLI | CLI | CLI | CLI via AGENTS.md | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| tessctl tasks pull | `.tess/bin/tessctl:16893` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl tasks set | `.tess/bin/tessctl:16570` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl vault doctor | `.tess/bin/tessctl:8431` | CLI | CLI | CLI | CLI | mechanical | proven | useful | wrong | rework | v0.2.1+ |
| tessctl vault exec | `.tess/bin/tessctl:8363` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl vault init | `.tess/bin/tessctl:7693` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl vault scan | `.tess/bin/tessctl:8587` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl vault set | `.tess/bin/tessctl:8181` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl verdict | `.tess/bin/tessctl (cmd_verdict: keygen/sign/verify)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl verdict sign | `.tess/bin/tessctl:9473` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| tessctl verdict verify | `.tess/bin/tessctl:9584` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep | - |
| Memory-continuity heartbeat (L2) + launchd template | `scripts/heartbeat/*, scripts/heartbeat.sh, scripts/launchd/*.plist.template` | Spawns claude -p when activated | n/a | n/a | n/a | mechanical | unproven | optional | current | defer | v0.2.1+ |
| run driver: codex (CodexExecDriver) | `.tess/bin/tessctl:14135` | n/a | Spawns codex exec | n/a | n/a | mechanical | unproven | optional | outdated | defer | v0.2.1+ |
| run driver: gemini | `RUN_DRIVERS .tess/bin/tessctl:14348 = {claude, codex, fake}` | n/a | n/a | missing | n/a | none | unproven | optional | missing | defer | v0.2.0 |
| run driver: claude (ClaudeCliDriver) | `.tess/bin/tessctl:14058` | Spawns Claude Code headless | n/a | n/a | n/a | mechanical | likely | optional | current | defer | v0.2.1+ |
| tessctl retry | `.tess/bin/tessctl (cmd_retry log/check/migrate)` | CLI | CLI | CLI | CLI | mechanical | likely | optional | current | keep | - |
| tessctl run | `.tess/bin/tessctl (cmd_run)` | Spawns claude | Spawns codex | No driver | n/a | mechanical | likely | optional | current | defer | v0.2.1+ |
| tessctl trace | `.tess/bin/tessctl (cmd_trace export)` | CLI | CLI | CLI | CLI | mechanical | likely | optional | current | keep | - |
| render target: generic | `.tess/bin/tessctl:2471 GenericRenderTarget` | n/a | n/a | n/a | AGENTS.md shared with codex | mechanical | proven | optional | outdated | cut | v0.2.0 |
| run driver: fake (FakeDriver) | `.tess/bin/tessctl:14216` | n/a | n/a | n/a | n/a | mechanical | proven | optional | current | keep | - |
| tessctl audit | `.tess/bin/tessctl (cmd_audit export/verify)` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep | - |
| tessctl audit export | `.tess/bin/tessctl:17741` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep | - |
| tessctl audit verify | `.tess/bin/tessctl:17957` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep | - |
| tessctl gate signoff sign / verify | `.tess/bin/tessctl:12106 / 12193` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | defer | v0.2.1+ |
| tessctl gate-status | `.tess/bin/tessctl (cmd_gate_status)` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep | - |
| tessctl retry migrate | `.tess/bin/tessctl:13752` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep | - |
| tessctl run (conductor loop) | `.tess/bin/tessctl:15403 cmd_run` | CLI | CLI | No Gemini driver | n/a | mechanical | proven | optional | current | defer | v0.2.1+ |
| tessctl tasks claim | `.tess/bin/tessctl:16717` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep | - |
| tessctl tasks handoff | `.tess/bin/tessctl:17066` | CLI | CLI | Not a valid target | n/a | mechanical | proven | optional | current | defer | v0.2.1+ |
| tessctl tasks release | `.tess/bin/tessctl:16781` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep | - |
| tessctl tasks render | `.tess/bin/tessctl:16946` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep | - |
| tessctl trace export | `.tess/bin/tessctl:12739` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | defer | v0.2.1+ |
| tessctl vault get | `.tess/bin/tessctl:8225` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep | - |
| tessctl vault list | `.tess/bin/tessctl:8270` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep | - |
| tessctl vault rm | `.tess/bin/tessctl:8295` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep | - |
| tessctl vault rotate | `.tess/bin/tessctl:8311` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep | - |
| tessctl verdict keygen | `.tess/bin/tessctl:9643` | CLI | CLI | CLI | CLI | mechanical | proven | optional | outdated | rework | v0.2.1+ |

## 10. Installer (create-tess) and scaffolds (24)

Essential 11 / useful 10 / optional 2 / cut 1. Reliability proven 16 / likely 0 / unproven 2 / broken 6.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action | Planned for |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Agency mode scaffold (clients/_template) | `clients/_template/{CLAUDE.md,branding/DESIGN.md,kb/}` | Nested CLAUDE.md loads when working in the folder | No AGENTS.md in template, so Codex never reads the brief | Not read | Not read | instruction | broken | essential | outdated | rework | v0.2.0 |
| Python/PyYAML preflight (ensurePython3) | `create-tess/src/scaffold.js:89` | n/a | n/a | n/a | n/a | mechanical | broken | essential | wrong | rework | v0.2.1+ |
| writeProfile (operator/profile.json) | `create-tess/src/keystone.js:41` | Read by the engine at render time | same | same | same | mechanical | broken | essential | wrong | rework | v0.2.0 |
| bake (roster apply, set-operator, rename, pathway, render) | `create-tess/src/keystone.js:100` | Renders CLAUDE.md | Renders AGENTS.md | Nothing | AGENTS.md | mechanical | proven | essential | current | keep | - |
| build-template + template-drift-guard (maintainer) | `create-tess/scripts/build-template.mjs; test/template-drift-guard.test.js` | n/a | n/a | n/a | n/a | ci | proven | essential | current | keep | - |
| check (doctor + verify after scaffold) | `create-tess/src/keystone.js:261` | n/a | n/a | n/a | n/a | mechanical | proven | essential | current | keep | - |
| create-tess entry (npx create-tess / npm create tess), bundled template | `create-tess/bin/create-tess.mjs; src/index.js main 225` | Produces the Claude surfaces | Produces AGENTS.md and .codex | Produces nothing for Gemini | Produces AGENTS.md | mechanical | proven | essential | current | keep | - |
| create-tess wizard (journey.js) | `create-tess/src/journey.js` | Terminal wizard, before any agent session | same | same | same | mechanical | proven | essential | outdated | rework | v0.2.1+ |
| Policy key reset + regenPolicyLock | `create-tess/src/policy-reset.js; keystone.js:83` | n/a | n/a | n/a | n/a | mechanical | proven | essential | current | keep | - |
| Secrets-exclusion copy filter (ignore.js) | `create-tess/src/ignore.js:237, 312` | n/a | n/a | n/a | n/a | mechanical | proven | essential | current | keep | - |
| Template secrets exclusion (ignore.js) | `create-tess/src/ignore.js, pathnorm.js` | n/a | n/a | n/a | n/a | mechanical | proven | essential | current | keep | - |
| --force clean-replace + rollbackTarget | `create-tess/src/index.js:313, 332-338; scaffold.js:224-241` | n/a | n/a | n/a | n/a | mechanical | broken | useful | wrong | rework | v0.2.0 |
| Install detection (clobberReason) | `create-tess/src/scaffold.js:101-109` | n/a | n/a | n/a | n/a | mechanical | broken | useful | wrong | rework | v0.2.0 |
| Adopt an existing instance (tessctl adopt / create-tess --adopt) | `(absent; planned)` | n/a | n/a | n/a | n/a | none | unproven | useful | missing | add | v0.2.1+ |
| activateGate (git init + install-hooks) | `create-tess/src/keystone.js:198` | git hooks | git hooks | git hooks | git hooks | mechanical | proven | useful | wrong | rework | v0.2.1+ |
| Arrival card and first-push notice | `create-tess/src/index.js:164 printFirstPushNotice; printArrival` | Tells the user to run /add-mission | Same text | Same | Same | instruction | proven | useful | wrong | rework | v0.2.0 |
| create-tess non-interactive flags (args.js) | `create-tess/src/args.js` | n/a | n/a | n/a | n/a | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| create-tess wizard (npm create tess) | `create-tess/src/journey.js, args.js` | Runs before any runtime | Same | Same | Same | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| git init + gate install-hooks | `create-tess/src/keystone.js` | n/a | n/a | n/a | n/a | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| Scaffold payload (what gets copied) | `create-tess/template/** (2,653 files)` | n/a | n/a | n/a | n/a | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| Template payload scope | `create-tess/template/ (built by scripts/build-template.mjs)` | n/a | n/a | n/a | n/a | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| --template-source / --template-ref git path | `create-tess/src/git-template-source.js:52` | n/a | n/a | n/a | n/a | mechanical | broken | optional | outdated | rework | v0.2.0 |
| Extra presets (software project; researcher/creator; student) | `(builders/coding-squad path exists; others missing)` | Preset squads + folders | Same | Same | Same | instruction | unproven | optional | missing | defer | v0.2.0 + v0.2.1 |
| Installer identity strings | `create-tess/src (install summary)` | n/a | n/a | n/a | n/a | none | proven | cut | wrong | rework | v0.2.0 |

## 11. CI and release gates (10)

Essential 5 / useful 4 / optional 1 / cut 0. Reliability proven 6 / likely 0 / unproven 3 / broken 1.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action | Planned for |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CI: ci.yml | `.github/workflows/ci.yml` | n/a | n/a | n/a | n/a | ci | proven | essential | current | keep | - |
| CI: ci.yml create-tess job | `.github/workflows/ci.yml job create-tess` | n/a | n/a | n/a | n/a | ci | proven | essential | current | keep | - |
| CI: ci.yml secret-scan (gitleaks) | `.github/workflows/ci.yml job secret-scan` | n/a | n/a | n/a | n/a | ci | proven | essential | current | keep | - |
| CI: ci.yml tests job | `.github/workflows/ci.yml job test` | n/a | n/a | n/a | n/a | ci | proven | essential | current | keep | - |
| CI: tess-gate.yml | `.github/workflows/tess-gate.yml` | n/a | n/a | n/a | n/a | ci | proven | essential | current | keep | - |
| CI: release.yml | `.github/workflows/release.yml` | n/a | n/a | n/a | n/a | ci | broken | useful | wrong | rework | v0.2.0 |
| CI: publish-npm.yml | `.github/workflows/publish-npm.yml` | n/a | n/a | n/a | n/a | ci | unproven | useful | current | keep | v0.2.0 |
| MISSING: Fresh-clone probe (zero-context comprehension test) | (new) CI job / tessctl probe | Runtime-agnostic CI | Runtime-agnostic CI | Runtime-agnostic CI | Runtime-agnostic CI | ci | unproven | useful | missing | add | v0.2.0 + v0.2.1 |
| CI: CodeQL (GitHub default setup) | `(GitHub default setup; no workflow file)` | n/a | n/a | n/a | n/a | ci | proven | useful | current | keep | - |
| CI: tess-gate.yml installed into instances | `instance .github/workflows/tess-gate.yml (written by gate install-hooks)` | n/a | n/a | n/a | n/a | ci | unproven | optional | wrong | rework | v0.2.1+ |

## 12. Docs (8)

Essential 0 / useful 6 / optional 2 / cut 0. Reliability proven 2 / likely 1 / unproven 5 / broken 0.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action | Planned for |
|---|---|---|---|---|---|---|---|---|---|---|---|
| docs/MEMORY_AND_ORCHESTRATION_CONTRACT.md | `docs/MEMORY_AND_ORCHESTRATION_CONTRACT.md` | n/a | n/a | n/a | n/a | none | unproven | useful | outdated | rework | v0.2.1+ |
| docs/STATE_LAYER.md + docs/memory-continuity.md | `docs/STATE_LAYER.md; docs/memory-continuity.md` | n/a | Referenced by AGENTS.md | n/a | Referenced by AGENTS.md | none | unproven | useful | current | keep | - |
| MISSING: Runtime capability matrix (honest reliability doc) | (new) docs/RUNTIMES.md | Documents CLAUDE.md/@import, hooks, subagents | Documents AGENTS.md 32 KiB, hooks.json trust, .agents/skills, prompts deprecated | Documents GEMINI.md/context.fileName, hooks fingerprinting, .agents/skills, .gemini/commands TOML | AGENTS.md only | none | unproven | useful | missing | add | v0.2.0 |
| adapters/ + CONFORMANCE.md + manifests | `adapters/` | Claude C3 | Codex C2 | No row yet | Generic C2 | none | likely | useful | outdated | rework | v0.2.0 |
| adapters/manifests + CONFORMANCE | `adapters/manifests/*.adapter-manifest.json; adapters/CONFORMANCE.md` | C3 preview | C2 | No manifest | generic C2 | none | proven | useful | outdated | rework | v0.2.0 |
| missions/README.md (mission records as code) | `missions/README.md` | Not referenced by doctrine/commands | Not referenced | n/a | Not referenced | mechanical | proven | useful | current | keep | - |
| .tess/core/MANIFEST.md | `.tess/core/MANIFEST.md` | n/a | n/a | n/a | n/a | none | unproven | optional | outdated | keep | - |
| conductor/release-process.md | `conductor/release-process.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | current | rework | v0.2.0 + v0.2.1 |

## 13. Other repo content (18)

Essential 2 / useful 3 / optional 11 / cut 2. Reliability proven 11 / likely 4 / unproven 2 / broken 1.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action | Planned for |
|---|---|---|---|---|---|---|---|---|---|---|---|
| .tess/state/memory/ shared memory store | `.tess/state/memory/` | Only if `tessctl memory adopt` symlinks Claude auto memory | Pointed to by AGENTS.md | n/a | Pointed to by AGENTS.md | mixed | broken | essential | outdated | rework | v0.2.1+ |
| memory/ (project cards + registry.md) | `memory/projects/*.md; memory/registry.md` | Read if doctrine says so | Same | Same | Same | instruction | likely | essential | current | keep | - |
| proving-ground/ + gate-arena/ | `proving-ground/, gate-arena/` | n/a | n/a | n/a | n/a | ci | proven | useful | current | keep | - |
| scripts/heartbeat (memory-continuity heartbeat) + launchd | `scripts/heartbeat.sh; scripts/heartbeat/; scripts/launchd/` | Tier-2 synthesis spawns claude -p | Not used | Not used | n/a | mechanical | proven | useful | outdated | rework | v0.2.1+ |
| tools/validate_adapter_manifests | `tools/validate_adapter_manifests.py; adapter_manifest_validator.py EXPECTED_CLAIMS:33` | n/a | n/a | n/a | n/a | ci | proven | useful | current | keep | - |
| connectors/ registry | `connectors/registry/{anthropic,openai,gemini}` | n/a | n/a | n/a | n/a | none | unproven | optional | current | defer | v0.2.0 |
| gate-arena/ (gate bypass corpus) | `gate-arena/` | n/a | n/a | n/a | n/a | none | unproven | optional | outdated | cut | v0.2.1+ |
| gui/ Mission Control dashboard | `gui/` | Spawns claude CLI | n/a | n/a | n/a | mechanical | likely | optional | current | defer | v0.2.1+ |
| intent-router/ + spec-engine/ + orchestrator/ + telemetry/ (idea-to-app pipeline) | `intent-router/, spec-engine/, orchestrator/, telemetry/, main.py` | Not wired to any runtime session | n/a | n/a | n/a | mechanical | likely | optional | current | defer | v0.2.1+ |
| tools/receipt-emit, receipt-verify, adapter/AEC validators | `tools/` | n/a | n/a | n/a | n/a | mechanical | likely | optional | current | keep | - |
| connectors/validate_connector_manifests | `connectors/` | n/a | n/a | n/a | n/a | ci | proven | optional | current | keep | - |
| examples/receipt-demo + Makefile | `examples/receipt-demo/; Makefile` | n/a | n/a | n/a | n/a | mechanical | proven | optional | current | keep | - |
| proving-ground/ (benchmark harness) | `proving-ground/` | Claude driver | n/a | n/a | n/a | mechanical | proven | optional | outdated | cut | v0.2.1+ |
| tools/receipt-emit | `tools/receipt-emit/` | CLI / orchestrator opt-in | CLI | CLI | CLI | mechanical | proven | optional | current | keep | - |
| tools/receipt-verify | `tools/receipt-verify/` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep | - |
| tools/validate_aec_support_policy | `tools/validate_aec_support_policy.py` | n/a | n/a | n/a | n/a | ci | proven | optional | current | keep | - |
| main.py / pyproject stub | `main.py; pyproject.toml` | n/a | n/a | n/a | n/a | none | proven | cut | outdated | cut | v0.2.1+ |
| orchestrator / intent-router / spec-engine / telemetry (idea-to-app codegen spine) | `orchestrator/; intent-router/; spec-engine/; telemetry/ (69 files)` | n/a | n/a | n/a | n/a | mechanical | proven | cut | outdated | cut | v0.2.1+ |

