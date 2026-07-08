"""Aggregate raw trial records into per-cell numbers, and render them into
`REPORT-template.md`.

This is the ONLY path by which a number is allowed to reach a report or
README: read `results/run-*.json` -> aggregate here -> substitute into the
template. There is deliberately no code path that lets a human hand-type a
pass-rate into a markdown file and call it this harness's output — see
`proving-ground/README.md` "How README numbers must be generated".
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from pg_lib.matrix import MODEL_TIERS
from pg_lib.scaffolds import BARE

TABLE_MARKER = "<!-- PROVING_GROUND_RESULTS_TABLE -->"


def summarize_task_outcomes(trials: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Group trials by (cell_id, task_id) and reduce each group to one
    outcome: did it eventually pass, at which attempt, and at what total
    cost across every attempt actually spent on it."""
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for trial in trials:
        key = f"{trial['cell_id']}::{trial['task_id']}"
        grouped[key].append(trial)

    outcomes: Dict[str, Dict[str, Any]] = {}
    for key, attempts in grouped.items():
        attempts_sorted = sorted(attempts, key=lambda t: t["attempt"])
        passing = [a for a in attempts_sorted if a["passed"]]
        outcomes[key] = {
            "cell_id": attempts_sorted[0]["cell_id"],
            "task_id": attempts_sorted[0]["task_id"],
            "passed": bool(passing),
            "attempts_used": len(attempts_sorted),
            "attempts_to_pass": passing[0]["attempt"] if passing else None,
            "total_cost_usd": sum(a["cost_usd"] for a in attempts_sorted),
            "impure_bare": any(a.get("impure_bare") for a in attempts_sorted),
        }
    return outcomes


def aggregate_by_cell(trials: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """The report's core numbers, one row per cell (model x scaffold)."""
    task_outcomes = summarize_task_outcomes(trials)

    by_cell: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for outcome in task_outcomes.values():
        by_cell[outcome["cell_id"]].append(outcome)

    aggregated: Dict[str, Dict[str, Any]] = {}
    for cell_id, outcomes in by_cell.items():
        aggregated[cell_id] = _aggregate_one_cell(outcomes)
    return aggregated


def _aggregate_one_cell(outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
    n_tasks = len(outcomes)
    n_passed = sum(1 for o in outcomes if o["passed"])
    attempts_to_pass = [o["attempts_to_pass"] for o in outcomes if o["attempts_to_pass"] is not None]
    return {
        "n_tasks": n_tasks,
        "n_passed": n_passed,
        "verified_pass_rate": (n_passed / n_tasks) if n_tasks else 0.0,
        "total_cost_usd": round(sum(o["total_cost_usd"] for o in outcomes), 4),
        "mean_attempts_to_pass": round(statistics.mean(attempts_to_pass), 2) if attempts_to_pass else None,
        "any_impure_bare": any(o["impure_bare"] for o in outcomes),
    }


def _split_cell_id(cell_id: str) -> Tuple[str, str]:
    """`"weak-tess-os"` -> `("weak", "tess-os")`. Can't just `.split("-")`
    because the `tess-os` scaffold name itself contains a hyphen — match
    against the known tier prefixes instead (`pg_lib.matrix.MODEL_TIERS`)."""
    for tier in MODEL_TIERS:
        prefix = f"{tier}-"
        if cell_id.startswith(prefix):
            return tier, cell_id[len(prefix):]
    raise ValueError(f"cell_id {cell_id!r} does not start with a known model tier {MODEL_TIERS}")


def compute_cost_multipliers(aggregated: Dict[str, Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Per-cell cost multiplier vs. that cell's same-tier `bare` baseline:
    `tess_os_total_cost / bare_total_cost`.

    This is the benchmark's own headline cost finding (`tess-os` ran
    1.7-2.7x `bare`'s cost every task, both tiers, no exceptions — see
    `reports/2026-07-07-fair.md`) made a first-class, always-computed
    number instead of something a reader has to derive by hand from two
    raw-dollar columns. A `bare` cell's own multiplier is always `1.0`
    (it IS the baseline). A cell gets `None` (rendered `n/a`, never a
    silently wrong number) when its same-tier `bare` counterpart is
    missing from this run (e.g. skipped for no `ANTHROPIC_API_KEY`) or
    when that baseline's cost is exactly `$0` (would divide by zero).
    """
    multipliers: Dict[str, Optional[float]] = {}
    for cell_id, row in aggregated.items():
        tier, scaffold = _split_cell_id(cell_id)
        if scaffold == BARE:
            multipliers[cell_id] = 1.0
            continue
        bare_row = aggregated.get(f"{tier}-{BARE}")
        if bare_row is None or bare_row["total_cost_usd"] == 0:
            multipliers[cell_id] = None
        else:
            multipliers[cell_id] = round(row["total_cost_usd"] / bare_row["total_cost_usd"], 2)
    return multipliers


def render_markdown_table(aggregated: Dict[str, Dict[str, Any]]) -> str:
    """One markdown table row per cell, sorted for a stable diff."""
    multipliers = compute_cost_multipliers(aggregated)
    header = (
        "| Cell | Tasks passed | Verified pass rate | Total cost (USD) | "
        "Cost vs bare (multiplier) | Mean attempts-to-pass | Notes |\n"
    )
    header += "|---|---|---|---|---|---|---|\n"
    rows = []
    for cell_id in sorted(aggregated):
        row = aggregated[cell_id]
        notes = "impure bare (no ANTHROPIC_API_KEY — see README)" if row["any_impure_bare"] else ""
        attempts = row["mean_attempts_to_pass"] if row["mean_attempts_to_pass"] is not None else "n/a"
        multiplier = multipliers.get(cell_id)
        if multiplier is None:
            cost_multiplier = "n/a"
        elif multiplier == 1.0 and _split_cell_id(cell_id)[1] == BARE:
            cost_multiplier = "1.00x (baseline)"
        else:
            cost_multiplier = f"{multiplier:.2f}x"
        rows.append(
            f"| `{cell_id}` | {row['n_passed']}/{row['n_tasks']} | "
            f"{row['verified_pass_rate']:.0%} | {row['total_cost_usd']:.4f} | "
            f"{cost_multiplier} | {attempts} | {notes} |"
        )
    return header + "\n".join(rows) + "\n"


META_MARKERS = {
    "timestamp_utc": "<!-- filled by run metadata -->",
    "models": "<!-- weak model id / strong model id -->",
    "scaffolds": "<!-- bare / tess-os -->",
    "max_attempts": "<!-- N -->",
    "tasks": "<!-- all 10, or a named subset -->",
}


def render_report(
    template_text: str,
    aggregated: Dict[str, Dict[str, Any]],
    meta: Optional[Dict[str, Any]] = None,
) -> str:
    """Substitute the results table into the report template at
    `TABLE_MARKER`, and (if `meta` is given) the "Run configuration" table's
    placeholder comments with the real values from this run. Raises if the
    results-table marker is missing — a template edited to drop it must
    fail loudly, not silently ship a report with no numbers in it. Meta
    substitution is best-effort (a missing placeholder just means that
    field stays as template text) so an edited template's Run Configuration
    section never blocks the one thing that MUST always render: the
    results table.
    """
    if TABLE_MARKER not in template_text:
        raise ValueError(f"REPORT template is missing the required marker: {TABLE_MARKER}")
    rendered = template_text.replace(TABLE_MARKER, render_markdown_table(aggregated))
    for field, placeholder in META_MARKERS.items():
        if meta and field in meta:
            rendered = rendered.replace(placeholder, str(meta[field]))
    return rendered
