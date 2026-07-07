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
from typing import Any, Dict, List, Optional

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


def render_markdown_table(aggregated: Dict[str, Dict[str, Any]]) -> str:
    """One markdown table row per cell, sorted for a stable diff."""
    header = "| Cell | Tasks passed | Verified pass rate | Total cost (USD) | Mean attempts-to-pass | Notes |\n"
    header += "|---|---|---|---|---|---|\n"
    rows = []
    for cell_id in sorted(aggregated):
        row = aggregated[cell_id]
        notes = "impure bare (no ANTHROPIC_API_KEY — see README)" if row["any_impure_bare"] else ""
        attempts = row["mean_attempts_to_pass"] if row["mean_attempts_to_pass"] is not None else "n/a"
        rows.append(
            f"| `{cell_id}` | {row['n_passed']}/{row['n_tasks']} | "
            f"{row['verified_pass_rate']:.0%} | {row['total_cost_usd']:.4f} | {attempts} | {notes} |"
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
