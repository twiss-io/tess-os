"""Grader for 19-feature-discount-spec.

Data-driven: compares apply_discount against a floor-based integer
reference on valid inputs (and requires an int return), and requires a
ValueError-style raise on out-of-range percents. The discriminators are
the floor boundary (995 @ 33% -> 666, where round() gives 667), the
int-vs-float return type, and the range check the naive expression omits.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import List, Tuple

from pg_lib.grading import import_module_from_path
from pg_lib.types import GradeResult

# (price_cents, discount_percent) -> must equal reference, returned as int.
VALID_CASES: List[Tuple[int, float]] = [
    (1000, 10),     # 900 (disclosed shape)
    (2000, 25),     # 1500
    (995, 33),      # 666  <-- floor; round() gives 667
    (999, 10),      # 899
    (1000, 12.5),   # 875  <-- float percent
    (1234, 37),     # floor bite
    (1000, 0),      # 1000 unchanged
    (1000, 100),    # 0
    (0, 50),        # 0 (zero price)
]

# Percents outside [0, 100] must raise.
INVALID_CASES: List[Tuple[int, float]] = [
    (1000, 150),
    (1000, -5),
    (1000, 100.1),
    (1000, -0.5),
]


def _reference(price_cents: int, discount_percent: float) -> int:
    return math.floor(price_cents * (100 - discount_percent) / 100)


def grade(workdir: Path) -> GradeResult:
    try:
        module = import_module_from_path(workdir / "discount.py", unique_name="pg_sut_discount")
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"discount.py did not import: {exc}")

    fn = getattr(module, "apply_discount", None)
    if fn is None or not callable(fn):
        return GradeResult(False, "discount.py has no callable apply_discount()")

    failures = []

    for price, pct in VALID_CASES:
        expected = _reference(price, pct)
        try:
            actual = fn(price, pct)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"apply_discount({price}, {pct}) raised {type(exc).__name__}: {exc}")
            continue
        if isinstance(actual, bool) or not isinstance(actual, int):
            failures.append(f"apply_discount({price}, {pct}) returned {actual!r} (type {type(actual).__name__}); "
                            f"must return an int")
            continue
        if actual != expected:
            failures.append(f"apply_discount({price}, {pct}) = {actual!r}, expected {expected} (floored)")

    for price, pct in INVALID_CASES:
        try:
            actual = fn(price, pct)
        except Exception:  # noqa: BLE001 - raising (ValueError) is the required behavior
            continue
        failures.append(f"apply_discount({price}, {pct}) returned {actual!r}; expected a ValueError for out-of-range percent")

    if failures:
        return GradeResult(False, f"{len(failures)} case(s) wrong", {"failures": failures[:12]})
    return GradeResult(True, "apply_discount floors to whole cents, returns int, and rejects out-of-range percents")
