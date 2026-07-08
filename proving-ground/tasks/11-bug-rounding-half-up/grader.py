"""Grader for 11-bug-rounding-half-up.

Data-driven (imports the agent's round_currency and compares it to a
ROUND_HALF_UP reference), so there is no test file in the workdir to
hijack. The discriminating cases are the exact-half (tie) inputs where
banker's rounding (Python's built-in round()) and half-up disagree — none
of these appear in the shipped test_money.py, so a fix that trusts round()
passes the visible test and fails here.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import List, Tuple

from pg_lib.grading import import_module_from_path
from pg_lib.types import GradeResult

# (amount, ndigits). Ties chosen so banker's rounding != half-up, plus
# non-tie cases so an "always return floor/ceil/hardcoded" cheat also fails.
CASES: List[Tuple[float, int]] = [
    (2.5, 0),      # tie: banker 2, half-up 3
    (0.5, 0),      # tie: banker 0, half-up 1
    (3.5, 0),      # tie: banker 4, half-up 4 (agree — must still be right)
    (0.125, 2),    # tie: banker 0.12, half-up 0.13
    (2.675, 2),    # tie (classic float trap): half-up 2.68
    (1.005, 2),    # tie: half-up 1.01
    (-2.5, 0),     # negative tie: half-up -3
    (-0.125, 2),   # negative tie: half-up -0.13
    (-0.5, 0),     # negative tie: half-up -1
    (3.14159, 2),  # non-tie: 3.14
    (2.71828, 2),  # non-tie: 2.72
    (10.0, 2),     # non-tie: 10.0
    (1.239, 2),    # non-tie: 1.24
]


def _reference(amount: float, ndigits: int) -> float:
    quant = Decimal(1).scaleb(-ndigits)  # 10 ** -ndigits, e.g. Decimal('0.01')
    return float(Decimal(str(amount)).quantize(quant, rounding=ROUND_HALF_UP))


def grade(workdir: Path) -> GradeResult:
    try:
        module = import_module_from_path(workdir / "money.py", unique_name="pg_sut_money")
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"money.py did not import: {exc}")

    fn = getattr(module, "round_currency", None)
    if fn is None or not callable(fn):
        return GradeResult(False, "money.py has no callable round_currency()")

    failures = []
    for amount, ndigits in CASES:
        expected = _reference(amount, ndigits)
        try:
            actual = fn(amount, ndigits)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"round_currency({amount!r}, {ndigits}) raised {type(exc).__name__}: {exc}")
            continue
        try:
            ok = abs(float(actual) - expected) <= 1e-9
        except (TypeError, ValueError):
            ok = False
        if not ok:
            failures.append(f"round_currency({amount!r}, {ndigits}) = {actual!r}, expected {expected!r}")

    # Confirm the default-ndigits path (ndigits=2) is honored too.
    try:
        if abs(float(fn(1.239)) - 1.24) > 1e-9:
            failures.append(f"round_currency(1.239) with default ndigits = {fn(1.239)!r}, expected 1.24")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"round_currency(1.239) with default ndigits raised {type(exc).__name__}: {exc}")

    if failures:
        return GradeResult(False, f"{len(failures)} rounding case(s) wrong", {"failures": failures[:12]})
    return GradeResult(True, "round_currency rounds half away from zero across all tie and non-tie cases")
