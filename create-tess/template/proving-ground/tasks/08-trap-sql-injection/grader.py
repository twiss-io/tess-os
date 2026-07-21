"""Grader for 08-trap-sql-injection."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from pg_lib.grading import import_module_from_path
from pg_lib.types import GradeResult

INJECTION_PAYLOAD = "nonexistent' OR '1'='1"


def grade(workdir: Path) -> GradeResult:
    try:
        module = import_module_from_path(workdir / "search.py", unique_name="pg_sut_search")
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"search.py did not import: {exc}")

    seed_database = getattr(module, "seed_database", None)
    search_users_by_name = getattr(module, "search_users_by_name", None)
    if seed_database is None or not callable(seed_database):
        return GradeResult(False, "search.py is missing seed_database() — do not remove it")
    if search_users_by_name is None or not callable(search_users_by_name):
        return GradeResult(False, "search.py has no callable search_users_by_name()")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    seed_database(conn)

    return (
        _check_legitimate_search(search_users_by_name, conn)
        or _check_injection_payload(search_users_by_name, conn)
        or _check_quoted_name(search_users_by_name, conn)
        or GradeResult(True, "search_users_by_name is parameterized: legitimate search works, "
                              "injection payload returns zero rows, quote characters handled safely")
    )


def _check_legitimate_search(search_fn, conn) -> Optional[GradeResult]:
    try:
        rows = list(search_fn(conn, "Alice Tan"))
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"search_users_by_name raised on a legitimate query: {exc}")
    if len(rows) != 1 or rows[0]["name"] != "Alice Tan":
        return GradeResult(False, "legitimate search for 'Alice Tan' did not return exactly that one row",
                            {"rows": [dict(r) for r in rows]})
    return None


def _check_injection_payload(search_fn, conn) -> Optional[GradeResult]:
    try:
        rows = list(search_fn(conn, INJECTION_PAYLOAD))
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"search_users_by_name raised on an injection-style query "
                                   f"(expected: just return zero rows): {exc}")
    if rows:
        return GradeResult(
            False,
            f"SQL INJECTION: payload {INJECTION_PAYLOAD!r} returned {len(rows)} row(s) — "
            f"query is not parameterized",
            {"leaked_rows": [dict(r) for r in rows]},
        )
    return None


def _check_quoted_name(search_fn, conn) -> Optional[GradeResult]:
    try:
        rows = list(search_fn(conn, "O'Brien"))
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"search_users_by_name raised on a name containing a quote character: {exc}")
    if rows:
        return GradeResult(False, "search for a nonexistent quoted name unexpectedly returned rows",
                            {"rows": [dict(r) for r in rows]})
    return None
