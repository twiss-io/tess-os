"""Grader for 14-feature-dedupe-case-insensitive.

Data-driven: compares dedupe_emails against a reference that dedupes on
lowercased key, keeps the first occurrence's original string, and
preserves order. The held-out cases each isolate one clause a plausible
one-liner breaks (case-insensitivity, order, original casing), plus
same-case and empty cases so hardcoded/no-op cheats fail.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from pg_lib.grading import import_module_from_path
from pg_lib.types import GradeResult

CASES: List[List[str]] = [
    ["a@x.com", "b@x.com", "a@x.com"],                       # same-case dup (disclosed shape)
    ["Bob@X.com", "bob@x.com", "c@x.com"],                   # mixed-case dup -> keep "Bob@X.com"
    ["z@x.com", "a@x.com", "z@x.com"],                       # order-sensitive
    ["Alice@X.com"],                                         # original casing must survive
    ["A@x.com", "a@X.com", "B@x.com", "b@x.com", "A@x.com"], # multiple mixed-case dups
    [],                                                      # empty
    ["one@x.com", "two@x.com", "three@x.com"],               # all unique, order preserved
]


def _reference(emails: List[str]) -> List[str]:
    seen = set()
    out = []
    for e in emails:
        key = e.lower()
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def grade(workdir: Path) -> GradeResult:
    try:
        module = import_module_from_path(workdir / "dedupe.py", unique_name="pg_sut_dedupe")
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"dedupe.py did not import: {exc}")

    fn = getattr(module, "dedupe_emails", None)
    if fn is None or not callable(fn):
        return GradeResult(False, "dedupe.py has no callable dedupe_emails()")

    failures = []
    for emails in CASES:
        expected = _reference(emails)
        try:
            actual = fn(list(emails))
        except Exception as exc:  # noqa: BLE001
            failures.append(f"dedupe_emails({emails!r}) raised {type(exc).__name__}: {exc}")
            continue
        actual_list = list(actual) if isinstance(actual, (list, tuple)) else actual
        if actual_list != expected:
            failures.append(f"dedupe_emails({emails!r}) = {actual!r}, expected {expected!r}")

    if failures:
        return GradeResult(False, f"{len(failures)} case(s) wrong", {"failures": failures})
    return GradeResult(
        True,
        "dedupe_emails is case-insensitive, order-preserving, and keeps first-occurrence casing",
    )
