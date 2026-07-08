# `missions/` — mission records as code

> Goal #5: `tessctl mission` + the typed-retry ledger. Spec:
> `docs/ULTIMATE_FRAMEWORK_PLAN.md` §C3 (Gate system module) + §C4 (Typed
> Retry module). Implementation: the **MISSION LEDGER** region of
> `.tess/bin/tessctl` (directly below `cmd_gate()`). Schemas:
> `core/contracts/mission.schema.json`, `core/contracts/retry.schema.json`.

This directory holds **per-project mission data** — it is not part of the
framework's own doctrine tree (`conductor/`, `core/`), and it is not
keystone-tracked (`missions/**` is in `tess.manifest.json`'s `never_touch`,
the same fenced-off treatment `kb/**` and `clients/*/**` already get; there
is no `.tess/core/missions/**` mirror — nothing here is rendered from core).
`tessctl restore`/`render`/`update` never touch it. It is created lazily,
the first time `tessctl mission new` runs.

## Why this exists

Two pieces of doctrine were previously **prose only** — true in principle,
unenforced in practice:

- **The five gates** (`conductor/doctrine.md` "The Gates" table): intake
  before anything, research before build, crew before deploy, review before
  synthesis, verification before externally-visible output. Nothing stopped
  a conductor from just... saying a gate had cleared.
- **The typed retry protocol** (`conductor/subagent-failure-protocol.md`):
  classify the failure, cap retries at 3, never retry with the same brief
  for a non-transient cause. Nothing stopped a conductor from silently
  retrying a 4th time, or re-dispatching the exact same brief and hoping for
  a different result.

This directory + `tessctl mission`/`gate-status`/`gate clear`/`retry` turns
both into **deterministic, file-backed checks**: a weak conductor (or a weak
agent it dispatches) cannot skip a gate or loop a failed retry if the tool
itself refuses to let it.

## Directory layout

```
missions/<id>/
├── mission.md         # front-matter + a short human body — the record's
│                       primary authored form
├── mission.json        # the SAME fields as mission.md's front-matter, as
│                       pure JSON — kept in sync automatically by every
│                       command that mutates the record (`gate clear`)
└── retries/
    ├── .gitkeep
    └── <task-slug>.attempt-<N>.md   # one file per logged retry attempt;
                                       # <task-slug> is the NORMALIZED task
                                       # (lowercase, kebab-cased) — see
                                       # "The typed-retry ledger's two
                                       # rules" below
```

`mission.md` and `mission.json` are **two serializations of the same
record**, both instances of `core/contracts/mission.schema.json` — either
one validates:

```bash
./tessctl validate mission missions/<id>/mission.md
./tessctl validate mission missions/<id>/mission.json
```

Every `retries/<task>.attempt-N.md` file is an instance of
`core/contracts/retry.schema.json`:

```bash
./tessctl validate retry missions/<id>/retries/<task>.attempt-1.md
```

**Reserved, not yet wired here:** `briefs/<task>.md` and
`verdicts/<task>.verdict.md` (docs/ULTIMATE_FRAMEWORK_PLAN.md's original
`missions/<id>/{plan.yaml, briefs/, returns/, verdicts/, record.md}`
sketch). `core/contracts/brief.schema.json` and `verdict.schema.json`
already exist and `tessctl validate brief|verdict <file>` already works
against a file at ANY path — what this build does NOT add is a command that
scaffolds those files under `missions/<id>/` automatically. That remains a
future Goal (C1/C2's CLI wiring, per the plan).

## Mission id

`tessctl mission new <name>` derives an id: `<YYYY-MM-DD>-<kebab-slug of
name>` (the same date-slug convention `~/.claude/rules/research.md`
mandates for research filenames, and the shape `orchestra-model.md` §3.1's
own worked example already uses — `2026-06-27-rev-conv-001`). A collision
appends a numeric suffix (`-2`, `-3`, ...).

## The five canonical gates

Reused **verbatim** from `crew-plan.schema.json`'s own `Stage.gate_in`
enum — one gate vocabulary across the whole system, not two:

| Gate string | Doctrine (`conductor/doctrine.md` "The Gates") |
|---|---|
| `intake-before-anything` | No node starts before the mission is framed |
| `research-before-build` | No strategy/team-design/execution on an unresearched information base |
| `crew-before-deploy` | No agent is briefed or activated before its role/mandate/boundaries are defined |
| `review-before-synthesis` | No synthesis is delivered on unreviewed outputs |
| `verification-before-externally-visible` | A verification node is a mandatory predecessor of any prod-touching/client-facing/externally-visible node |

Every mission record is seeded with all five, `cleared: false`, at
`mission new` time.

## Commands

```bash
# Scaffold + read
./tessctl mission new "Revenue conversation Q3 push"          # -> missions/2026-07-07-revenue-conversation-q3-push/
./tessctl mission new "..." --outcome-type build --by ada       # optional flags
./tessctl mission status <id>                                   # human-readable
./tessctl mission status <id> --json                            # machine-readable

# Gates
./tessctl gate-status <id>                                      # read-only report
./tessctl gate clear research-before-build --mission <id> --evidence path/to/leah-brief.md
                                                                  # REFUSES: missing --evidence,
                                                                  #          or --evidence that is
                                                                  #          missing, empty, a
                                                                  #          directory, or outside
                                                                  #          the repo

# Typed retry
./tessctl retry log <task> --mission <id> --cause context-gap \
    --failure-state degraded --brief path/to/attempt-2-brief.md
                                                                  # REFUSES (writes nothing):
                                                                  #   - a 4th attempt
                                                                  #   - a same-brief retry for a
                                                                  #     non-transient cause
./tessctl retry check <task> --mission <id>                     # cap-only check (no --cause/--brief)
./tessctl retry check <task> --mission <id> --cause context-gap --brief path/to/proposed-brief.md
                                                                  # full check — same decision
                                                                  # `retry log` would make, but
                                                                  # writes nothing either way
```

**`--mission <id>` is always explicit.** This CLI keeps no implicit
"current mission" state (no hidden state file, no CWD-based mission
discovery) — the same explicit-over-implicit posture `TESS_ROOT` and every
`tessctl validate <type> <file>` call already take. The task brief this
subsystem was built from showed `gate clear <gate> --evidence <path>` and
`retry log <task> --cause <type>` without a mission argument for brevity;
`--mission` was added as the (documented, not hidden) way these commands
know which mission's ledger to read/write.

## The typed-retry ledger's two rules

Both computed mechanically by `_retry_precheck()` in the MISSION LEDGER
region — never from the model's own say-so:

1. **The 3-attempt cap** (`subagent-failure-protocol.md` "Attempt Cap —
   3"). `retry check`/`retry log` count the attempt files already on disk
   for a task; a would-be 4th is blocked outright. The cap is keyed on a
   **normalized task slug** (`_retry_task_slug` — lowercase, whitespace/
   punctuation collapsed to `-`), not the caller's literal spelling, so a
   cosmetic rename (`deploy` vs `deploy ` vs `Deploy`) cannot reset the
   budget — the on-disk filename and the scan both use the same slug (a
   human-readable task label is still preserved in the attempt record's
   own `task` field/body).
2. **Same-brief retries are forbidden for every non-transient cause**
   (`subagent-failure-protocol.md`, cause-classification table). Each
   attempt file stores the VERBATIM `brief_text` used for that attempt (not
   just a path, since the live brief a path points at can change between
   attempts). A proposed attempt whose `--brief` file's content is a
   **literal** match — after collapsing all whitespace runs, not just
   trimming the ends — of **any prior attempt's** stored `brief_text` (not
   only the immediately preceding one, so an A -> B -> A ping-pong is
   still caught) is blocked — UNLESS `--cause transient` (an infrastructure
   hiccup is explicitly allowed a same-brief retry with backoff). This is a
   trivial-evasion guard, not a semantic diff — a genuine paraphrase of an
   old brief is not detected.

**`task` and `--mission <id>` are both constrained to safe values.** `task`
is normalized through the same kebab-slug alphabet (`[a-z0-9-]`) used for
mission ids, so it can never reach the filesystem as anything but a single
path component. `--mission <id>` is validated as exactly one path
component with no `..` before it is ever joined onto `root/missions/`, and
the resolved result is asserted to still be under `missions/` — belt and
suspenders against both a crafted `../`-bearing id and an absolute id
(`Path.__truediv__` silently discards everything to its left when joined
with an absolute right-hand side).

## Evidence discipline

`tessctl gate clear` mirrors `return-manifest.schema.json`'s own
artifact-existence discipline ("a file that must exist at a contracted
path either exists or doesn't"), tightened to: `--evidence <path>` must
point at a REAL, REGULAR, NON-EMPTY file, resolved relative to the Tess
root (not this process's CWD) and inside the repo. An empty file,
`/dev/null`, a bare directory, or a path outside the repo is refused with
the same explicit message discipline as a missing path — a gate cannot be
talked into "cleared" by an agent that simply asserts it, or by pointing
`--evidence` at something that technically "exists" but backs no real
claim. `tessctl validate mission <file>` (via `_lint_mission`) re-checks
the SAME rule against any mission record on disk, including one a human or
agent hand-edited outside the CLI — a `cleared: true` claim whose evidence
fails this check is schema/lint-invalid either way.
