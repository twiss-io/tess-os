# The Proving Ground

> Spec: `docs/ULTIMATE_FRAMEWORK_PLAN.md` §C9 ("The Proving Ground") and
> Phase 3 acceptance ("the report exists with real numbers; README claims
> are regenerated from it"). Sequencing rationale, same document: "Proving
> Ground before any marketing claim (the repo's own evidence rule)."

> **UPDATE (2026-07-08) — the test described below has been run, twice,
> and the thesis it was built to test did not hold.** See
> `reports/2026-07-07.md` (Run 1, tasks 01–10) and
> `reports/2026-07-07-fair.md` (Run 2 — FAIR, tasks 11–19, harder
> discriminating tasks, dispatch-guard friction fixed). Headline: across
> 19 tasks and ~80 trials, `weak+tess-os` never beat `weak+bare`, lost to
> it by 11.1 points in the fair run (8/9 vs 9/9, n=9 — too small a sample
> for a rate; directional, not a precision claim), and cost 1.7–2.7× more
> in every mounted-doctrine cell measured. Every `bare` cell in both runs
> ran with `--allow-impure-bare` (no `ANTHROPIC_API_KEY` in this build
> environment — see "Known limitation" below); read "bare" as "bare,
> approximately," not a stripped baseline. The sections below (written before
> either run) are kept as the harness's original design spec; where they
> describe the pitch as an open question, treat that as historical —
> the "Central pitch, corrected" section right below is the current
> status.

## Central pitch, corrected

Tess OS's central pitch *was* structure-as-enhancement — the claim that
mounting this repo's doctrine into a model's context would let a
lower-tier model close the gap to a higher-tier model's verified output
quality. This harness tested that pitch on 2026-07-07 (twice) and
disproved it: see `reports/2026-07-07.md` and
`reports/2026-07-07-fair.md`. The pitch is now **enforcement**, stated at
the grain it actually operates: the ship-gate (`tessctl gate`) means a
change to a policy-flagged path cannot ship without a signed covering
verdict, at git/CI, provided CI runs as a required check from a trusted
engine — the producing agent's quality is irrelevant within that scope;
this harness's standing jobs are the two below, not the thesis test.

It does three jobs — the first is answered, not open:
1. ~~**The thesis test.** Does `weak model + tess-os scaffold` approach or
   beat `strong model + bare harness` on this suite?~~ **Answered:** no —
   see the reports. This job is retired.
2. **Regression CI for doctrine payloads.** Any edit to `conductor/` or
   `.claude/` — or, going forward, any per-render-target doctrine
   profile — is checked against the same suite before it ships, and must
   show a non-negative pass-rate delta at that payload size.
3. **The enforcement arena** (planned, not yet built) — the honest
   demonstration of what the gate actually claims at its real grain: that
   a change to a policy-flagged path cannot ship without a signed
   covering verdict, at git/CI, provided CI runs as a required check from
   a trusted engine. Its output will be a measured bad-ship-rate
   reduction from gate + verifier, replacing the retired thesis-test job
   as the harness's headline number — no such number exists yet; this job
   has not been run.

Kept, inverted: **a real number beats an adjective — including when the
number is bad.** That principle is why jobs 2 and 3 above exist, and why
this update note is at the top of the file instead of a quiet edit
further down.

## What's here

```
proving-ground/
├── README.md                (this file)
├── REPORT-template.md       the ONLY template a real report is rendered from
├── grade.py                 deterministic grader CLI — one task, one workdir, pass/fail
├── run.py                   the matrix runner (4 cells x N tasks x up to --max-attempts)
├── pg_lib/                  the harness's internals (manifest loading, grading engine,
│                            scaffold mounting, the claude -p subprocess driver, report
│                            aggregation/rendering) — see docstrings in each module
├── tasks/                   19 seeded tasks — see tasks/README.md for the manifest contract
├── tests/                   pytest suite: unit-tests every grader + the dry-run + the CLI
├── reports/                 the two committed, generated-from-run reports (2026-07-07,
│                            2026-07-07-fair) — the actual evidence, not a template
└── results/                 generated run output (gitignored — see .gitignore)
```

## Quickstart

```bash
# 1. Validate the whole harness — zero cost, no claude subprocess invoked.
python proving-ground/run.py --dry-run

# 2. Unit-test every grader against crafted "known good" / "known bad" fixtures.
#    (pytest + PyYAML are already this repo's own requirements-dev.txt — nothing new to install.)
python -m pytest proving-ground/tests/ -v

# 3. A single, cheap, real cell — proves the claude -p pipeline end-to-end.
#    (see "What's actually been run" below for the real numbers from building this)
python proving-ground/run.py \
  --tasks 01-bug-average-empty-list --models weak --scaffolds bare \
  --max-attempts 1 --max-budget-usd 0.25 --allow-impure-bare
```

`proving-ground/tests/` is intentionally NOT under this repo's root
`pytest.ini` `testpaths` (that points at the top-level `tests/`, the
tessctl engine suite) — running it needs the explicit path shown above.
`pytest.ini`'s `testpaths` only takes effect when pytest is invoked with
no path arguments, so this never collides with the existing CI job.

## The matrix

A **cell** is one `(model tier, scaffold)` combination — four total:

| | `bare` | `tess-os` |
|---|---|---|
| **weak model** | unassisted cheap/fast model | cheap/fast model + this repo's doctrine |
| **strong model** | unassisted frontier model | frontier model + this repo's doctrine |

`bare` copies nothing into the workdir beyond the task's own fixture.
`tess-os` additionally mounts this repo's `CLAUDE.md`, `conductor/`,
`agents/`, `.claude/`, and `core/` verbatim — the real governance surface,
unmodified (see `pg_lib/scaffolds.py`). It deliberately excludes `.tess/`
(the upgrade engine): the doctrine itself says a fresh clone works without
it, and this harness must never depend on `.tess/bin/tessctl` at all.

Each cell runs against every selected task, up to `--max-attempts`
attempts (default 3, matching the framework's own retry-protocol cap),
stopping at first pass. The report's three headline numbers per cell:
**verified pass rate**, **total cost (USD)**, **mean attempts-to-pass**.

## The task suite (19 tasks)

See `tasks/README.md` for the full manifest contract and anti-cheat
design. Tasks 01–10 are the original suite; 11–19 are the **harder,
discriminating** tasks (added 2026-07-07) built specifically so a *bare*
model — especially the weak tier — produces confident-but-wrong output
that fails a deterministic grader, where a verify-first / check-the-edge /
adversarial-test approach would pass. See "Why the harder tasks
discriminate" below.

| # | id | category | what it tests |
|---|---|---|---|
| 01 | `01-bug-average-empty-list` | bug | fix a `ZeroDivisionError`, don't touch the failing test |
| 02 | `02-bug-pagination-off-by-one` | bug | fix an off-by-one slice bound |
| 03 | `03-feature-token-bucket-ratelimiter` | feature | implement to spec, graded by a hidden test suite |
| 04 | `04-feature-csv-dedupe` | feature | implement to spec, graded by a hidden test suite |
| 05 | `05-research-roster-facts` | research | extract facts from a synthetic doc corpus; one fact is deliberately absent (must answer "unknown", not fabricate) |
| 06 | `06-research-log-analysis` | research | compute exact counts/averages from a synthetic access log |
| 07 | `07-trap-tenant-isolation` | **trap** | implement tenant-scoped data access without a cross-tenant leak |
| 08 | `08-trap-sql-injection` | **trap** | implement a search function without SQL injection (the vulnerable pattern is shown as a "teammate's draft" in the brief) |
| 09 | `09-bug-duplicate-charge-idempotency` | bug | fix a payment processor that double-charges on retry |
| 10 | `10-feature-pagination-contract` | feature | implement to a machine-readable contract; graded against the grader's own independent reference implementation, not just the disclosed examples |
| 11 | `11-bug-rounding-half-up` | bug | currency rounding: `round()` uses banker's rounding and fails on ties; a decoy test (no ties) passes against it |
| 12 | `12-bug-csv-quoted-fields` | bug | parse a CSV line: `line.split(",")` passes the quote-free decoy test but mangles quoted fields containing commas |
| 13 | `13-feature-code-exact-match` | feature | validate an exact 4-digit code: `re.match` over-accepts `"12345"`, and `re.match(...$)` accepts a trailing newline |
| 14 | `14-feature-dedupe-case-insensitive` | feature | dedupe emails case-insensitively, order-preserving, keep first casing — three clauses a one-liner breaks |
| 15 | `15-research-cascading-billing` | research | **cascading** multi-step compute; "busiest month" is by row count, not revenue — a wrong intermediate corrupts every field |
| 16 | `16-trap-path-traversal` | **trap** | read a note by name from a flat dir; the obvious `os.path.join`+`open` leaks `../secret.txt` (risk not announced) |
| 17 | `17-trap-mass-assignment` | **trap** | apply a profile update to editable fields only; `user.update(updates)` lets `is_admin` through (risk not announced) |
| 18 | `18-bug-idempotency-retry-after-failure` | bug | idempotent charge that records the key *before* the charge succeeds, so a failed attempt is never retried |
| 19 | `19-feature-discount-spec` | feature | discount with three buried constraints: floor (not round), reject out-of-range percent, return an int |

Every category the mission requires is covered (bug, feature, research,
trap), with four planted traps (07, 08, 16, 17) rather than the minimum
one.

### Why the harder tasks discriminate (bare fails, verification catches)

The original 10 tasks *announce their own traps* — the brief names the
exact edge case, or a failing test spells out the requirement — so a
capable model, even the weak one, just does what it's told (the
2026-07-07 run scored both bare cells at 100%). The 11–19 tasks are
designed so the **plausible first thing a bare model writes is wrong**,
and the visible signal (disclosed examples, or a shipped decoy test that
passes against the naive code) points the wrong way:

- **Subtle bug / confident-wrong** (11, 12, 13, 18): the obvious
  implementation (`round()`, `line.split(",")`, `re.match`, record-before-
  charge) passes the decoy/disclosed cases and fails a held-out edge the
  grader checks. A verify-first agent that tests the boundary (a tie, a
  quoted comma, `"12345"`, a failing `charge_fn`) catches it.
- **Cascading** (15): a wrong step-1 intermediate corrupts every
  downstream number; verifying each intermediate before combining catches
  it, a one-shot doesn't.
- **Security/correctness traps** (16, 17): the brief does not mention
  "security"; the happy path works; only an adversarial input (`../`
  traversal, an `is_admin` in the update) reveals the hole.
- **Spec-adherence** (13, 14, 19): the discriminating requirement is a
  clause the disclosed examples don't exercise (full anchoring, case-
  insensitive+first-casing, floor+range-validation+int) — a careful,
  checked reading honors it; a skim misses it.

All 11–19 graders are **data-driven** (import the module, compare against a
reference the grader holds, run adversarial inputs) or pinned-`answer_key`
JSON — there is no test file in the workdir to hijack, and every grader is
unit-tested with a correct impl (must PASS), the naive/plausible-wrong impl
(must FAIL), and a no-op/hardcode cheat (must FAIL). See
`tests/test_graders_new_*.py`.

## Verified against a real `claude -p` invocation

Built and checked interactively against a real `claude` 2.1.201 install
(not assumed from documentation alone):

- `--output-format json` returns a JSON array of stream events; the last
  `"type": "result"` event carries `total_cost_usd`, `is_error`, `result`
  (final text), `num_turns`, `duration_ms`, `session_id` — this is
  exactly what `pg_lib/claude_driver.py` parses, and
  `tests/test_claude_driver_parsing.py` locks in the contract using the
  real captured payloads (trimmed) from both calls below.
- `--model haiku` resolved to `claude-haiku-4-5-20251001` and ran under
  the existing OAuth session (no `ANTHROPIC_API_KEY` needed) — a real
  "reply with the single word OK" turn cost **$0.0165** (`total_cost_usd`
  from the actual response), driven almost entirely by loading this
  repo's own ambient Claude Code context (plugins, skills, tool list) —
  which is exactly why that mode is NOT used as this harness's `bare`
  condition (see next point).
- `--bare` (true harness isolation — skips hooks, plugin sync, and
  CLAUDE.md auto-discovery) explicitly requires `ANTHROPIC_API_KEY` or an
  `apiKeyHelper`; it never reads OAuth/keychain auth. Confirmed live:
  without that key set, a `--bare` call fails **instantly**, with
  `"error": "authentication_failed"` and `"total_cost_usd": 0` — zero
  spend, fails before any request goes out. `pg_lib.claude_driver.
  bare_mode_available()` checks for this precondition up front so `run.py`
  can skip (or, with `--allow-impure-bare`, clearly flag) bare-scaffold
  cells rather than silently running a contaminated baseline.

## Known limitation: what "bare" means without an API key

This build environment has no `ANTHROPIC_API_KEY` configured (only OAuth
session auth, as used by this very session). That means:

- **`tess-os`-scaffold cells run cleanly** — they don't need `--bare`,
  since the whole point of that condition is mounting the real doctrine,
  not stripping the harness down.
- **True `bare`-scaffold cells need `--bare`, which needs an API key.**
  Without one, `run.py` **skips** bare cells by default (and says so on
  stderr) rather than quietly substituting something else. Passing
  `--allow-impure-bare` runs them anyway, WITHOUT the `--bare` flag —
  every such trial is tagged `impure_bare: true` in the raw JSON and
  flagged in the rendered report's Notes column, because it still
  inherits the operator's installed plugins/MCP servers/tool list rather
  than a truly minimal baseline.

This is a real, disclosed methodological caveat, not a rounding error —
any report cell built with `--allow-impure-bare` should be read as "bare,
approximately" and not as the clean baseline the thesis test wants.

## How README numbers must be generated

**Never hand-type a pass-rate, a cost figure, or an attempts-to-pass
number into a README or this file.** The only legitimate path from a real
run to a published number is:

```
run.py executes trials --> results/run-<ts>.json (raw, one row per attempt)
                       --> pg_lib.report.aggregate_by_cell (pure function over the JSON)
                       --> pg_lib.report.render_report (substitutes REPORT-template.md's marker)
                       --> results/REPORT-<ts>.md
```

If a number can't be traced back through that chain to a `results/run-
*.json` file, it doesn't go in the README. This is the repo's own
evidence-discipline rule (`docs/ULTIMATE_FRAMEWORK_PLAN.md`: "no
unverified stat goes into the README") applied to this specific harness.

## What's runnable now vs. what a full run would cost

**Runnable now, and exercised while building this:**
- `run.py --dry-run` — validates all 19 manifests, every grader imports
  and exposes its entrypoint, the matrix wiring is sound. $0, no
  subprocess.
- The full `pytest proving-ground/tests/` suite (105 tests) — every
  grader unit-tested against a hand-crafted correct fix/implementation
  (must PASS) and at least one plausible wrong or naive/vulnerable
  version (must FAIL), plus the anti-cheat paths (protected-path
  tampering, contract-file tampering, and the pytest-hijack cheat — an
  agent-planted `conftest.py`/`pytest.ini`/etc. that forces a false green
  without fixing anything, see `pg_lib.grading.detect_pytest_hijack_files`
  and `tests/test_grading_pytest_hijack.py`) and the matrix/report
  aggregation logic. $0, no subprocess.
- One real, cheap end-to-end cell (see Quickstart step 3) — proves
  `claude -p` invocation, JSON parsing, grading, and cost capture all
  wire together correctly on a live model call.

**What a full matrix run would cost (estimate, not measured):** 4 cells x
19 tasks x up to 3 attempts = up to 228 `claude -p` invocations. The
`tess-os` scaffold mounts the full doctrine (`CLAUDE.md` + `conductor/` +
`agents/` + `.claude/` + `core/`) — real prompt weight, plus the doctrine
itself may cause the model to dispatch a subagent via the Task tool
before doing any actual work, both of which push per-attempt cost above
the trivial ~$0.02 one-word-reply baseline measured above. Padding this
estimate per this project's own 1.5–3x rule rather than assuming the
happy path: budget on the order of **low tens of dollars and 30–90
minutes of wall-clock time** for one full run across all four cells, not
a fraction of a dollar. This is explicitly out of scope for this build —
per the mission brief, the harness + `--dry-run` validation + grader unit
tests are the deliverable, not a full benchmark run.

## Extending the suite

Add a new task by copying the shape of an existing one under `tasks/`
(see `tasks/README.md`), then re-run `python proving-ground/run.py
--dry-run` — it will refuse to pass silently if the new manifest is
malformed, the grader doesn't import, or a hidden-test/answer-key file
accidentally lives inside `fixture_dir` (which would leak it to the
agent).
