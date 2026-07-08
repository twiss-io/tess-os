"""Grader for 12-bug-csv-quoted-fields.

Data-driven: compares the agent's parse_fields against Python's own
csv.reader (the authoritative RFC-4180 parser) over a held-out set of
rows. Plain rows are included so an "always return []"/hardcoded cheat
fails; the quoted-comma and doubled-quote rows are the discriminators
that line.split(",") gets wrong.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from pg_lib.grading import import_module_from_path
from pg_lib.types import GradeResult

# Held-out rows — NONE of these appear in the shipped test_csvparse.py.
LINES: List[str] = [
    "a,b,c",                 # plain (must still be right)
    "name,age,city",         # plain
    "p,,q",                  # empty middle field
    "solo",                  # single field
    'a,"b,c",d',             # quoted field with a comma  <-- split(",") breaks here
    '"hello, world",42',     # leading quoted field with a comma
    'x,"y""z",w',            # doubled-quote escape inside a quoted field
    '"a,b","c,d"',           # two quoted fields each containing a comma
    'trailing,',             # trailing empty field
    '"just one, field"',     # single quoted field with a comma
]


def _reference(line: str) -> List[str]:
    return next(csv.reader([line]))


def grade(workdir: Path) -> GradeResult:
    try:
        module = import_module_from_path(workdir / "csvparse.py", unique_name="pg_sut_csvparse")
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"csvparse.py did not import: {exc}")

    fn = getattr(module, "parse_fields", None)
    if fn is None or not callable(fn):
        return GradeResult(False, "csvparse.py has no callable parse_fields()")

    failures = []
    for line in LINES:
        expected = _reference(line)
        try:
            actual = fn(line)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"parse_fields({line!r}) raised {type(exc).__name__}: {exc}")
            continue
        # Normalize tuples -> lists so a correct csv-based impl isn't
        # penalized for returning a tuple; values themselves must match.
        actual_list = list(actual) if isinstance(actual, (list, tuple)) else actual
        if actual_list != expected:
            failures.append(f"parse_fields({line!r}) = {actual!r}, expected {expected!r}")

    if failures:
        return GradeResult(False, f"{len(failures)} CSV row(s) parsed wrong", {"failures": failures[:10]})
    return GradeResult(True, "parse_fields matches csv.reader across plain, quoted-comma, and escaped-quote rows")
