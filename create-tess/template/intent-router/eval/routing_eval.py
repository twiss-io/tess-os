#!/usr/bin/env python3
"""Standalone runner for the 40-case routing eval (Epic E1 acceptance
criterion). This is the same eval `tests/intent_router/test_routing_eval.py`
enforces in CI, exposed as a script so a human can run it directly and
read a per-case report without invoking pytest.

    python intent-router/eval/routing_eval.py [--cases PATH] [--table PATH]

Exit code is 0 iff aggregate accuracy is >= 90%, mirroring the epic's
acceptance criterion exactly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

COMPONENT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = COMPONENT_ROOT.parent
DEFAULT_CASES = REPO_ROOT / "tests" / "intent_router" / "fixtures" / "routing_eval_cases.yaml"
DEFAULT_TABLE = COMPONENT_ROOT / "routing_table.example.yaml"

MIN_ACCURACY = 0.90

if str(COMPONENT_ROOT) not in sys.path:
    sys.path.insert(0, str(COMPONENT_ROOT))

from intent_router.routing_table import RoutingTable  # noqa: E402
from intent_router.router import route  # noqa: E402


def run(cases_path: Path, table_path: Path) -> int:
    with cases_path.open("r", encoding="utf-8") as f:
        cases = yaml.safe_load(f)["cases"]
    table = RoutingTable.load(table_path)

    correct = 0
    print(f"Routing eval — {len(cases)} cases against {table_path}\n")
    for i, case in enumerate(cases, start=1):
        decision = route(case["input"], table, force=True)
        ok = decision.route_id in case["expected_route_ids"]
        correct += int(ok)
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] #{i:02d} expected={case['expected_route_ids']} got={decision.route_id!r}")
        if not ok:
            print(f"        input: {case['input'][:100]!r}")

    accuracy = correct / len(cases)
    print(f"\nAccuracy: {correct}/{len(cases)} = {accuracy:.1%} (required >= {MIN_ACCURACY:.0%})")
    return 0 if accuracy >= MIN_ACCURACY else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    args = parser.parse_args(argv)
    return run(args.cases, args.table)


if __name__ == "__main__":
    sys.exit(main())
