"""Grader for 18-bug-idempotency-retry-after-failure.

Data-driven: drives process() directly with instrumented charge_fns. The
discriminating case (4) makes the first attempt's charge_fn raise, then
retries with a working charge_fn and asserts the retry actually charged —
which the shipped record-before-charge code cannot do (it stored the key
on the failed attempt). Cases 1-3 mirror the visible test so a no-op or a
"never charge" cheat also fails.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pg_lib.grading import import_module_from_path
from pg_lib.types import GradeResult


def grade(workdir: Path) -> GradeResult:
    try:
        module = import_module_from_path(workdir / "charge.py", unique_name="pg_sut_charge")
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"charge.py did not import: {exc}")

    process = getattr(module, "process", None)
    if process is None or not callable(process):
        return GradeResult(False, "charge.py has no callable process()")

    return (
        _check_first_success(process)
        or _check_idempotent_repeat(process)
        or _check_distinct_keys(process)
        or _check_retry_after_failure(process)
        or GradeResult(
            True,
            "process charges once, is idempotent on repeat success, charges distinct keys, "
            "and a retry after a failed attempt actually charges",
        )
    )


def _check_first_success(process) -> Optional[GradeResult]:
    calls = []
    ledger = {}
    try:
        result = process("k1", 100, lambda a: calls.append(a), ledger)
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"process raised on a normal first charge: {type(exc).__name__}: {exc}")
    if calls != [100]:
        return GradeResult(False, f"first charge called charge_fn {calls!r} times, expected exactly [100]")
    if result != {"status": "charged", "amount": 100}:
        return GradeResult(False, f"first charge returned {result!r}, expected charged/100")
    return None


def _check_idempotent_repeat(process) -> Optional[GradeResult]:
    calls = []
    ledger = {}
    first = process("k1", 100, lambda a: calls.append(a), ledger)
    second = process("k1", 100, lambda a: calls.append(a), ledger)
    if calls != [100]:
        return GradeResult(False, f"repeat with same key charged again (calls={calls!r}); must be idempotent")
    if second != first:
        return GradeResult(False, f"idempotent repeat returned {second!r}, expected the first result {first!r}")
    return None


def _check_distinct_keys(process) -> Optional[GradeResult]:
    calls = []
    ledger = {}
    process("k1", 100, lambda a: calls.append(a), ledger)
    process("k2", 50, lambda a: calls.append(a), ledger)
    if calls != [100, 50]:
        return GradeResult(False, f"distinct keys should each charge (calls={calls!r}, expected [100, 50])")
    return None


def _check_retry_after_failure(process) -> Optional[GradeResult]:
    calls = []
    ledger = {}

    def failing(_amount):
        raise RuntimeError("gateway down")

    # First attempt: charge_fn raises. However the impl signals failure
    # (propagating is what the brief asks for), it must NOT record the key.
    try:
        process("kf", 200, failing, ledger)
    except Exception:  # noqa: BLE001 - a propagated failure is expected/acceptable here
        pass

    # Retry with a working charge_fn — this MUST actually charge.
    try:
        result = process("kf", 200, lambda a: calls.append(a), ledger)
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"retry after a failed attempt raised: {type(exc).__name__}: {exc}")

    if calls != [200]:
        return GradeResult(
            False,
            "IDEMPOTENCY BUG: after the first attempt's charge_fn raised, the retry did NOT charge "
            f"(charge_fn calls on retry={calls!r}, expected [200]) — the key was poisoned by the failed attempt",
        )
    if result != {"status": "charged", "amount": 200}:
        return GradeResult(False, f"retry after failure returned {result!r}, expected charged/200")
    return None
