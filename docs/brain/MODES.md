# Modes, presets and packs

Onboarding step 1 asks who the brain is for. The answer picks one or more
**modes**; step 2 may add a **preset**. This page defines both, lists what each
creates, and says why other use cases are presets or packs rather than modes.
See [ONBOARDING.md](ONBOARDING.md) for the interview and
[SECOND_BRAIN.md](SECOND_BRAIN.md) for the always-on layer every mode shares.

## The mode test

A use case gets its own mode only if it changes at least one of:

1. **the principal**: one person, a firm serving outside clients, or an
   institution with internal roles;
2. **the isolation boundary**: none, hard per client, or role-based;
3. **the writer model**: one writer, a few, or many with roles.

Anything else is a **preset** (template data on top of a mode) or a **pack**
(addable at any time). Research into common uses of frontier assistants
(practical guidance, information seeking, writing, planning, operations,
content, software, research) found none that passes the test beyond the
three modes below, and found the personal share of use large enough that the
personal operator layer (profile, decisions, loops, journal) is always on.

## The three modes

| Mode | Principal | Isolation | Entity roots (`brain.json`) |
|---|---|---|---|
| personal | one person | none between areas; health and money bodies in `brain/.private/` | `brain/life`, `brain/life/areas/*`, `brain/life/projects/*` |
| agency | a firm serving outside clients | hard, per client | `brain/agency`, `brain/clients/*` |
| organisation | an institution with internal roles | role-based | `brain/org`, `brain/org/units/*`, `brain/org/clients/*` |

### Presets (v0.2.0)

| Preset | Base mode | Adds |
|---|---|---|
| `startup` | organisation | 1-10 people: seats `founder-ceo`, `product`, `growth`, `operations`; this quarter's priorities page; a 5-row scorecard; an investors pointer page; suggests the `founders` squad |
| `solo-consultant` | agency | a team of one: `agency/proposals/`, a pipeline page and a rate card in `pricing.md`; suggests the `operators` squad |

### Later

| Kind | Items | Base | When |
|---|---|---|---|
| Preset | researcher (citation and provenance lint), creator (voice and publishing pipeline) | personal | v0.2.1 |
| Pack | codebase; health; money; sales, support and product desks; telegram; per-client repositories | any | v0.2.1+ |
| Backlog | household, nonprofit, student, investor | | on demand |
| Non-goal | companion or therapy use | | never: measured demand is small and assistant sycophancy is highest in those domains |

## Hybrids

`brain.json.modes` is a list, primary first ("agency and personal" is fine).
All mode roots sit side by side under `brain/` and `START-HERE.md` lists every
entity. Work inside one entity never reads another entity's
`privacy: limited` files unless the task names both.

Add a mode later with `python3 scripts/brain/onboard.py add-mode <mode> --quote "..."`.
It creates the new mode's base entity, records a decision with the operator's
words, and never moves or renames anything that exists.

## What each mode creates

Every entity folder holds an `AGENTS.md` that starts with `# START HERE: <name>`
(at most 100 lines and 6 KiB), plus two one-line shims so every runtime finds
it: `CLAUDE.md` containing `@AGENTS.md` and `GEMINI.md` containing
`@./AGENTS.md`. No symlinks, so the tree works on every OS and in every editor.

Always (the core):

```
brain/brain.json  brain/START-HERE.md  brain/probe.json  brain/tombstones.txt
brain/profile.md  brain/learned.md  brain/open-loops.md        (generated)
brain/decisions/{INDEX.md,ALL.md}                               (generated)
brain/decisions/D-<YYYYMMDD-HHMM>-brain-mode.md                 (first decision)
brain/{facts,inbox,index,journal,loops,profile,reviews,skills-drafts,archive}/
brain/kb/{raw,research,wiki}/
brain/.private/                                                 (local only)
memory/projects/                                                (state cards)
```

Personal (example answers: areas work, home, learning, health, money; two projects):

```
brain/life/{AGENTS.md,CLAUDE.md,GEMINI.md,routines.md}
brain/life/{areas,projects,people,resources,archive}/
brain/life/areas/<area>/{AGENTS.md,CLAUDE.md,GEMINI.md}
brain/life/areas/{health,money}/AGENTS.md      pointer only; the body lives in brain/.private/areas/<area>/
brain/life/projects/<project>/{AGENTS.md,CLAUDE.md,GEMINI.md}   goal, done when, status, next action, due
```

Agency (example: solo-consultant preset, two clients):

```
brain/agency/{AGENTS.md,CLAUDE.md,GEMINI.md,services.md,pricing.md,pipeline.md,team.md}
brain/agency/{sops,people,proposals}/
brain/clients/<client>/{AGENTS.md,CLAUDE.md,GEMINI.md,contacts.md,repos.md}
brain/clients/<client>/{projects,meetings}/
brain/clients/<client>/kb/{raw,research,wiki}/
brain/clients/<client>/brand/{current,staging,archive}/
brain/clients/<client>/admin/README.md         pointers only: where contracts, SOWs and invoices live
```

Organisation (example: startup preset, two units):

```
brain/org/{AGENTS.md,CLAUDE.md,GEMINI.md,direction.md}
brain/org/seats/<seat>.md                      one holder per seat
brain/org/units/<unit>/{AGENTS.md,CLAUDE.md,GEMINI.md}
brain/org/{people,clients,vendors,processes,policies,meetings,onboarding,kb}/
brain/org/metrics/scorecard.md  brain/org/priorities/<YYYY-Qn>.md  brain/org/cadence/README.md
brain/org/investors/README.md                  (startup preset)
```

The exact file lists for the three test fixtures are in
`tests/fixtures/brain_oobe/expected-tree-*.txt`.

## Adding entities later

`python3 scripts/brain/onboard.py add <kind> "<name>"`:

| Mode | Kinds |
|---|---|
| personal | `area`, `project`, `person` |
| agency | `client`, `project` (with `--in <client-slug>`), `person` |
| organisation | `unit`, `seat`, `person`, `client` |

The index row (in `START-HERE.md` for entities, in the parent `AGENTS.md` for
cards) is written before the files, so a half-finished add is still reachable.
Existing paths are reported `skipped (exists)` and left byte-for-byte alone.

## Naming

Organisation mode uses plain, generic names: seat chart, direction page,
quarterly priorities, scorecard, weekly leadership meeting, issues list. Tess OS
does not use the trademarked vocabulary of any management system, and it does
not use numbering schemes whose documentation is licensed for non-commercial
use only.
