"""Grader for 10-feature-pagination-contract.

Data-driven, not pytest-based: this grader carries its own independent
reference implementation of contract.json's rules, and compares the
agent's `paginate_response` against it — across the three examples
disclosed in contract.json AND a generated set of held-out cases the
agent never sees (including the `page_size <= 0` error case and an
exact-fitting last page). Comparing against disclosed examples ALONE
would let a lookup-table cheat pass; the held-out cases close that gap.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List

from pg_lib.grading import import_module_from_path
from pg_lib.types import GradeResult


def _reference_paginate_response(items: List[Any], page: int, page_size: int) -> Dict[str, Any]:
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    total = len(items)
    start = page * page_size
    end = start + page_size
    page_items = items[start:end]
    total_pages = math.ceil(total / page_size) if total else 0
    return {
        "items": page_items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": end < total,
        "has_prev": page > 0,
    }


def _generated_cases() -> List[Dict[str, Any]]:
    """Held-out cases the agent never sees — closes the lookup-table gap
    the three disclosed contract.json examples alone would leave open."""
    cases = []
    for total in (0, 1, 3, 4, 5, 7):
        items = list(range(total))
        for page_size in (1, 2, 3, 10):
            for page in (0, 1, 2, 5):
                cases.append({"items": items, "page": page, "page_size": page_size})
    cases.append({"items": [1, 2, 3], "page": 0, "page_size": 0})  # must raise ValueError
    cases.append({"items": [1, 2, 3], "page": 0, "page_size": -1})  # must raise ValueError
    return cases


def _load_disclosed_examples(workdir: Path) -> List[Dict[str, Any]]:
    contract = json.loads((workdir / "contract.json").read_text(encoding="utf-8"))
    return [{"input": ex["input"], "expected": ex["output"]} for ex in contract["examples"]]


def _run_one_case(paginate_response, case: Dict[str, Any]) -> str:
    """Returns "" on match, else a short failure description."""
    try:
        expected = _reference_paginate_response(**case)
    except ValueError:
        expected = "ValueError"

    try:
        actual = paginate_response(**case)
    except ValueError:
        actual = "ValueError"
    except Exception as exc:  # noqa: BLE001 - any other exception is a mismatch, not a harness crash
        return f"input {case}: raised unexpected {type(exc).__name__}: {exc}"

    if actual != expected:
        return f"input {case}: expected {expected!r}, got {actual!r}"
    return ""


def grade(workdir: Path) -> GradeResult:
    try:
        module = import_module_from_path(workdir / "pagination_contract.py", unique_name="pg_sut_pagination_contract")
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"pagination_contract.py did not import: {exc}")

    paginate_response = getattr(module, "paginate_response", None)
    if paginate_response is None or not callable(paginate_response):
        return GradeResult(False, "pagination_contract.py has no callable paginate_response()")

    failures = []
    for example in _load_disclosed_examples(workdir):
        failures.append(_run_one_case(paginate_response, example["input"]))
    for case in _generated_cases():
        failures.append(_run_one_case(paginate_response, case))
    failures = [f for f in failures if f]

    if failures:
        return GradeResult(False, f"{len(failures)} case(s) failed", {"failures": failures[:10]})
    return GradeResult(True, "all disclosed + held-out cases matched the reference implementation")
