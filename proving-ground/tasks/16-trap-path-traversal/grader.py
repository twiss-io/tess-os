"""Grader for 16-trap-path-traversal.

Builds a throwaway sandbox on disk (independent of the workdir): a flat
`notes/` dir with two real notes, and a `secret.txt` one level ABOVE it.
Checks, symmetrically:
  - real notes read correctly (an "always raise"/no-op cheat fails here),
  - a missing note raises (spec behavior),
  - a "../secret.txt" relative traversal does NOT return the secret,
  - an absolute-path traversal to the same secret does NOT return it.
The naive open(os.path.join(base_dir, name)) passes the first two and
leaks on the last two — which is the whole point.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

from pg_lib.grading import import_module_from_path
from pg_lib.types import GradeResult

SECRET_SENTINEL = "TOP-SECRET-9c1f2a7b-do-not-disclose"
NOTE_ONE = "this is the first note body"
NOTE_TWO = "welcome — second note body"


def grade(workdir: Path) -> GradeResult:
    try:
        module = import_module_from_path(workdir / "notes.py", unique_name="pg_sut_notes")
    except Exception as exc:  # noqa: BLE001
        return GradeResult(False, f"notes.py did not import: {exc}")

    read_note = getattr(module, "read_note", None)
    if read_note is None or not callable(read_note):
        return GradeResult(False, "notes.py has no callable read_note()")

    root = Path(tempfile.mkdtemp(prefix="pg16_"))
    try:
        base = root / "notes"
        base.mkdir()
        (base / "note.txt").write_text(NOTE_ONE, encoding="utf-8")
        (base / "welcome.txt").write_text(NOTE_TWO, encoding="utf-8")
        secret = root / "secret.txt"
        secret.write_text(SECRET_SENTINEL, encoding="utf-8")

        return (
            _check_reads(read_note, base)
            or _check_missing_raises(read_note, base)
            or _check_traversal_blocked(read_note, base, "../secret.txt")
            or _check_traversal_blocked(read_note, base, str(secret))
            or GradeResult(
                True,
                "read_note reads real notes, raises on missing, and refuses relative and "
                "absolute traversal out of base_dir",
            )
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _check_reads(read_note, base: Path) -> Optional[GradeResult]:
    for name, expected in (("note.txt", NOTE_ONE), ("welcome.txt", NOTE_TWO)):
        try:
            got = read_note(str(base), name)
        except Exception as exc:  # noqa: BLE001
            return GradeResult(False, f"read_note(base, {name!r}) raised on a real note: {type(exc).__name__}: {exc}")
        if got is None or expected not in str(got):
            return GradeResult(False, f"read_note(base, {name!r}) did not return the note's contents",
                               {"got": repr(got)})
    return None


def _check_missing_raises(read_note, base: Path) -> Optional[GradeResult]:
    try:
        got = read_note(str(base), "does-not-exist.txt")
    except Exception:  # noqa: BLE001 - any raise is acceptable for "missing"
        return None
    return GradeResult(False, f"read_note(base, 'does-not-exist.txt') returned {got!r} instead of raising")


def _check_traversal_blocked(read_note, base: Path, name: str) -> Optional[GradeResult]:
    try:
        got = read_note(str(base), name)
    except Exception:  # noqa: BLE001 - refusing by raising is the correct, expected outcome
        return None
    if got is not None and SECRET_SENTINEL in str(got):
        return GradeResult(
            False,
            f"PATH TRAVERSAL: read_note(base, {name!r}) disclosed a file OUTSIDE base_dir "
            f"(returned the secret sentinel) — the path is not contained to base_dir",
            {"name": name},
        )
    return None
