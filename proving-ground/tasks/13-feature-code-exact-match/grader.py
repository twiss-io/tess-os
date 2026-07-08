"""Grader for 13-feature-code-exact-match.

Data-driven: compares is_valid_code against re.fullmatch(r"[0-9]{4}", s)
over a held-out set. The two discriminators are the over-length string
"12345" (which re.match(r"\\d{4}", s) wrongly accepts) and the
trailing-newline "1234\\n" (which re.match(r"\\d{4}$", s) wrongly accepts,
because $ matches before a final newline in Python). Valid strings are
included so an "always False" cheat fails, and clearly-invalid ones so an
"always True" cheat fails.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

from pg_lib.grading import import_module_from_path
from pg_lib.types import GradeResult

_REFERENCE = re.compile(r"[0-9]{4}")

CASES: List[str] = [
    "1234",     # valid
    "0000",     # valid
    "0007",     # valid
    "9999",     # valid
    "123",      # invalid: too short
    "12345",    # invalid: too long  <-- re.match without a trailing anchor accepts this
    "1234\n",   # invalid: trailing newline  <-- re.match(r"\d{4}$") accepts this
    "12a4",     # invalid: non-digit
    " 1234",    # invalid: leading space
    "1234 ",    # invalid: trailing space
    "12 4",     # invalid: internal space
    "",         # invalid: empty
    "abcd",     # invalid: no digits
    "12.4",     # invalid: punctuation
]


def _reference(s: str) -> bool:
    return _REFERENCE.fullmatch(s) is not None


def grade(workdir: Path) -> GradeResult:
    try:
        module = import_module_from_path(workdir / "codes.py", unique_name="pg_sut_codes")
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"codes.py did not import: {exc}")

    fn = getattr(module, "is_valid_code", None)
    if fn is None or not callable(fn):
        return GradeResult(False, "codes.py has no callable is_valid_code()")

    failures = []
    for s in CASES:
        expected = _reference(s)
        try:
            actual = fn(s)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"is_valid_code({s!r}) raised {type(exc).__name__}: {exc}")
            continue
        if bool(actual) != expected:
            failures.append(f"is_valid_code({s!r}) = {actual!r}, expected {expected}")

    if failures:
        return GradeResult(False, f"{len(failures)} case(s) wrong", {"failures": failures})
    return GradeResult(True, "is_valid_code exactly matches a fully-anchored 4-digit check on all held-out cases")
