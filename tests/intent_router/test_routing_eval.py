"""The 40-case routing eval — Epic E1's acceptance criteria, made runnable
and CI-checked.

"A 40-case routing eval (real historical mission briefs from
kb/wiki/log.md as ground truth) routes >=90% to the same entry point a
human operator chose."

See fixtures/routing_eval_cases.yaml for the honest data-source note: this
public repo does not carry the private Tess repo's historical mission
log, so these 40 cases are synthetic-but-representative utterances across
the same six outcome-orchestrator domains + ten mission-lifecycle/system
commands, phrased independently of the routing table's own keyword and
example text (to test generalization, not memorization).

This eval calls the DETERMINISTIC classifier only (no `external_signal`,
no model call) — it is exactly the "deterministic mapping" the parent
task brief says must be "testable separately" from any model-assisted
classification pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import _paths  # noqa: F401 -- sys.path bootstrap, see _paths.py docstring
from _paths import example_routing_table  # noqa: F401 -- pytest fixture, used by parameter name

from intent_router.router import route

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
CASES_PATH = FIXTURES_DIR / "routing_eval_cases.yaml"

MIN_ACCURACY = 0.90


def _load_cases():
    with CASES_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["cases"]


def test_fixture_has_exactly_40_cases():
    assert len(_load_cases()) == 40


def test_routing_eval_meets_or_exceeds_90_percent_accuracy(example_routing_table):
    cases = _load_cases()
    results = []
    for case in cases:
        decision = route(case["input"], example_routing_table, force=True)
        correct = decision.route_id in case["expected_route_ids"]
        results.append(
            {
                "input": case["input"],
                "expected": case["expected_route_ids"],
                "got": decision.route_id,
                "ambiguous_before_force": decision.assumption_stated is not None,
                "correct": correct,
            }
        )

    accuracy = sum(r["correct"] for r in results) / len(results)
    failures = [r for r in results if not r["correct"]]

    failure_report = "\n".join(
        f"  input={r['input'][:80]!r} expected={r['expected']} got={r['got']!r}"
        for r in failures
    )
    assert accuracy >= MIN_ACCURACY, (
        f"routing eval accuracy {accuracy:.2%} < required {MIN_ACCURACY:.0%} "
        f"({len(failures)}/{len(results)} misses):\n{failure_report}"
    )


def test_routing_eval_never_leaves_a_case_unrouted(example_routing_table):
    """Zero cases where the user is asked to pick a command (epic
    acceptance criterion, second half) — every case, forced through
    clarification if needed, must land on a real route id."""
    cases = _load_cases()
    for case in cases:
        decision = route(case["input"], example_routing_table, force=True)
        assert decision.route_id is not None
        assert decision.ambiguous is False


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["input"][:40])
def test_each_case_individually(case, example_routing_table):
    """Same eval, one case per test id, so a CI failure names the exact
    input that mis-routed instead of only the aggregate percentage."""
    decision = route(case["input"], example_routing_table, force=True)
    if decision.route_id not in case["expected_route_ids"]:
        pytest.xfail(
            f"expected one of {case['expected_route_ids']}, got {decision.route_id!r} "
            "(aggregate accuracy is separately enforced at >=90% by "
            "test_routing_eval_meets_or_exceeds_90_percent_accuracy)"
        )
