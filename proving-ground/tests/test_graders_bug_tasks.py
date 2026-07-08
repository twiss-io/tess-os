"""Unit-test the graders for the three bug-with-failing-test tasks
(01, 02, 09) against hand-crafted fixtures: the as-shipped (broken) state
must FAIL, a correct fix must PASS, and editing the protected test file
must FAIL regardless of the "fix" (anti-cheat check).
"""
from __future__ import annotations

from pg_lib.grading import grade_task


def test_01_shipped_bug_fails_grading(stage_task):
    manifest, workdir = stage_task("01-bug-average-empty-list")
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_01_correct_fix_passes_grading(stage_task):
    manifest, workdir = stage_task("01-bug-average-empty-list")
    (workdir / "calc.py").write_text(
        "def average(values):\n"
        "    if not values:\n"
        "        return 0.0\n"
        "    return sum(values) / len(values)\n"
    )
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason


def test_01_editing_protected_test_file_fails_even_with_a_fix(stage_task):
    manifest, workdir = stage_task("01-bug-average-empty-list")
    (workdir / "calc.py").write_text(
        "def average(values):\n"
        "    return 0.0\n"
    )
    (workdir / "test_calc.py").write_text("def test_trivially_true():\n    assert True\n")
    result = grade_task(manifest, workdir)
    assert result.passed is False
    assert "protected" in result.reason.lower()


def test_02_shipped_bug_fails_grading(stage_task):
    manifest, workdir = stage_task("02-bug-pagination-off-by-one")
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_02_correct_fix_passes_grading(stage_task):
    manifest, workdir = stage_task("02-bug-pagination-off-by-one")
    (workdir / "paginate.py").write_text(
        "def paginate(items, page, page_size):\n"
        "    start = page * page_size\n"
        "    end = start + page_size\n"
        "    return items[start:end]\n"
    )
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason


def test_09_shipped_bug_fails_grading(stage_task):
    manifest, workdir = stage_task("09-bug-duplicate-charge-idempotency")
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_09_correct_fix_passes_grading(stage_task):
    manifest, workdir = stage_task("09-bug-duplicate-charge-idempotency")
    (workdir / "payments.py").write_text(
        "def process_payment(idempotency_key, amount, charge_fn, ledger):\n"
        "    if idempotency_key in ledger:\n"
        "        return ledger[idempotency_key]\n"
        "    charge_fn(amount)\n"
        "    result = {'status': 'charged', 'amount': amount}\n"
        "    ledger[idempotency_key] = result\n"
        "    return result\n"
    )
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason
