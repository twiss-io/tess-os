# Tess OS Proving Ground — Report

> **This file is a template, not a report.** A real report is produced by
> `run.py` writing to `results/REPORT-<timestamp>.md` — it is `run.py`
> reading `REPORT-template.md`, substituting the results table at the
> marker below, and writing the result. Nobody hand-types the table.
> See `README.md`'s "How README numbers must be generated" for the rule
> this enforces, and `pg_lib/report.py` for the substitution code.

## What this measures

Four cells — every combination of:

- **Model tier**: `weak` (a cheap/fast model) vs. `strong` (a
  frontier-class model)
- **Scaffold**: `bare` (no Tess OS doctrine — the model, unassisted) vs.
  `tess-os` (this repo's `CLAUDE.md` + `conductor/` + `agents/` +
  `.claude/` + `core/` doctrine, mounted verbatim)

against the 10 seeded tasks in `tasks/` (spanning bug-with-failing-test,
feature-vs-spec, research-with-checkable-facts, and planted security
traps — see `tasks/README.md`).

**The thesis under test:** `weak + tess-os` should approach or exceed
`strong + bare` on verified-pass-rate — i.e., structure narrows the gap a
raw model-quality upgrade would otherwise require. This report either
supports that or it doesn't; either outcome is the actual result. A
report showing the thesis DOESN'T hold on this suite is still a valid,
useful report — it means either the doctrine needs work or the task
suite needs harder/different cases, and that itself is information the
project needs.

## Run configuration

| Field | Value |
|---|---|
| Timestamp (UTC) | `<!-- filled by run metadata -->` |
| Models under test | `<!-- weak model id / strong model id -->` |
| Scaffolds under test | `<!-- bare / tess-os -->` |
| Max attempts per task | `<!-- N -->` |
| Tasks included | `<!-- all 10, or a named subset -->` |

## Results

<!-- PROVING_GROUND_RESULTS_TABLE -->

**Column definitions:**

- **Tasks passed** — count of tasks where at least one attempt (within
  `--max-attempts`) produced a `GradeResult(passed=True)`.
- **Verified pass rate** — tasks passed / tasks attempted for that cell.
  "Verified" because every pass is a deterministic grader's verdict, not
  a model's self-report — the same distinction the framework's own
  `return-manifest` contract draws between a claim and its evidence.
- **Total cost (USD)** — summed `total_cost_usd` from every `claude -p`
  attempt actually run for that cell, across every task.
- **Cost vs bare (multiplier)** — `this cell's total cost / that same
  model tier's bare-cell total cost` (`pg_lib.report.compute_cost_multipliers`).
  `bare` rows show `1.00x (baseline)`; `n/a` if the same-tier `bare` cell
  wasn't run this time (skipped, or all-zero cost). This is the doctrine's
  cost premium made a first-class, always-rendered number — not something
  a reader has to compute by hand from the raw-dollar column. The first
  full runs found this in the 1.7-2.7x range at both tiers, every task, no
  exceptions (see `reports/2026-07-07-fair.md`) — this column is what lets
  any future run report that premium explicitly instead of re-deriving it.
- **Mean attempts-to-pass** — averaged only over tasks that eventually
  passed; `n/a` if none did.
- **Notes** — flags `impure bare` cells (see below) and anything else
  material to interpreting that row.

## Known limitations / threats to validity

- **`impure_bare`** — a true `bare` condition requires the `claude --bare`
  CLI flag, which mandates `ANTHROPIC_API_KEY` auth (OAuth/keychain are
  never read in that mode — verified live against a real `claude`
  install; see `README.md`). Without that key configured, `run.py`
  either **skips** bare-scaffold cells entirely (default) or, with
  `--allow-impure-bare`, runs them without `--bare` — which still
  inherits the operator's installed plugins, MCP servers, and tool list.
  Any cell run this way is marked `impure_bare: true` in the raw results
  and flagged in this table's Notes column; its numbers are NOT a clean
  baseline and should not be quoted without that caveat.
- **Non-determinism** — model sampling means a single attempt's pass/fail
  is a draw, not a fixed property. `--max-attempts` (default 3, matching
  the framework's own retry-protocol cap) reduces but does not eliminate
  this; a report over N=1 task-instances per cell has real variance —
  treat single-suite numbers as directional, not as tight statistics.
- **Ten tasks is a floor, not a ceiling** — the mission's acceptance bar
  is "at least 10 seeded tasks spanning four categories." A published
  claim resting on this report should say "on this 10-task suite," not
  imply a general benchmark result.
- **Cost is per-attempt `claude -p --max-budget-usd`-capped**, and the
  whole run is additionally capped by `--max-total-budget-usd` — a run
  that hits either cap stops early and is marked in the raw JSON's
  `meta.budget_exhausted`. Check that field before trusting a "0 cost"
  or suspiciously low-attempt row.

## Raw data

The machine-readable trial-level data behind this table lives alongside
this report at `results/run-<timestamp>.json` (same timestamp as this
file's filename) — every individual attempt, not just the aggregates.
