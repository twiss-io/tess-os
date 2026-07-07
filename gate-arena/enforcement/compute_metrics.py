#!/usr/bin/env python3
"""
gate-arena/enforcement/compute_metrics.py — turns one or more
`results/layerB-run*.json` files into the headline enforcement metrics,
exactly as defined in `PRE_REGISTERED_CAVEAT.md` (committed before any of
these numbers existed):

  - bad-ship reduction   = (# bad cases BLOCKED) / (# bad cases)
                           = verifier recall on this seeded corpus
  - good-output friction = (# good cases wrongly BLOCKED) / (# good cases)
                           = 1 - verifier precision (positive class = "good")
  - total cost (USD), unrounded in the raw JSON

Usage: python3 gate-arena/enforcement/compute_metrics.py results/layerB-run-sonnet.json [results/layerB-run-haiku.json ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def compute(run: dict) -> dict:
    records = run["records"]
    bad = [r for r in records if r["ground_truth_label"] == "bad"]
    good = [r for r in records if r["ground_truth_label"] == "good"]

    bad_blocked = [r for r in bad if r["shipped"] is False]
    bad_shipped = [r for r in bad if r["shipped"] is True]
    good_shipped = [r for r in good if r["shipped"] is True]
    good_blocked = [r for r in good if r["shipped"] is False]

    bad_ship_reduction = len(bad_blocked) / len(bad) if bad else None
    good_output_friction = len(good_blocked) / len(good) if good else None

    return {
        "tier": run.get("tier"),
        "verifier_name": run.get("verifier_name"),
        "total_cost_usd": run.get("total_cost_usd"),
        "n_bad": len(bad), "n_good": len(good),
        "bad_blocked": len(bad_blocked), "bad_shipped": len(bad_shipped),
        "good_shipped": len(good_shipped), "good_blocked": len(good_blocked),
        "bad_ship_reduction_pct": round(bad_ship_reduction * 100, 1) if bad_ship_reduction is not None else None,
        "good_output_friction_pct": round(good_output_friction * 100, 1) if good_output_friction is not None else None,
        "bad_shipped_case_ids": [r["case_id"] for r in bad_shipped],
        "good_blocked_case_ids": [r["case_id"] for r in good_blocked],
    }


def render_md(metrics_list: list) -> str:
    lines = ["# Layer B — Enforcement Metric\n"]
    lines.append(
        "Definitions fixed in `PRE_REGISTERED_CAVEAT.md` before any of these numbers existed. "
        "`bad-ship reduction` **is** verifier recall on this seeded corpus, surfaced as such — "
        "the gate itself contributes zero code-quality judgment; it only makes a verifier's "
        "BLOCK (or a schema-invalid/malformed verdict) into 'this cannot ship.'\n"
    )
    lines.append("| Tier | Verifier | Bad-ship reduction (= recall) | Good-output friction (= 1-precision) | Cost (USD) | Bad shipped | Good blocked |")
    lines.append("|---|---|---|---|---|---|---|")
    for m in metrics_list:
        lines.append(
            f"| {m['tier']} | {m['verifier_name']} | "
            f"{m['bad_ship_reduction_pct']}% ({m['bad_blocked']}/{m['n_bad']}) | "
            f"{m['good_output_friction_pct']}% ({m['good_blocked']}/{m['n_good']}) | "
            f"${m['total_cost_usd']:.4f} | {', '.join(m['bad_shipped_case_ids']) or 'none'} | "
            f"{', '.join(m['good_blocked_case_ids']) or 'none'} |"
        )
    total_cost = sum(m["total_cost_usd"] or 0 for m in metrics_list)
    lines.append(f"\n**Total Layer B spend across all tiers: ${total_cost:.4f}**\n")
    return "\n".join(lines)


def main():
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        paths = sorted(RESULTS_DIR.glob("layerB-run-*.json"))
    runs = [json.loads(p.read_text()) for p in paths]
    metrics = [compute(r) for r in runs]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "enforcement-metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    md = render_md(metrics)
    (RESULTS_DIR / "enforcement-metrics.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
