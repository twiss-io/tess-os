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
- **Evidence.** The public table keeps the verdicts only. The probe notes
  behind each row stay with the maintainers.

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

## Summary

### Essential x reliability

| essential \ reliability | proven | likely | unproven | broken | total |
|---|---|---|---|---|---|
| essential | 38 | 5 | 48 | 20 | 111 |
| useful | 68 | 31 | 31 | 10 | 140 |
| optional | 35 | 26 | 36 | 12 | 109 |
| cut | 5 | 1 | 2 | 3 | 11 |
| total | 146 | 63 | 117 | 45 | 371 |

### Status x v0.2 action

| status \ v02_action | keep | rework | add | cut | defer | total |
|---|---|---|---|---|---|---|
| current | 118 | 11 | 0 | 5 | 27 | 161 |
| outdated | 5 | 80 | 0 | 16 | 2 | 103 |
| wrong | 0 | 47 | 0 | 6 | 0 | 53 |
| missing | 0 | 0 | 48 | 0 | 6 | 54 |
| total | 123 | 138 | 48 | 27 | 35 | 371 |

### Essential components that were broken, wrong, unproven or missing

| # | Component | Kind | Reliability | Status | v0.2 action |
|---|---|---|---|---|---|
| 1 | Mandatory verifiers (Reid, Quinn, Cyra, Verity, Maialen, Lysandra) | agent | broken | wrong | rework |
| 2 | /close | command | broken | wrong | rework |
| 3 | /wake | command | broken | wrong | rework |
| 4 | .tess/tess.lock framework pin | config | broken | wrong | rework |
| 5 | Release public key (.tess/keys/twiss-release-key.asc) | config | broken | wrong | rework |
| 6 | conductor/guardrails.md (18 rules; security tier) | doctrine | broken | wrong | rework |
| 7 | conductor/verification-routing.md (security tier) | doctrine | broken | wrong | rework |
| 8 | kb/ knowledge-base scaffold | doctrine | broken | outdated | rework |
| 9 | tessctl render | engine | broken | wrong | rework |
| 10 | tessctl rollback | engine | broken | wrong | rework |
| 11 | tessctl self-update | engine | broken | wrong | rework |
| 12 | tessctl update (signed OTA) | engine | broken | wrong | rework |
| 13 | Agency mode scaffold (clients/_template) | installer | broken | outdated | rework |
| 14 | Instance .gitignore (brain tracking) | installer | broken | wrong | rework |
| 15 | Python/PyYAML preflight (ensurePython3) | installer | broken | wrong | rework |
| 16 | writeProfile (operator/profile.json) | installer | broken | wrong | rework |
| 17 | Client brief template (clients/_template/CLAUDE.md) | instruction | broken | outdated | rework |
| 18 | Fragment: directory.md (directory tree + KB framework) | instruction | broken | wrong | rework |
| 19 | Fragment: session-memory.md (shared memory pointer) | instruction | broken | outdated | rework |
| 20 | .tess/state/memory/ shared memory store | other | broken | outdated | rework |
| 21 | CI: multi-runtime fresh-install smoke | ci | unproven | missing | add |
| 22 | Fresh-clone probe | ci | unproven | missing | add |
| 23 | Codex hook rendering (.codex/hooks.json) | config | unproven | missing | add |
| 24 | Gemini CLI support (.gemini/settings.json + GEMINI.md or context.fileName) | config | unproven | missing | add |
| 25 | MISSING: GEMINI.md entry / .gemini/settings.json context.fileName | config | unproven | missing | add |
| 26 | Decisions register | doctrine | unproven | missing | add |
| 27 | Learnings store (preferences, corrections, facts) with provenance + index budget | doctrine | unproven | missing | add |
| 28 | MISSING: Agency mode pack (clients as entities) | doctrine | unproven | missing | add |
| 29 | MISSING: Channel-agnostic notification doctrine | doctrine | unproven | missing | add |
| 30 | MISSING: Decisions register (template + rule) | doctrine | unproven | missing | add |
| 31 | MISSING: Learning-loop doctrine (always smarter, never wrong) | doctrine | unproven | missing | add |
| 32 | MISSING: Organisation mode pack | doctrine | unproven | missing | add |
| 33 | MISSING: Personal mode pack | doctrine | unproven | missing | add |
| 34 | MISSING: Save contract / File Placement Contract | doctrine | unproven | missing | add |
| 35 | START HERE per-entity index | doctrine | unproven | missing | add |
| 36 | Brain index budget + START HERE linter | engine | unproven | missing | add |
| 37 | Conversation capture (transcript ingestion) | engine | unproven | missing | add |
| 38 | Decision register + decision ledger event | engine | unproven | missing | add |
| 39 | Fresh-clone probe (tessctl probe + CI job) | engine | unproven | missing | add |
| 40 | Learning loop notes (preference / correction / fact / open loop) | engine | unproven | missing | add |
| 41 | MISSING: Memory index budget guard | engine | unproven | missing | add |
| 42 | Mode scaffolds (personal / agency / organisation + presets) | engine | unproven | missing | add |
| 43 | render target: gemini (GEMINI.md / .gemini/settings.json) | engine | unproven | missing | add |
| 44 | tessctl save (commit + push brain) | engine | unproven | missing | add |
| 45 | Conversation capture pipeline (every conversation noted) | hook | unproven | missing | add |
| 46 | MISSING: Mechanical conversation capture | hook | unproven | missing | add |
| 47 | MISSING: SessionStart unsaved-work warning | hook | unproven | missing | add |
| 48 | Memory index budget guard | hook | unproven | missing | add |
| 49 | SessionStart brain loader (START HERE, open loops, decisions, first-run onboarding trigger) | hook | unproven | missing | add |
| 50 | Unsaved-work status (tessctl status --unsaved) + SessionStart warning | hook | unproven | missing | add |
| 51 | Unsaved-work warn hook | hook | unproven | missing | add |
| 52 | In-session first-run onboarding (mode: personal / agency / organisation + presets) | installer | unproven | missing | add |
| 53 | Organisation mode scaffold | installer | unproven | missing | add |
| 54 | Personal mode scaffold | installer | unproven | missing | add |
| 55 | MISSING: @AGENTS.md import in CLAUDE.md (shared core for Claude) | instruction | unproven | missing | add |
| 56 | MISSING: First-run onboarding (in-session, every runtime) | instruction | unproven | missing | add |
| 57 | MISSING: Per-entity START HERE index template | instruction | unproven | missing | add |
| 58 | MISSING: Worker override for dispatched subagents | instruction | unproven | missing | add |
| 59 | .agents/skills/tess-* (commands as cross-runtime skills) | skill | unproven | missing | add |
| 60 | Brain skills: onboard / remember / decide / save / recall | skill | unproven | missing | add |
| 61 | MISSING: Cross-runtime command/skill port (.agents/skills + .gemini/commands) | skill | unproven | missing | add |
| 62 | First-run onboarding inside the agent session | workflow | unproven | missing | add |
| 63 | /feedback | command | unproven | outdated | rework |
| 64 | Internal KB skeleton (kb/wiki index/log, raw/, lint/) | doctrine | unproven | outdated | rework |
| 65 | conductor/channel-guardrails.md (security tier) | doctrine | unproven | outdated | rework |
| 66 | conductor/daily-operating-behavior.md | doctrine | unproven | outdated | rework |
| 67 | conductor/memory-model.md | doctrine | unproven | outdated | rework |
| 68 | Fragment: hard-floor.md (Doctrine Gates + Verification/Retry + Rule 18 floor) | instruction | unproven | current | rework |
| 69 | Instance .gitignore (template copy of the framework's) | config | proven | wrong | rework |
| 70 | tessctl approve | engine | proven | wrong | rework |
| 71 | tessctl memory adopt | engine | proven | wrong | rework |
| 72 | CLAUDE.md (entry doctrine) | instruction | proven | wrong | rework |

## 1. Instruction files (auto-loaded entry points and injected zones) (28)

Essential 15 / useful 7 / optional 5 / cut 1. Reliability P 7 / L 4 / U 12 / B 5.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action |
|---|---|---|---|---|---|---|---|---|---|---|
| Client brief template (clients/_template/CLAUDE.md) | `clients/_template/CLAUDE.md (source .tess/core/templates/clie...` | Loaded lazily when Claude reads files in that... | Never read: no AGENTS.md (or symlink) in the... | Never read | Never read | instruction | broken | essential | outdated | rework |
| Fragment: directory.md (directory tree + KB framework) | `.tess/core/templates/claude-md/directory.md` | Rendered into CLAUDE.md | n/a | n/a | n/a | instruction | broken | essential | wrong | rework |
| Fragment: session-memory.md (shared memory pointer) | `.tess/core/templates/agents-md/session-memory.md` | n/a (never shown to Claude | In AGENTS.md | n/a | In AGENTS.md | instruction | broken | essential | outdated | rework |
| Fragment: hard-floor.md (Doctrine Gates + Verification/Retry + Rule 18 floor) | `.tess/core/templates/claude-md/hard-floor.md` | Rendered into CLAUDE.md | Hard-floor portion delivered separately via w... | n/a | n/a (worker-hard-floor via AGENTS.md) | instruction | unproven | essential | current | rework |
| MISSING: @AGENTS.md import in CLAUDE.md (shared core for Claude) | (new) CLAUDE.md first line | Docs: import AGENTS.md with '@AGENTS.md'; nev... | n/a | n/a | n/a | mechanical | unproven | essential | missing | add |
| MISSING: First-run onboarding (in-session, every runtime) | (new) shared core in AGENTS.md + onboarding skill/command | Instruction in shared core (via @AGENTS.md) +... | AGENTS.md instruction + SessionStart hook in... | Loaded via context.fileName + SessionStart ho... | AGENTS.md instruction only | mixed | unproven | essential | missing | add |
| MISSING: Per-entity START HERE index template | (new) top section of every entity CLAUDE.md/AGENTS.md | Lazy-loaded with entity CLAUDE.md | Per-folder AGENTS.md | Via context.fileName | Per-folder AGENTS.md | instruction | unproven | essential | missing | add |
| MISSING: Worker override for dispatched subagents | (new) block in dispatch defs or omitClaudeMd:true | Docs: custom subagents load CLAUDE.md unless... | n/a | n/a | n/a | mechanical | unproven | essential | missing | add |
| CLAUDE.md (rendered conductor entry point) | `CLAUDE.md` | Auto-loaded at session start | n/a (Codex reads AGENTS.md/AGENTS.override.md... | n/a (Gemini default context file is GEMINI.md) | n/a | mixed | likely | essential | outdated | rework |
| AGENTS.md (rendered worker profile) | `AGENTS.md` | Not read by default because CLAUDE.md exists... | Auto-loaded git-root→cwd, 32 KiB default cap... | NOT loaded: default context file is GEMINI.md | Read natively per AGENTS.md convention (Curso... | mixed | proven | essential | outdated | rework |
| AGENTS.md (worker digest) | `AGENTS.md (render_agents_md, .tess/core/templates/agents-md/)` | Not read while CLAUDE.md exists (Claude docs... | Loaded natively (proven, 5,408 B < 32 KiB pro... | Only if .gemini/settings.json context.fileNam... | Loaded natively | instruction | proven | essential | outdated | rework |
| AGENTS.md.tpl (worker template) | `.tess/core/templates/agents-md/AGENTS.md.tpl` | n/a | Rendered by tessctl render --target codex (en... | n/a (no gemini target in RENDER_TARGETS) | Rendered by generic target (not enabled by de... | mechanical | proven | essential | outdated | rework |
| CLAUDE.md (entry doctrine) | `CLAUDE.md (rendered from .tess/core/templates/claude-md/*)` | Auto-loaded as project instructions (proven) | Not read (Codex reads AGENTS.md | Not read (Gemini reads GEMINI.md unless conte... | n/a | instruction | proven | essential | wrong | rework |
| CLAUDE.md.tpl (entry-point template) | `.tess/core/templates/CLAUDE.md.tpl` | Rendered to CLAUDE.md by tessctl render (clau... | n/a | n/a | n/a | mechanical | proven | essential | outdated | rework |
| Fragment: worker-hard-floor.md | `.tess/core/templates/agents-md/worker-hard-floor.md` | n/a (Claude gets hard-floor.md) | In AGENTS.md (loaded) | n/a until Gemini reads AGENTS.md | In AGENTS.md | instruction | proven | essential | current | keep |
| Fragment: rule-zero.md (Always dispatch, never execute solo) | `.tess/core/templates/claude-md/rule-zero.md` | Rendered to CLAUDE.md top | n/a (denylisted from AGENTS.md by test_worker... | n/a | n/a | mixed | unproven | useful | outdated | rework |
| Fragment: system-laws.md (7 System Laws table) | `.tess/core/templates/claude-md/system-laws.md` | Rendered into CLAUDE.md (always in context) | n/a | n/a | n/a | instruction | unproven | useful | outdated | rework |
| operator/user-profile.md (profile stub) | `operator/user-profile.md` | inject:false by default → renders empty | n/a | n/a | n/a | instruction | unproven | useful | outdated | rework |
| Fragment: commands.md (command table) | `.tess/core/templates/claude-md/commands.md` | Rendered into CLAUDE.md | n/a (Codex does not load project .codex/prompts | n/a (Gemini commands need .gemini/commands/*.... | n/a | instruction | likely | useful | outdated | rework |
| Fragment: gate-compliance.md (ship-gate facts) | `.tess/core/templates/agents-md/gate-compliance.md` | n/a | In AGENTS.md | n/a | In AGENTS.md | mixed | likely | useful | outdated | rework |
| Fragment: shared-tasks.md (cross-harness task board) | `.tess/core/templates/agents-md/shared-tasks.md` | n/a (not in CLAUDE.md) | In AGENTS.md | n/a | In AGENTS.md, but hardcodes --harness codex /... | mixed | likely | useful | outdated | rework |
| operator/identity-stub.md | `operator/identity-stub.md` | Injected into CLAUDE.md | n/a (not in AGENTS.md) | n/a | n/a | mechanical | proven | useful | current | keep |
| Fragment: harness-note.md (command mirrors note) | `.tess/core/templates/agents-md/harness-note.md` | n/a | In AGENTS.md | n/a | In AGENTS.md | instruction | broken | optional | wrong | rework |
| Fragment: orchestrators.md (Outcome Orchestrator Layer) | `.tess/core/templates/claude-md/orchestrators.md` | Rendered into CLAUDE.md | n/a (denylisted) | n/a | n/a | instruction | broken | optional | wrong | rework |
| operator/build-facts-stub.md | `operator/build-facts-stub.md` | n/a | inject:false → empty in AGENTS.md | n/a | inject:false | instruction | unproven | optional | current | keep |
| operator/org-channels.md (channel map stub) | `operator/org-channels.md` | inject:false → empty | n/a | n/a | n/a | instruction | unproven | optional | outdated | rework |
| Pathway personas (5: chief-of-staff, co-founder, strategist, guide, operator) | `.tess/core/personas/*.md` | Rendered into conductor/personality.md, which... | n/a (AGENTS.md has no persona) | n/a | n/a | instruction | unproven | optional | outdated | rework |
| starter/ third-party kit instructions (starter/CLAUDE.md, starter/global-clau... | `starter/` | starter/CLAUDE.md loads when Claude reads fil... | n/a | n/a | n/a | instruction | unproven | cut | outdated | cut |

## 2. Doctrine (conductor/, playbooks, KB and memory conventions) (63)

Essential 18 / useful 22 / optional 22 / cut 1. Reliability P 1 / L 4 / U 51 / B 7.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action |
|---|---|---|---|---|---|---|---|---|---|---|
| conductor/guardrails.md (18 rules; security tier) | `conductor/guardrails.md` | Not auto-loaded | Linked from AGENTS.md (Rule 18) | n/a | Linked from AGENTS.md | mixed | broken | essential | wrong | rework |
| conductor/verification-routing.md (security tier) | `conductor/verification-routing.md` | Not auto-loaded | Linked from AGENTS.md ship-gate | n/a | Linked from AGENTS.md | mixed | broken | essential | wrong | rework |
| kb/ knowledge-base scaffold | `kb/{raw,wiki/{concepts,missions,people,synthesis},lint}, kb/w...` | Read/write via tools | Same | Same | Same | instruction | broken | essential | outdated | rework |
| conductor/channel-guardrails.md (security tier) | `conductor/channel-guardrails.md` | Not auto-loaded | n/a | n/a | n/a | instruction | unproven | essential | outdated | rework |
| conductor/daily-operating-behavior.md | `conductor/daily-operating-behavior.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | essential | outdated | rework |
| conductor/memory-model.md | `conductor/memory-model.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | essential | outdated | rework |
| Decisions register | (missing) | decide skill + capture hook | skill + AGENTS.md rule | skill | AGENTS.md rule | mixed | unproven | essential | missing | add |
| Internal KB skeleton (kb/wiki index/log, raw/, lint/) | `kb/` | Read on demand | Not referenced by AGENTS.md | n/a | Not referenced | instruction | unproven | essential | outdated | rework |
| Learnings store (preferences, corrections, facts) with provenance + index budget | (missing) | remember skill + Stop/SessionEnd extraction q... | skill + hooks (trusted) | skill + hooks | Instruction only | mixed | unproven | essential | missing | add |
| MISSING: Agency mode pack (clients as entities) | (new) mode pack: agency | Subdirectory CLAUDE.md lazy load | Per-folder AGENTS.md (Codex walks git root→cwd) | GEMINI.md/AGENTS.md per folder via context.fi... | Per-folder AGENTS.md | instruction | unproven | essential | missing | add |
| MISSING: Channel-agnostic notification doctrine | (new) replaces chat-channel mandates | Instruction | Instruction | Instruction | Instruction | instruction | unproven | essential | missing | add |
| MISSING: Decisions register (template + rule) | (new) <entity>/decisions.md | Instruction | Same via AGENTS.md | Same | Same | instruction | unproven | essential | missing | add |
| MISSING: Learning-loop doctrine (always smarter, never wrong) | (new) conductor/learning-loop.md + shared core summary | Instruction + Stop hook nudge | Instruction + Stop hook (advisory) | Instruction + AfterAgent hook | Instruction only (model may forget) | mixed | unproven | essential | missing | add |
| MISSING: Organisation mode pack | (new) mode pack: organisation | Rendered tree + per-entity START HERE | Per-folder AGENTS.md | Via context.fileName | Per-folder AGENTS.md | instruction | unproven | essential | missing | add |
| MISSING: Personal mode pack | (new) mode pack: personal | Rendered tree + START HERE | Same via AGENTS.md | Same via context.fileName | Same via AGENTS.md | instruction | unproven | essential | missing | add |
| MISSING: Save contract / File Placement Contract | (new) shared core section | Instruction (via @AGENTS.md) | Instruction (AGENTS.md) | Instruction | Instruction | instruction | unproven | essential | missing | add |
| START HERE per-entity index | (missing) | Loaded via SessionStart + CLAUDE.md | Top of AGENTS.md | Via context file | Top of AGENTS.md | mixed | unproven | essential | missing | add |
| memory/ open-projects registry (README, registry.md, projects/EXAMPLE.md) | `memory/` | Not referenced by CLAUDE.md | Not referenced by AGENTS.md | n/a | Not referenced | mixed | likely | essential | outdated | rework |
| Client KB skeleton (kb/wiki index+log, lint-log, research/, branding/DESIGN.md) | `clients/_template/kb/, clients/_template/branding/DESIGN.md` | Files read on demand | Files read on demand | Files read on demand | Files read on demand | instruction | broken | useful | outdated | rework |
| conductor/hook-testing-protocol.md | `conductor/hook-testing-protocol.md` | Not auto-loaded | n/a (Claude-only content) | n/a | n/a | instruction | broken | useful | outdated | rework |
| agents/README.md (roster overview) | `agents/README.md` | Read on demand (whitelisted by dispatch-guard) | n/a | n/a | n/a | instruction | unproven | useful | current | keep |
| conductor/commands.md (command catalogue) | `conductor/commands.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | outdated | rework |
| conductor/dispatch-brief.md (security tier) | `conductor/dispatch-brief.md` | Not auto-loaded | Not referenced | n/a | Not referenced | mixed | unproven | useful | outdated | rework |
| conductor/doctrine.md (dependency gates, Simple Task Path) | `conductor/doctrine.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | outdated | rework |
| conductor/identity.md (rendered) | `conductor/identity.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | current | keep |
| conductor/mission-states.md | `conductor/mission-states.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | outdated | rework |
| conductor/output-framework.md (System Law) | `conductor/output-framework.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | current | keep |
| conductor/personality.md (rendered + active pathway) | `conductor/personality.md` | Not auto-loaded | n/a | n/a | n/a | instruction | unproven | useful | outdated | rework |
| conductor/README.md (doctrine index) | `conductor/README.md` | Not auto-loaded | Not referenced by AGENTS.md | n/a (nothing loads) | Not referenced | instruction | unproven | useful | outdated | rework |
| conductor/review-output-standards.md (System Law) | `conductor/review-output-standards.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | current | keep |
| conductor/subagent-failure-protocol.md | `conductor/subagent-failure-protocol.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | current | rework |
| conductor/user-profile.md | `conductor/user-profile.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | wrong | rework |
| conductor/verdict-signing.md | `conductor/verdict-signing.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | useful | wrong | rework |
| Eva hiring framework + portfolio (agents/eva/*, 9 files) | `agents/eva/` | Read by Eva subagent on demand | n/a | n/a | n/a | instruction | unproven | useful | current | keep |
| MISSING: Extra presets (candidates; research pending) | (new) presets | Preset overlays on a base mode | Same | Same | Same | instruction | unproven | useful | missing | defer |
| playbooks/founder-decision-memo.md | `conductor/playbooks/founder-decision-memo.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | useful | current | keep |
| conductor/vault.md | `conductor/vault.md` | Not auto-loaded | Not referenced | n/a | Not referenced | mixed | likely | useful | outdated | rework |
| conductor/vault.md | `conductor/vault.md (live only; absent from .tess/core/conductor)` | On demand | n/a | n/a | n/a | mixed | likely | useful | outdated | rework |
| memory/ open-projects registry (L1) | `memory/README.md, memory/registry.md, memory/projects/*.md` | Read on demand | Read on demand | Read on demand | Read on demand | mixed | likely | useful | current | keep |
| Conductor pathways (5 personas) | `.tess/core/personas/{chief-of-staff,co-founder,strategist,gui...` | Via rendered CLAUDE.md/personality.md | Not in AGENTS.md worker profile | n/a | n/a | mixed | proven | useful | current | keep |
| conductor/orchestra-model.md | `conductor/orchestra-model.md` | Not auto-loaded | Not referenced | n/a | Not referenced | mixed | broken | optional | wrong | rework |
| Chat-channel coupling (cross-cutting) | `CLAUDE.md, guardrails Rule 10, /wake /close /finalize /code-r...` | Instruction, plus hooks that don't reach the... | n/a | n/a | n/a | instruction | broken | optional | wrong | rework |
| client-experience-orchestrator.md (doctrine) | `conductor/outcome-orchestrators/client-experience-orchestrato...` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer |
| conductor/agent-lifecycle.md (System Law) | `conductor/agent-lifecycle.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | current | keep |
| conductor/cross-guild-coordination.md (System Law) | `conductor/cross-guild-coordination.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | current | defer |
| conductor/founders-office.md (System Law) | `conductor/founders-office.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | outdated | rework |
| conductor/mission-control.md | `conductor/mission-control.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | outdated | cut |
| conductor/outcome-orchestrators/integration.md (System Law) | `conductor/outcome-orchestrators/integration.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | current | defer |
| conductor/outcome-orchestrators/README.md | `conductor/outcome-orchestrators/README.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | current | defer |
| conductor/playbooks/README.md | `conductor/playbooks/README.md` | Read on demand (doctrine.md intake 'playbook... | n/a | n/a | n/a | instruction | unproven | optional | outdated | keep |
| conductor/soul.md | `conductor/soul.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | current | keep |
| founders-office-orchestrator.md (doctrine) | `conductor/outcome-orchestrators/founders-office-orchestrator.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer |
| Guild/governance docs (20 *-guild.md / *-governance.md / coding-team.md / int... | `agents/*.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer |
| operational-reliability-orchestrator.md (doctrine) | `conductor/outcome-orchestrators/operational-reliability-orche...` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer |
| playbooks/event-launch-orchestration.md | `conductor/playbooks/event-launch-orchestration.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer |
| playbooks/investor-fundraising-prep.md | `conductor/playbooks/investor-fundraising-prep.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer |
| playbooks/product-build-mission.md | `conductor/playbooks/product-build-mission.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer |
| playbooks/revenue-diagnosis.md | `conductor/playbooks/revenue-diagnosis.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer |
| product-delivery-orchestrator.md (doctrine) | `conductor/outcome-orchestrators/product-delivery-orchestrator.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer |
| revenue-orchestrator.md (doctrine) | `conductor/outcome-orchestrators/revenue-orchestrator.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer |
| Rule Zero dispatch discipline (cross-cutting) | `CLAUDE.md banner, guardrails Rule 1/1a, dispatch-guard.sh` | Instruction | Excluded by design from AGENTS.md | n/a | Excluded | instruction | unproven | optional | outdated | rework |
| strategic-growth-orchestrator.md (doctrine) | `conductor/outcome-orchestrators/strategic-growth-orchestrator.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | optional | outdated | defer |
| playbooks/l99-merge-discipline.md | `conductor/playbooks/l99-merge-discipline.md` | Read on demand | n/a | n/a | n/a | instruction | unproven | cut | wrong | cut |

## 3. Hooks (18)

Essential 7 / useful 6 / optional 1 / cut 4. Reliability P 4 / L 0 / U 10 / B 4.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action |
|---|---|---|---|---|---|---|---|---|---|---|
| Conversation capture pipeline (every conversation noted) | (missing) | Stop/SessionEnd/PreCompact provide transcript... | SessionEnd/Stop hooks (trusted) | SessionEnd/AfterAgent hooks | Instruction only ('append a session note') | mixed | unproven | essential | missing | add |
| Memory index budget guard | (missing) | PostToolUse on Write/Edit or SessionStart check | Same via hooks | Same via hooks | doctor check only | mechanical | unproven | essential | missing | add |
| MISSING: Mechanical conversation capture | (new) Stop/SessionEnd hooks per runtime → kb/conversations/YY... | Stop/SessionEnd hooks receive transcript_path... | Stop/SessionEnd hooks get transcript_path, wh... | SessionEnd/AfterAgent hooks exist (geminicli.... | n/a: instruction fallback only | mechanical | unproven | essential | missing | add |
| MISSING: SessionStart unsaved-work warning | (new) SessionStart hook for Claude/.codex/hooks.json/.gemini/... | SessionStart stdout added as context (docs) | SessionStart stdout added as developer contex... | SessionStart supports context injection (docs) | n/a | mechanical | unproven | essential | missing | add |
| SessionStart brain loader (START HERE, open loops, decisions, first-run onboa... | (missing) | SessionStart: plain stdout or additionalConte... | SessionStart hook via .codex/hooks.json (trus... | SessionStart hookSpecificOutput.additionalCon... | Instruction fallback in AGENTS.md: 'read STAR... | mixed | unproven | essential | missing | add |
| Unsaved-work status (tessctl status --unsaved) + SessionStart warning | (absent in tess-os) | Warn-only SessionStart hook | SessionStart hook | SessionStart hook | Instruction: run the CLI first | mixed | unproven | essential | missing | add |
| Unsaved-work warn hook | (missing) | SessionStart stdout | SessionStart hook | SessionStart JSON additionalContext | n/a | mechanical | unproven | essential | missing | add |
| anti-fabrication-guard.sh | `.claude/hooks/anti-fabrication-guard.sh` | Fires only with a dispatch lock | n/a | n/a | n/a | mechanical | broken | useful | wrong | rework |
| Codex hooks (.codex/hooks.json) | (absent) | n/a | Codex loads <repo>/.codex/hooks.json or [hook... | n/a | n/a | none | unproven | useful | missing | add |
| Gemini hooks (.gemini/settings.json hooks) | (absent) | n/a | n/a | Events: SessionStart, SessionEnd, BeforeAgent... | n/a | none | unproven | useful | missing | defer |
| Output-path / placement guard | (missing) | PreToolUse Write/Edit | PreToolUse apply_patch | BeforeTool | n/a | mechanical | unproven | useful | missing | defer |
| utc-local-context.sh | `.claude/hooks/utc-local-context.sh` | UserPromptSubmit, plain stdout reaches the mo... | n/a (not rendered | n/a (BeforeAgent would need JSON additionalCo... | n/a | mechanical | proven | useful | outdated | rework |
| vault-dispatch-scan.py | `.claude/hooks/vault-dispatch-scan.py (NOT in .tess/core/hooks...` | Blocks: exit 2 plus deprecated decision:block... | n/a (Codex PreToolUse covers spawn_agent | n/a | n/a | mechanical | proven | useful | outdated | rework |
| Chat-format guard hook | `.claude/hooks/` (chat-format guard) | Fires, but its rewrite is ignored | n/a | n/a | n/a | mechanical | broken | optional | wrong | cut |
| dispatch-guard.sh | `.claude/hooks/dispatch-guard.sh` | Fires on every main-session Bash/Edit/Write | n/a | n/a | n/a | mechanical | broken | cut | wrong | cut |
| PostToolUse Agent inline echo (chat nudge) | `.claude/settings.json PostToolUse matcher 'Agent'` | Fires | n/a | n/a | n/a | mechanical | broken | cut | wrong | cut |
| task-lock-clear.sh | `.claude/hooks/task-lock-clear.sh` | Fires | n/a | n/a | n/a | mechanical | proven | cut | outdated | cut |
| task-lock-set.sh | `.claude/hooks/task-lock-set.sh` | Fires | n/a | n/a | n/a | mechanical | proven | cut | outdated | cut |

## 4. Commands (30)

Essential 3 / useful 8 / optional 17 / cut 2. Reliability P 0 / L 19 / U 2 / B 9.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action |
|---|---|---|---|---|---|---|---|---|---|---|
| /close | `.claude/commands/close.md` | Registered | Not loaded | n/a | on request | instruction | broken | essential | wrong | rework |
| /wake | `.claude/commands/wake.md` | Registered | Not loaded | n/a | on request | instruction | broken | essential | wrong | rework |
| /feedback | `.claude/commands/feedback.md` | Registered | Not loaded | n/a | on request | instruction | unproven | essential | outdated | rework |
| /add-agent | `.claude/commands/add-agent.md` | Registered | Not loaded | n/a | on request | instruction | likely | useful | current | keep |
| /add-mission | `.claude/commands/add-mission.md` | Slash command registered (proven) | Not loaded (.codex/prompts dead) | n/a (needs .gemini/commands/*.toml) | prompts/add-mission.md on request | instruction | likely | useful | outdated | rework |
| /brainstorm | `.claude/commands/brainstorm.md` | Registered | Not loaded | n/a | on request | instruction | likely | useful | outdated | keep |
| /code-red | `.claude/commands/code-red.md` | Registered | Not loaded | n/a | on request | instruction | likely | useful | wrong | rework |
| /finalize | `.claude/commands/finalize.md` | Registered | Not loaded | n/a | on request | instruction | likely | useful | outdated | keep |
| /help | `.claude/commands/help.md` | Registered | Not loaded | n/a | on request | instruction | likely | useful | outdated | rework |
| /list-agents | `.claude/commands/list-agents.md` | Registered | Not loaded | n/a | on request | instruction | likely | useful | current | keep |
| /summary | `.claude/commands/summary.md` | Registered | Not loaded | n/a | on request | instruction | likely | useful | current | rework |
| .codex/prompts/*.md Codex command mirrors (26 files) | `.codex/prompts/` | n/a | Not discovered from the project | n/a | n/a | instruction | broken | optional | outdated | rework |
| /cx-mode | `.claude/commands/cx-mode.md` | Registered | Not loaded | n/a | on request | instruction | broken | optional | wrong | rework |
| /ops-mode | `.claude/commands/ops-mode.md` | Registered | Not loaded | n/a | on request | instruction | broken | optional | wrong | rework |
| /product-mode | `.claude/commands/product-mode.md` | Registered | Not loaded | n/a | on request | instruction | broken | optional | wrong | rework |
| /strategic-mode | `.claude/commands/strategic-mode.md` | Registered | Not loaded | n/a | on request | instruction | broken | optional | wrong | rework |
| prompts/*.md generic command mirrors (26 files) | `prompts/` | n/a | n/a | n/a (Gemini commands must be .gemini/commands... | Not auto-loaded | instruction | broken | optional | wrong | rework |
| prompts/ (generic mirrors) | `prompts/*.md` | n/a | Not auto-loaded | Not auto-loaded | Readable only if the model is told to open one | instruction | unproven | optional | outdated | cut |
| /founder-mode | `.claude/commands/founder-mode.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | rework |
| /remove-agent | `.claude/commands/remove-agent.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | keep |
| /reset | `.claude/commands/reset.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | keep |
| /revenue-mode | `.claude/commands/revenue-mode.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | rework |
| /review-mission | `.claude/commands/review-mission.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | outdated | rework |
| /route-mission | `.claude/commands/route-mission.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | cut |
| /show-active-guilds | `.claude/commands/show-active-guilds.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | cut |
| /show-next-moves | `.claude/commands/show-next-moves.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | cut |
| /show-owner | `.claude/commands/show-owner.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | cut |
| /show-risks | `.claude/commands/show-risks.md` | Registered | Not loaded | n/a | on request | instruction | likely | optional | current | cut |
| .codex/prompts/ (26 command mirrors) | `.codex/prompts/*.md` | n/a | NOT loaded: custom prompts are user-level ~/.... | n/a | n/a | none | broken | cut | wrong | cut |
| /initiate | `.claude/commands/initiate.md` | Registered | Not loaded | n/a | on request | instruction | likely | cut | outdated | cut |

## 5. Skills (10)

Essential 3 / useful 0 / optional 7 / cut 0. Reliability P 7 / L 0 / U 3 / B 0.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action |
|---|---|---|---|---|---|---|---|---|---|---|
| .agents/skills/tess-* (commands as cross-runtime skills) | (missing; manifest never_touch has .agents/) | n/a (Claude uses .claude/skills) | Discovers .agents/skills from cwd up to repo... | Workspace .agents/skills alias | Varies | instruction | unproven | essential | missing | add |
| Brain skills: onboard / remember / decide / save / recall | (missing) | .claude/skills | .agents/skills | .agents/skills | AGENTS.md pointers | instruction | unproven | essential | missing | add |
| MISSING: Cross-runtime command/skill port (.agents/skills + .gemini/commands) | (new) .agents/skills/<name>/SKILL.md; .gemini/commands/*.toml | n/a (.claude/commands/.claude/skills) | Codex scans .agents/skills from cwd up to rep... | Workspace skills .gemini/skills or .agents/sk... | n/a | instruction | unproven | essential | missing | add |
| 3d-web-experience skill | `.claude/skills/3d-web-experience/SKILL.md` | Registered (proven) | n/a (.agents/skills only) | n/a | n/a | instruction | proven | optional | wrong | cut |
| design-taste-frontend skill | `.claude/skills/design-taste-frontend/SKILL.md` | Registered (proven) | n/a | n/a | n/a | instruction | proven | optional | outdated | cut |
| full-output-enforcement skill | `.claude/skills/full-output-enforcement/SKILL.md` | Registered (proven) | n/a | n/a | n/a | instruction | proven | optional | current | defer |
| high-end-visual-design skill | `.claude/skills/high-end-visual-design/SKILL.md` | Registered (proven) | n/a | n/a | n/a | instruction | proven | optional | outdated | cut |
| industrial-brutalist-ui skill | `.claude/skills/industrial-brutalist-ui/SKILL.md` | Registered (proven) | n/a | n/a | n/a | instruction | proven | optional | outdated | cut |
| minimalist-ui skill | `.claude/skills/minimalist-ui/SKILL.md` | Registered (proven) | n/a | n/a | n/a | instruction | proven | optional | outdated | cut |
| redesign-existing-projects skill | `.claude/skills/redesign-existing-projects/SKILL.md` | Registered (proven) | n/a | n/a | n/a | instruction | proven | optional | outdated | cut |

## 6. Agents (subagent definitions and roster) (13)

Essential 1 / useful 3 / optional 9 / cut 0. Reliability P 0 / L 9 / U 3 / B 1.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action |
|---|---|---|---|---|---|---|---|---|---|---|
| Mandatory verifiers (Reid, Quinn, Cyra, Verity, Maialen, Lysandra) | `.tess/core/agents-dispatch/{reid,quinn,cyra,verity,maialen,ly...` | founders install: 0 of 6 | n/a | n/a | n/a | instruction | broken | essential | wrong | rework |
| Clio session scribe (dispatch def + persona) | `.tess/core/agents-dispatch/clio.md; agents/clio/README.md` | Dispatchable only if installed (operators pat... | n/a | n/a | n/a | instruction | unproven | useful | outdated | rework |
| eva (HR/crew design) | `.claude/agents/eva.md` | Subagent registered (proven) | n/a | n/a | n/a | instruction | likely | useful | current | keep |
| leah (Senior Researcher) | `.claude/agents/leah.md` | Subagent registered (proven in init agents list) | n/a (.codex/agents not rendered | n/a | n/a | instruction | likely | useful | current | keep |
| Persona prose specs + guild files (agents/ 165 entries, 3.2 MB; mirror .tess/... | `agents/<name>/{README,identity,personality,soul,capabilities}...` | Not auto-loaded | n/a | n/a | n/a | none | unproven | optional | current | defer |
| Roster persona prose specs (144 persona dirs, 736 files, 3.2 MB; mirrored in... | `agents/<name>/` | Read only on demand | n/a | n/a | n/a | instruction | unproven | optional | current | defer |
| apolline (Chief Sales) | `.claude/agents/apolline.md` | Subagent registered (proven) | n/a | n/a | n/a | instruction | likely | optional | current | keep |
| athena (Chief Strategy) | `.claude/agents/athena.md` | Subagent registered (proven) | n/a | n/a | n/a | instruction | likely | optional | current | keep |
| Benched orchestrators (4: product-delivery, client-experience, strategic-grow... | `.tess/core/agents-dispatch/*-orchestrator.md` | Only after recruit/path install | n/a | n/a | n/a | instruction | likely | optional | wrong | rework |
| Benched specialist roster (144 dispatch definitions) | `.tess/core/agents-dispatch/*.md (150 incl. 6 orchestrators; 1...` | Installed into .claude/agents via tessctl rec... | n/a | n/a | n/a | instruction | likely | optional | current | defer |
| founders-office-orchestrator | `.claude/agents/founders-office-orchestrator.md` | Subagent registered (proven) | n/a | n/a | n/a | instruction | likely | optional | current | keep |
| revenue-orchestrator | `.claude/agents/revenue-orchestrator.md` | Subagent registered (proven) | n/a | n/a | n/a | instruction | likely | optional | current | keep |
| zelie (Deck design) | `.claude/agents/zelie.md` | Subagent registered (proven) | n/a | n/a | n/a | instruction | likely | optional | current | keep |

## 7. Workflows (2)

Essential 1 / useful 0 / optional 1 / cut 0. Reliability P 0 / L 0 / U 2 / B 0.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action |
|---|---|---|---|---|---|---|---|---|---|---|
| First-run onboarding inside the agent session | (absent) | Bootstrap block at the top of CLAUDE.md, plus... | AGENTS.md bootstrap block, plus a .codex/hook... | AGENTS.md via context.fileName, plus a Gemini... | AGENTS.md bootstrap block only (instruction) | mixed | unproven | essential | missing | add |
| Saved workflows (.claude/workflows) | (none in tess-os) | Workflow tool only | n/a | n/a | n/a | mechanical | unproven | optional | missing | defer |

## 8. Config and state files (15)

Essential 10 / useful 5 / optional 0 / cut 0. Reliability P 5 / L 4 / U 3 / B 3.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action |
|---|---|---|---|---|---|---|---|---|---|---|
| .tess/tess.lock framework pin | `.tess/tess.lock` | Engine data | Engine data | Engine data | Engine data | mechanical | broken | essential | wrong | rework |
| Release public key (.tess/keys/twiss-release-key.asc) | `.tess/keys/twiss-release-key.asc` | Engine data | Engine data | Engine data | Engine data | mechanical | broken | essential | wrong | rework |
| Codex hook rendering (.codex/hooks.json) | (missing) | n/a | Hooks are on by default | n/a | n/a | mechanical | unproven | essential | missing | add |
| Gemini CLI support (.gemini/settings.json + GEMINI.md or context.fileName) | (missing) | n/a | n/a | Without it Gemini loads no Tess context (read... | n/a | mixed | unproven | essential | missing | add |
| MISSING: GEMINI.md entry / .gemini/settings.json context.fileName | (new) GEMINI.md or .gemini/settings.json | n/a | n/a | Default context file is GEMINI.md | n/a | mechanical | unproven | essential | missing | add |
| .claude/settings.json / settings-core.json (hook wiring) | `.claude/settings.json, .tess/core/settings-core.json` | Loaded | n/a | n/a | n/a | mechanical | proven | essential | outdated | rework |
| .tess/state/ cross-harness state root | `.tess/state/{memory,tasks,ledger,locks,skills,receipts}` | Via tessctl | Via tessctl (AGENTS.md pointers) | Via tessctl | Via tessctl | mechanical | proven | essential | outdated | rework |
| Instance .gitignore (template copy of the framework's) | `.gitignore; create-tess/template/.gitignore (identical)` | git (runtime-independent) | git | git | git | mechanical | proven | essential | wrong | rework |
| operator/profile.json | `operator/profile.json` | Read by tessctl render (not by the model) | Same (render input) | n/a | n/a | mechanical | proven | essential | outdated | rework |
| tess.manifest.json render_targets | `tess.manifest.json` | claude-code enabled | codex enabled (AGENTS.md, .codex/) | No gemini target exists in RENDER_TARGETS (.t... | generic not enabled (yet prompts/ ships) | mechanical | proven | essential | outdated | rework |
| missions/ records | `missions/<id>/` | Via tessctl mission | Same | Same | Same | mechanical | broken | useful | outdated | rework |
| .codex/config.toml | `.codex/config.toml` | n/a | Loaded only for a trusted project | n/a | n/a | mechanical | likely | useful | current | keep |
| codex-config.toml.tpl → .codex/config.toml | `.tess/core/templates/agents-md/codex-config.toml.tpl` | n/a | Loaded only when the project is trusted (Code... | n/a | n/a | mechanical | likely | useful | current | keep |
| core/policy/policy.yaml (ship-gate policy) | `core/policy/policy.yaml` | Enforced by tessctl gate via git hooks/CI (ru... | Same (git-level) | Same (git-level) | Same (git-level) | mechanical | likely | useful | current | keep |
| operator/ stubs | `operator/{profile.json,user-profile.md,identity-stub.md,org-c...` | Rendered into CLAUDE.md only when inject:true | Not in AGENTS.md | n/a | n/a | mechanical | likely | useful | outdated | rework |

## 9. Engine (tessctl subcommands, drivers, render targets, tools) (125)

Essential 29 / useful 65 / optional 31 / cut 0. Reliability P 87 / L 18 / U 13 / B 7.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action |
|---|---|---|---|---|---|---|---|---|---|---|
| tessctl render | `.tess/bin/tessctl:2841 cmd_render; _render_enabled_targets 2825` | Produces CLAUDE.md and settings.json, which C... | Produces AGENTS.md (loaded) and config.toml (... | Nothing rendered for Gemini | Produces AGENTS.md | mechanical | broken | essential | wrong | rework |
| tessctl rollback | `.tess/bin/tessctl:5323 cmd_rollback; _prune_snapshots 1566` | CLI | CLI | CLI | CLI | mechanical | broken | essential | wrong | rework |
| tessctl self-update | `.tess/bin/tessctl:6407 cmd_self_update` | CLI | CLI | CLI | CLI | mechanical | broken | essential | wrong | rework |
| tessctl update (signed OTA) | `.tess/bin/tessctl:4527 cmd_update` | CLI; doctrine references update --ref | CLI | CLI | CLI | mechanical | broken | essential | wrong | rework |
| Brain index budget + START HERE linter | (absent) | doctor check | doctor check (AGENTS.md size cap) | doctor check | doctor check | mechanical | unproven | essential | missing | add |
| Conversation capture (transcript ingestion) | (absent) | Stop/SessionEnd hook gets transcript_path | Stop/SessionEnd hook | SessionEnd hook transcript_path | Instruction only: the model must append a ses... | mixed | unproven | essential | missing | add |
| Decision register + decision ledger event | (absent) | CLI + /decide command + capture hook proposals | CLI + skill | CLI | CLI named in AGENTS.md | mixed | unproven | essential | missing | add |
| Fresh-clone probe (tessctl probe + CI job) | (absent) | Run headless (claude -p) against the clone | codex exec against the clone | gemini -p against the clone | n/a | none | unproven | essential | missing | add |
| Learning loop notes (preference / correction / fact / open loop) | (absent) | CLI + hook-proposed candidates | CLI | CLI | CLI (instruction) | mixed | unproven | essential | missing | add |
| MISSING: Memory index budget guard | (new) tessctl doctor check + SessionStart warn | Auto memory loads 'first 200 lines or 25KB' (... | AGENTS.md combined cap 32 KiB by default | Concatenates all context files | Tool-specific | mechanical | unproven | essential | missing | add |
| Mode scaffolds (personal / agency / organisation + presets) | (absent; clients/_template is the only entity template) | Files + CLAUDE.md START HERE | Files + AGENTS.md pointer | Files + AGENTS.md pointer | Files + AGENTS.md pointer | mechanical | unproven | essential | missing | add |
| render target: gemini (GEMINI.md / .gemini/settings.json) | (absent) | n/a | n/a | Without it a Gemini session in a Tess folder... | n/a | none | unproven | essential | missing | add |
| tessctl save (commit + push brain) | (absent) | CLI + /save | CLI + skill | CLI | CLI | mechanical | unproven | essential | missing | add |
| tessctl self-update | `.tess/bin/tessctl (cmd_self_update)` | CLI | CLI | CLI | CLI | mechanical | likely | essential | current | keep |
| tessctl update | `.tess/bin/tessctl (cmd_update)` | CLI | CLI | CLI | CLI | mechanical | likely | essential | current | keep |
| render target: claude-code | `.tess/bin/tessctl:2323 ClaudeCodeRenderTarget` | Auto-loaded CLAUDE.md plus .claude/* (hooks,... | n/a | n/a | n/a | mechanical | proven | essential | current | keep |
| render target: codex | `.tess/bin/tessctl:2397 CodexRenderTarget` | n/a | AGENTS.md is loaded natively (98 lines) | n/a | AGENTS.md | mechanical | proven | essential | outdated | rework |
| tessctl approve | `.tess/bin/tessctl:5763 cmd_approve` | CLI; any agent can run it | CLI | CLI | CLI | mechanical | proven | essential | wrong | rework |
| tessctl doctor | `.tess/bin/tessctl (cmd_doctor)` | CLI | CLI | CLI | CLI | mechanical | proven | essential | current | rework |
| tessctl doctor (incl. --fix, --publish-clean) | `.tess/bin/tessctl:3133 cmd_doctor; 3076 publish-clean` | CLI; referenced 5x in doctrine | CLI; pre-commit hook fires on git commit | CLI; git hook fires on commit | git hook fires on commit | mechanical | proven | essential | outdated | rework |
| tessctl gate | `.tess/bin/tessctl (cmd_gate: pre-commit/pre-push/ci/install-h...` | CLI + git hooks | Same (git hooks) | Same | Same | ci | proven | essential | current | keep |
| tessctl log append | `.tess/bin/tessctl:17136; LEDGER_EVENTS 15592` | CLI; not in CLAUDE.md | CLI (AGENTS.md) | CLI | CLI | mechanical | proven | essential | outdated | rework |
| tessctl mcp serve (MCP server) | `.tess/bin/tessctl:20158 _mcp_serve; tools 19780-19942` | Would load via .mcp.json, but none ships (.mc... | Would load via [mcp_servers] in .codex/config... | Would load via .gemini/settings.json mcpServers | Depends on the tool | mechanical | proven | essential | outdated | rework |
| tessctl memory adopt | `.tess/bin/tessctl:19563; DEFAULT_MEMORY_ADOPT_HARNESS 18703` | Default harness: ~/.claude/projects/<slug>/me... | 'no well-known default memory path for harnes... | Unsupported | Unsupported | mechanical | proven | essential | wrong | rework |
| tessctl render | `.tess/bin/tessctl (cmd_render, RENDER_TARGETS)` | Produces CLAUDE.md/settings | Produces AGENTS.md, .codex/prompts, config.toml | No target | generic target, not enabled by default | mechanical | proven | essential | outdated | rework |
| tessctl root shim + Python engine runtime | `tessctl; .tess/bin/tessctl (21,325 lines)` | Bash tool: ./tessctl <cmd> | shell (workspace-write sandbox) | shell tool, if the model knows to call it | shell where the tool has one | mechanical | proven | essential | current | rework |
| tessctl roster apply | `.tess/bin/tessctl:6741 _roster_apply` | Installs .claude/agents/*.md, which Claude Co... | No Codex agent equivalent rendered | No Gemini agent equivalent | n/a | mechanical | proven | essential | current | keep |
| tessctl verify | `.tess/bin/tessctl (cmd_verify)` | CLI | CLI | CLI | CLI | mechanical | proven | essential | current | keep |
| tessctl verify | `.tess/bin/tessctl:5475 cmd_verify` | CLI | CLI | CLI | CLI | mechanical | proven | essential | current | keep |
| tessctl capture | `.tess/bin/tessctl:3534 cmd_capture` | CLI | CLI | CLI | CLI | mechanical | broken | useful | wrong | rework |
| tessctl publish | `.tess/bin/tessctl:5117 cmd_publish` | CLI | CLI | CLI | CLI | mechanical | broken | useful | wrong | rework |
| tessctl rollback | `.tess/bin/tessctl (cmd_rollback)` | CLI | CLI | CLI | CLI | mechanical | broken | useful | wrong | rework |
| MCP brain tools + runtime registration | (absent) | .mcp.json (project scope) | [mcp_servers.tess] in the project config.toml... | mcpServers in .gemini/settings.json | Depends on the tool | mechanical | unproven | useful | missing | add |
| tessctl approve | `.tess/bin/tessctl (cmd_approve)` | CLI | CLI | CLI | CLI | mechanical | likely | useful | current | rework |
| tessctl capture | `.tess/bin/tessctl (cmd_capture)` | CLI | CLI | CLI | CLI | mechanical | likely | useful | current | keep |
| tessctl identity | `.tess/bin/tessctl (cmd_identity)` | CLI | CLI | CLI | CLI | mechanical | likely | useful | current | keep |
| tessctl init | `.tess/bin/tessctl (cmd_init)` | CLI via Bash | CLI via shell | CLI via run_shell_command | If the tool has a shell | mechanical | likely | useful | outdated | rework |
| tessctl override | `.tess/bin/tessctl (cmd_override)` | CLI | CLI | CLI | CLI | mechanical | likely | useful | current | keep |
| tessctl publish | `.tess/bin/tessctl (cmd_publish)` | CLI | CLI | CLI | CLI | mechanical | likely | useful | current | keep |
| tessctl reset | `.tess/bin/tessctl (cmd_reset)` | CLI | CLI | CLI | CLI | mechanical | likely | useful | current | keep |
| tessctl resolve | `.tess/bin/tessctl (cmd_resolve)` | CLI | CLI | CLI | CLI | mechanical | likely | useful | current | keep |
| tessctl validate | `.tess/bin/tessctl (cmd_validate)` | CLI | CLI | CLI | CLI | mechanical | likely | useful | current | keep |
| tessctl vault | `.tess/bin/tessctl (cmd_vault: init/set/get/list/rm/rotate/exe...` | CLI | CLI | CLI | CLI | mechanical | likely | useful | outdated | rework |
| core/contracts/*.schema.json + README (11 files) | `core/contracts/` | Used by tessctl validate/gate/run, not loaded... | Same (CLI) | Same (CLI) | Same (CLI) | mechanical | proven | useful | current | keep |
| tessctl bench | `.tess/bin/tessctl (cmd_bench)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl bench | `.tess/bin/tessctl:6939 cmd_bench` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl diff | `.tess/bin/tessctl:5405 cmd_diff` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl gate ci | `.tess/bin/tessctl:11539` | n/a (CI) | n/a (CI) | n/a (CI) | n/a (CI) | ci | proven | useful | current | keep |
| tessctl gate clear | `.tess/bin/tessctl:13349` | CLI; not referenced by CLAUDE.md, .claude/com... | CLI; not in AGENTS.md | CLI | CLI | mechanical | proven | useful | outdated | rework |
| tessctl gate install-hooks | `.tess/bin/tessctl:12088` | Run by create-tess activateGate | same | same | same | mechanical | proven | useful | outdated | rework |
| tessctl gate pre-commit | `.tess/bin/tessctl:11472` | Runs on any git commit (git hook, runtime-ind... | Same git hook | Same git hook | Same git hook | mechanical | proven | useful | current | keep |
| tessctl gate pre-push (ship-gate) | `.tess/bin/tessctl:11502` | git pre-push hook (runtime-independent) | Same git hook | Same git hook | Same git hook | mechanical | proven | useful | wrong | rework |
| tessctl init | `.tess/bin/tessctl:1829 cmd_init` | CLI via Bash | CLI via shell | CLI only | CLI only | mechanical | proven | useful | wrong | rework |
| tessctl lock | `.tess/bin/tessctl (cmd_lock)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl lock (--check / --regen) | `.tess/bin/tessctl:6231 cmd_lock` | CLI (maintainer) | CLI (maintainer) | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl log | `.tess/bin/tessctl (cmd_log append/view/verify)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | rework |
| tessctl log verify | `.tess/bin/tessctl:17187` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl log view | `.tess/bin/tessctl:17153` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl mcp serve | `.tess/bin/tessctl (cmd_mcp)` | Usable as an MCP server (not registered by de... | MCP supported (not registered) | MCP supported (not registered) | Where MCP is supported | mechanical | proven | useful | current | rework |
| tessctl memory adopt | `.tess/bin/tessctl (cmd_memory adopt/--revert)` | Symlinks ~/.claude/projects/<slug>/memory | Codex keeps its own ~/.codex/memories | n/a | n/a | mechanical | proven | useful | outdated | rework |
| tessctl mission | `.tess/bin/tessctl (cmd_mission new/status)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | outdated | rework |
| tessctl mission new | `.tess/bin/tessctl:13245` | CLI; /add-mission does not call it | CLI | CLI | CLI | mechanical | proven | useful | outdated | rework |
| tessctl mission status | `.tess/bin/tessctl:13275` | CLI; also MCP tool mission_status | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl pathway | `.tess/bin/tessctl (cmd_pathway)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl pathway | `.tess/bin/tessctl:7177 cmd_pathway` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl recruit | `.tess/bin/tessctl (cmd_recruit)` | Writes .claude/agents/<n>.md | No Codex agent output | n/a | n/a | mechanical | proven | useful | current | keep |
| tessctl recruit | `.tess/bin/tessctl:6858 cmd_recruit` | CLI; the /add-agent flow points to it | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl rename | `.tess/bin/tessctl (cmd_rename)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl rename | `.tess/bin/tessctl:7106 cmd_rename` | CLI; re-renders CLAUDE.md | Re-renders AGENTS.md and codex prompts | Nothing rendered | Re-renders AGENTS.md | mechanical | proven | useful | outdated | rework |
| tessctl reset | `.tess/bin/tessctl:5998 cmd_reset` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl restore | `.tess/bin/tessctl (cmd_restore)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl restore | `.tess/bin/tessctl:2077 cmd_restore` | CLI via Bash | CLI via shell | CLI only | CLI only | mechanical | proven | useful | wrong | rework |
| tessctl retry check | `.tess/bin/tessctl:13672` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl retry log | `.tess/bin/tessctl:13698` | CLI; not wired into doctrine | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl roster | `.tess/bin/tessctl (cmd_roster)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl roster list | `.tess/bin/tessctl:6814 _roster_list` | CLI | CLI | CLI | CLI | mechanical | proven | useful | outdated | rework |
| tessctl set-operator | `.tess/bin/tessctl (cmd_set_operator)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl set-operator | `.tess/bin/tessctl:7144 cmd_set_operator` | CLI | CLI | CLI | CLI | mechanical | proven | useful | outdated | rework |
| tessctl skill from-task | `.tess/bin/tessctl (cmd_skill)` | CLI; output not auto-loaded | CLI; output not auto-loaded | CLI | CLI | mechanical | proven | useful | outdated | rework |
| tessctl skill from-task | `.tess/bin/tessctl:18555` | CLI; the draft is not loaded until promoted | Draft not placed in .agents/skills | Not placed | n/a | mechanical | proven | useful | outdated | rework |
| tessctl tasks | `.tess/bin/tessctl (cmd_tasks new/set/claim/release/block/pull...` | CLI | CLI (AGENTS.md instructs its use) | CLI | CLI | mechanical | proven | useful | outdated | rework |
| tessctl tasks block | `.tess/bin/tessctl:16834` | CLI | CLI (AGENTS.md) | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl tasks new | `.tess/bin/tessctl:16519` | CLI; not in CLAUDE.md | CLI; the AGENTS.md Shared Tasks section refer... | CLI; no doctrine | CLI via AGENTS.md | mechanical | proven | useful | outdated | rework |
| tessctl tasks pull | `.tess/bin/tessctl:16893` | CLI | CLI (AGENTS.md: 'tasks pull --unclaimed') | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl tasks set | `.tess/bin/tessctl:16570` | CLI | CLI (AGENTS.md) | CLI | CLI (AGENTS.md) | mechanical | proven | useful | current | keep |
| tessctl validate | `.tess/bin/tessctl:9385 cmd_validate` | CLI; also exposed as MCP tool validate_contract | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl vault doctor | `.tess/bin/tessctl:8431` | CLI | CLI | CLI | CLI | mechanical | proven | useful | wrong | rework |
| tessctl vault exec | `.tess/bin/tessctl:8363` | CLI; referenced 6x in doctrine | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl vault init | `.tess/bin/tessctl:7693` | CLI; the vault-dispatch-scan.py PreToolUse ho... | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl vault scan | `.tess/bin/tessctl:8587` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl vault set | `.tess/bin/tessctl:8181` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl verdict | `.tess/bin/tessctl (cmd_verdict: keygen/sign/verify)` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl verdict sign | `.tess/bin/tessctl:9473` | CLI (human only by process) | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| tessctl verdict verify | `.tess/bin/tessctl:9584` | CLI | CLI | CLI | CLI | mechanical | proven | useful | current | keep |
| Memory-continuity heartbeat (L2) + launchd template | `scripts/heartbeat/*, scripts/heartbeat.sh, scripts/launchd/*....` | Spawns claude -p when activated | n/a | n/a | n/a | mechanical | unproven | optional | current | defer |
| run driver: codex (CodexExecDriver) | `.tess/bin/tessctl:14135` | n/a | Spawns codex exec | n/a | n/a | mechanical | unproven | optional | outdated | defer |
| run driver: gemini | `RUN_DRIVERS .tess/bin/tessctl:14348 = {claude, codex, fake}` | n/a | n/a | missing | n/a | none | unproven | optional | missing | defer |
| run driver: claude (ClaudeCliDriver) | `.tess/bin/tessctl:14058` | Spawns Claude Code headless | n/a | n/a | n/a | mechanical | likely | optional | current | defer |
| tessctl diff | `.tess/bin/tessctl (cmd_diff)` | CLI | CLI | CLI | CLI | mechanical | likely | optional | current | keep |
| tessctl override | `.tess/bin/tessctl:5249 cmd_override` | CLI | CLI | CLI | CLI | mechanical | likely | optional | outdated | keep |
| tessctl retry | `.tess/bin/tessctl (cmd_retry log/check/migrate)` | CLI | CLI | CLI | CLI | mechanical | likely | optional | current | keep |
| tessctl run | `.tess/bin/tessctl (cmd_run)` | Spawns claude | Spawns codex | No driver | n/a | mechanical | likely | optional | current | defer |
| tessctl trace | `.tess/bin/tessctl (cmd_trace export)` | CLI | CLI | CLI | CLI | mechanical | likely | optional | current | keep |
| render target: generic | `.tess/bin/tessctl:2471 GenericRenderTarget` | n/a | n/a | n/a | AGENTS.md shared with codex | mechanical | proven | optional | outdated | cut |
| run driver: fake (FakeDriver) | `.tess/bin/tessctl:14216` | n/a | n/a | n/a | n/a | mechanical | proven | optional | current | keep |
| tessctl audit | `.tess/bin/tessctl (cmd_audit export/verify)` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl audit export | `.tess/bin/tessctl:17741` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl audit verify | `.tess/bin/tessctl:17957` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl gate signoff sign / verify | `.tess/bin/tessctl:12106 / 12193` | CLI (maintainer) | CLI | CLI | CLI | mechanical | proven | optional | current | defer |
| tessctl gate-status | `.tess/bin/tessctl (cmd_gate_status)` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl gate-status | `.tess/bin/tessctl:13319` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl identity | `.tess/bin/tessctl:7053 cmd_identity` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl resolve | `.tess/bin/tessctl:5871 cmd_resolve` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl retry migrate | `.tess/bin/tessctl:13752` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl run (conductor loop) | `.tess/bin/tessctl:15403 cmd_run` | CLI; spawns claude -p workers | CLI; spawns codex exec workers | No Gemini driver | n/a | mechanical | proven | optional | current | defer |
| tessctl tasks claim | `.tess/bin/tessctl:16717` | CLI | CLI (AGENTS.md) | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl tasks handoff | `.tess/bin/tessctl:17066` | CLI | CLI | Not a valid target | n/a | mechanical | proven | optional | current | defer |
| tessctl tasks release | `.tess/bin/tessctl:16781` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl tasks render | `.tess/bin/tessctl:16946` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl trace export | `.tess/bin/tessctl:12739` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | defer |
| tessctl vault get | `.tess/bin/tessctl:8225` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl vault list | `.tess/bin/tessctl:8270` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl vault rm | `.tess/bin/tessctl:8295` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl vault rotate | `.tess/bin/tessctl:8311` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tessctl verdict keygen | `.tess/bin/tessctl:9643` | CLI | CLI | CLI | CLI | mechanical | proven | optional | outdated | rework |

## 10. Installer (create-tess) and scaffolds (29)

Essential 15 / useful 11 / optional 2 / cut 1. Reliability P 16 / L 0 / U 6 / B 7.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action |
|---|---|---|---|---|---|---|---|---|---|---|
| Agency mode scaffold (clients/_template) | `clients/_template/{CLAUDE.md,branding/DESIGN.md,kb/}` | Nested CLAUDE.md loads when working in the fo... | No AGENTS.md in template, so Codex never read... | Not read | Not read | instruction | broken | essential | outdated | rework |
| Instance .gitignore (brain tracking) | `.gitignore (framework copy inherited by instances)` | n/a | n/a | n/a | n/a | mechanical | broken | essential | wrong | rework |
| Python/PyYAML preflight (ensurePython3) | `create-tess/src/scaffold.js:89` | n/a | n/a | n/a | n/a | mechanical | broken | essential | wrong | rework |
| writeProfile (operator/profile.json) | `create-tess/src/keystone.js:41` | Read by the engine at render time | same | same | same | mechanical | broken | essential | wrong | rework |
| In-session first-run onboarding (mode: personal / agency / organisation + pre... | (missing) | SessionStart hook detects no profile, then on... | AGENTS.md first-run rule + SessionStart hook... | GEMINI/AGENTS context + SessionStart JSON | AGENTS.md first-run rule (instruction) | mixed | unproven | essential | missing | add |
| Organisation mode scaffold | (missing) | Files + START HERE | Same | Same | Same | instruction | unproven | essential | missing | add |
| Personal mode scaffold | (missing) | Files + START HERE | Same files | Same files | Same files | instruction | unproven | essential | missing | add |
| bake (roster apply, set-operator, rename, pathway, render) | `create-tess/src/keystone.js:100` | Renders CLAUDE.md | Renders AGENTS.md | Nothing | AGENTS.md | mechanical | proven | essential | current | keep |
| build-template + template-drift-guard (maintainer) | `create-tess/scripts/build-template.mjs; test/template-drift-g...` | n/a | n/a | n/a | n/a | ci | proven | essential | current | keep |
| check (doctor + verify after scaffold) | `create-tess/src/keystone.js:261` | n/a | n/a | n/a | n/a | mechanical | proven | essential | current | keep |
| create-tess entry (npx create-tess / npm create tess), bundled template | `create-tess/bin/create-tess.mjs; src/index.js main 225` | Produces the Claude surfaces | Produces AGENTS.md and .codex | Produces nothing for Gemini | Produces AGENTS.md | mechanical | proven | essential | current | keep |
| create-tess wizard (journey.js) | `create-tess/src/journey.js` | Terminal wizard, before any agent session | same | same | same | mechanical | proven | essential | outdated | rework |
| Policy key reset + regenPolicyLock | `create-tess/src/policy-reset.js; keystone.js:83` | n/a | n/a | n/a | n/a | mechanical | proven | essential | current | keep |
| Secrets-exclusion copy filter (ignore.js) | `create-tess/src/ignore.js:237, 312` | n/a | n/a | n/a | n/a | mechanical | proven | essential | current | keep |
| Template secrets exclusion (ignore.js) | `create-tess/src/ignore.js, pathnorm.js` | n/a | n/a | n/a | n/a | mechanical | proven | essential | current | keep |
| --force clean-replace + rollbackTarget | `create-tess/src/index.js:313, 332-338; scaffold.js:224-241` | n/a | n/a | n/a | n/a | mechanical | broken | useful | wrong | rework |
| Install detection (clobberReason) | `create-tess/src/scaffold.js:101-109` | n/a | n/a | n/a | n/a | mechanical | broken | useful | wrong | rework |
| Adopt an existing instance (tessctl adopt / create-tess --adopt) | (absent; planned) | n/a | n/a | n/a | n/a | none | unproven | useful | missing | add |
| Runtime selector at install (axis 6) | (absent) | n/a | n/a | n/a | n/a | none | unproven | useful | missing | add |
| activateGate (git init + install-hooks) | `create-tess/src/keystone.js:198` | git hooks | git hooks | git hooks | git hooks | mechanical | proven | useful | wrong | rework |
| Arrival card and first-push notice | `create-tess/src/index.js:164 printFirstPushNotice; printArrival` | Tells the user to run /add-mission (Claude sl... | Same text | Same | Same | instruction | proven | useful | wrong | rework |
| create-tess non-interactive flags (args.js) | `create-tess/src/args.js` | n/a | n/a | n/a | n/a | mechanical | proven | useful | outdated | rework |
| create-tess wizard (npm create tess) | `create-tess/src/journey.js, args.js` | Runs before any runtime (outside the agent se... | Same | Same | Same | mechanical | proven | useful | outdated | rework |
| git init + gate install-hooks | `create-tess/src/keystone.js` | n/a | n/a | n/a | n/a | mechanical | proven | useful | outdated | rework |
| Scaffold payload (what gets copied) | `create-tess/template/ (2,653 files)` | n/a | n/a | n/a | n/a | mechanical | proven | useful | outdated | rework |
| Template payload scope | `create-tess/template/ (built by scripts/build-template.mjs)` | n/a | n/a | n/a | n/a | mechanical | proven | useful | outdated | rework |
| --template-source / --template-ref git path | `create-tess/src/git-template-source.js:52` | n/a | n/a | n/a | n/a | mechanical | broken | optional | outdated | rework |
| Extra presets (software project; researcher/creator; student) | (builders/coding-squad path exists; others missing) | Preset squads + folders | Same | Same | Same | instruction | unproven | optional | missing | defer |
| Installer identity strings | `create-tess/src (install summary)` | n/a | n/a | n/a | n/a | none | proven | cut | wrong | rework |

## 11. CI and release gates (12)

Essential 7 / useful 4 / optional 1 / cut 0. Reliability P 6 / L 0 / U 5 / B 1.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action |
|---|---|---|---|---|---|---|---|---|---|---|
| CI: multi-runtime fresh-install smoke | (absent) | Would verify CLAUDE.md loads | Would verify AGENTS.md and skills | Would verify context.fileName | Would verify AGENTS.md | none | unproven | essential | missing | add |
| Fresh-clone probe | (missing) | claude -p in a fresh clone | codex exec (pin -m gpt-5.5: default gpt-6-ast... | gemini -p when installed | n/a | ci | unproven | essential | missing | add |
| CI: ci.yml | `.github/workflows/ci.yml` | n/a | n/a | n/a | n/a | ci | proven | essential | current | keep |
| CI: ci.yml create-tess job | `.github/workflows/ci.yml job create-tess` | n/a | n/a | n/a | n/a | ci | proven | essential | current | keep |
| CI: ci.yml secret-scan (gitleaks) | `.github/workflows/ci.yml job secret-scan` | n/a | n/a | n/a | n/a | ci | proven | essential | current | keep |
| CI: ci.yml tests job | `.github/workflows/ci.yml job test` | n/a | n/a | n/a | n/a | ci | proven | essential | current | keep |
| CI: tess-gate.yml | `.github/workflows/tess-gate.yml` | n/a | n/a | n/a | n/a | ci | proven | essential | current | keep |
| CI: release.yml | `.github/workflows/release.yml` | n/a | n/a | n/a | n/a | ci | broken | useful | wrong | rework |
| CI: publish-npm.yml | `.github/workflows/publish-npm.yml` | n/a | n/a | n/a | n/a | ci | unproven | useful | current | keep |
| MISSING: Fresh-clone probe (zero-context comprehension test) | (new) CI job / tessctl probe | Runtime-agnostic CI | Runtime-agnostic CI | Runtime-agnostic CI | Runtime-agnostic CI | ci | unproven | useful | missing | add |
| CI: CodeQL (GitHub default setup) | (GitHub default setup; no workflow file) | n/a | n/a | n/a | n/a | ci | proven | useful | current | keep |
| CI: tess-gate.yml installed into instances | `instance .github/workflows/tess-gate.yml (written by gate ins...` | n/a | n/a | n/a | n/a | ci | unproven | optional | wrong | rework |

## 12. Docs (8)

Essential 0 / useful 6 / optional 2 / cut 0. Reliability P 2 / L 1 / U 5 / B 0.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action |
|---|---|---|---|---|---|---|---|---|---|---|
| docs/MEMORY_AND_ORCHESTRATION_CONTRACT.md | `docs/MEMORY_AND_ORCHESTRATION_CONTRACT.md` | n/a | n/a | n/a | n/a | none | unproven | useful | outdated | rework |
| docs/STATE_LAYER.md + docs/memory-continuity.md | `docs/STATE_LAYER.md; docs/memory-continuity.md` | n/a | Referenced by AGENTS.md | n/a | Referenced by AGENTS.md | none | unproven | useful | current | keep |
| MISSING: Runtime capability matrix (honest reliability doc) | (new) docs/RUNTIMES.md | Documents CLAUDE.md/@import, hooks, subagents | Documents AGENTS.md 32 KiB, hooks.json trust,... | Documents GEMINI.md/context.fileName, hooks f... | AGENTS.md only | none | unproven | useful | missing | add |
| adapters/ + CONFORMANCE.md + manifests | `adapters/` | Claude C3 | Codex C2 | No row yet | Generic C2 | none | likely | useful | outdated | rework |
| adapters/manifests + CONFORMANCE | `adapters/manifests/*.adapter-manifest.json; adapters/CONFORMA...` | C3 preview | C2 | No manifest | generic C2 | none | proven | useful | outdated | rework |
| missions/README.md (mission records as code) | `missions/README.md` | Not referenced by doctrine/commands | Not referenced | n/a | Not referenced | mechanical | proven | useful | current | keep |
| .tess/core/MANIFEST.md | `.tess/core/MANIFEST.md` | n/a (maintainer doc) | n/a | n/a | n/a | none | unproven | optional | outdated | keep |
| conductor/release-process.md | `conductor/release-process.md` | Not auto-loaded | Not referenced | n/a | Not referenced | instruction | unproven | optional | current | rework |

## 13. Other repo content (18)

Essential 2 / useful 3 / optional 11 / cut 2. Reliability P 11 / L 4 / U 2 / B 1.

| Component | Path | CC | CX | GM | AM | Mechanism | Reliability | Essential | Status | v0.2 action |
|---|---|---|---|---|---|---|---|---|---|---|
| .tess/state/memory/ shared memory store | `.tess/state/memory/` | Only if tessctl memory adopt symlinks Claude... | Pointed to by AGENTS.md | n/a | Pointed to by AGENTS.md | mixed | broken | essential | outdated | rework |
| memory/ (project cards + registry.md) | `memory/projects/*.md; memory/registry.md` | Read if doctrine says so | Same | Same | Same | instruction | likely | essential | current | keep |
| proving-ground/ + gate-arena/ | `proving-ground/, gate-arena/` | n/a | n/a | n/a | n/a | ci | proven | useful | current | keep |
| scripts/heartbeat (memory-continuity heartbeat) + launchd | `scripts/heartbeat.sh; scripts/heartbeat/; scripts/launchd/` | Tier-2 synthesis spawns claude -p (model sonnet) | Not used | Not used | n/a | mechanical | proven | useful | outdated | rework |
| tools/validate_adapter_manifests | `tools/validate_adapter_manifests.py; adapter_manifest_validat...` | n/a (maintainer) | n/a | n/a | n/a | ci | proven | useful | current | keep |
| connectors/ registry | `connectors/registry/{anthropic,openai,gemini}` | n/a | n/a | n/a | n/a | none | unproven | optional | current | defer |
| gate-arena/ (gate bypass corpus) | `gate-arena/` | n/a | n/a | n/a | n/a | none | unproven | optional | outdated | cut |
| gui/ Mission Control dashboard | `gui/` | Spawns claude CLI | n/a | n/a | n/a | mechanical | likely | optional | current | defer |
| intent-router/ + spec-engine/ + orchestrator/ + telemetry/ (idea-to-app pipel... | `intent-router/, spec-engine/, orchestrator/, telemetry/, main.py` | Not wired to any runtime session | n/a | n/a | n/a | mechanical | likely | optional | current | defer |
| tools/receipt-emit, receipt-verify, adapter/AEC validators | `tools/` | n/a | n/a | n/a | n/a | mechanical | likely | optional | current | keep |
| connectors/validate_connector_manifests | `connectors/` | n/a | n/a | n/a | n/a | ci | proven | optional | current | keep |
| examples/receipt-demo + Makefile | `examples/receipt-demo/; Makefile` | n/a | n/a | n/a | n/a | mechanical | proven | optional | current | keep |
| proving-ground/ (benchmark harness) | `proving-ground/` | Claude driver | n/a | n/a | n/a | mechanical | proven | optional | outdated | cut |
| tools/receipt-emit | `tools/receipt-emit/` | CLI / orchestrator opt-in | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tools/receipt-verify | `tools/receipt-verify/` | CLI | CLI | CLI | CLI | mechanical | proven | optional | current | keep |
| tools/validate_aec_support_policy | `tools/validate_aec_support_policy.py` | n/a | n/a | n/a | n/a | ci | proven | optional | current | keep |
| main.py / pyproject stub | `main.py; pyproject.toml` | n/a | n/a | n/a | n/a | none | proven | cut | outdated | cut |
| orchestrator / intent-router / spec-engine / telemetry (idea-to-app codegen s... | `orchestrator/; intent-router/; spec-engine/; telemetry/ (69 f...` | n/a | n/a | n/a | n/a | mechanical | proven | cut | outdated | cut |

