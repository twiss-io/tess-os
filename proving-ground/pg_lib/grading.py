"""The deterministic grading engine.

Every task's `grader.py` exposes a `grade(workdir: Path) -> GradeResult`
function (the name is configurable via manifest `grader_entrypoint`, default
`grade`). This module is what actually calls it, plus the shared,
reusable grading primitives every per-task grader is built from:

- `check_protected_paths`   — generic anti-cheat: fixture files an agent must
                               not edit (e.g. the failing test it's meant to
                               make pass) stayed byte-identical.
- `import_module_from_path` — load a specific .py file under a unique module
                               name, bypassing `sys.modules` caching so
                               grading ten different tasks' same-named
                               fixture files (or the same task graded twice
                               across two different workdirs) never imports
                               a stale cached copy.
- `run_pytest_in_workdir`   — copy hidden test file(s) into a produced
                               workdir and run them there with pytest.
- `compare_answer_json`     — data-driven comparison for research-style
                               tasks: the agent's `answer.json` vs. a
                               task's `answer_key.json`, with float
                               tolerance and case/whitespace-insensitive
                               string comparison.
"""
from __future__ import annotations

import filecmp
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, List, Optional

from pg_lib.types import GradeResult, Manifest

_MODULE_COUNTER = 0


def check_protected_paths(manifest: Manifest, workdir: Path) -> Optional[GradeResult]:
    """Fail the grade if any `manifest.protected_paths` entry was modified.

    Returns None (no verdict yet) when everything's untouched, so callers
    can chain it with `result = check_protected_paths(...) or grade(...)`.
    """
    for rel_path in manifest.protected_paths:
        original = manifest.fixture_path / rel_path
        produced = workdir / rel_path
        if not produced.is_file():
            return GradeResult(False, f"protected path missing from workdir: {rel_path}")
        if not filecmp.cmp(original, produced, shallow=False):
            return GradeResult(False, f"protected path was modified (not allowed): {rel_path}")
    return None


def import_module_from_path(file_path: Path, unique_name: Optional[str] = None):
    """Import a specific .py file as its own module, never via `sys.path` +
    a bare `import <name>` — that would resolve through `sys.modules` and
    could silently return a stale copy from a different workdir that
    happens to share a filename (e.g. two `calc.py` fixtures)."""
    global _MODULE_COUNTER
    _MODULE_COUNTER += 1
    module_name = unique_name or f"pg_sut_{_MODULE_COUNTER}_{file_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load module spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def load_grader_callable(manifest: Manifest):
    """Import `manifest.grader_path` and return its `grader_entrypoint`
    callable. Raises if the file doesn't import cleanly or the entrypoint
    is missing/not callable — used by both grading and `--dry-run`."""
    module = import_module_from_path(manifest.grader_path, unique_name=f"pg_grader_{manifest.id}")
    entrypoint = getattr(module, manifest.grader_entrypoint, None)
    if entrypoint is None or not callable(entrypoint):
        raise AttributeError(
            f"{manifest.grader}: no callable '{manifest.grader_entrypoint}' "
            f"(manifest.grader_entrypoint) found"
        )
    return entrypoint


def grade_task(manifest: Manifest, workdir: Path) -> GradeResult:
    """The single entrypoint `grade.py` and `run.py` both call.

    Order: protected-path check first (cheap, generic, catches the most
    common cheat) — only if it passes do we run the task's own grader.
    """
    protected_failure = check_protected_paths(manifest, workdir)
    if protected_failure is not None:
        return protected_failure

    try:
        grade_fn = load_grader_callable(manifest)
    except Exception as exc:  # noqa: BLE001 - a broken grader must FAIL the task, never crash the runner
        return GradeResult(False, f"grader failed to load: {exc}")

    try:
        result = grade_fn(workdir)
    except Exception as exc:  # noqa: BLE001 - same rationale: a grader bug is a FAIL, not an uncaught crash
        return GradeResult(False, f"grader raised an exception: {exc}")

    if not isinstance(result, GradeResult):
        return GradeResult(False, f"grader returned {type(result).__name__}, expected GradeResult")
    return result


def run_pytest_in_workdir(
    workdir: Path,
    test_files: Iterable[str],
    hidden_test_sources: Iterable[Path] = (),
    timeout_seconds: int = 60,
) -> GradeResult:
    """Run pytest over specific test file(s) inside a produced workdir.

    `test_files` are filenames already expected to exist in `workdir`
    (fixture-shipped tests for bug tasks). `hidden_test_sources` are
    absolute paths to test files that live at the *task* directory level
    (never shipped in `fixture/`) — they're copied into the workdir first,
    under their own basename, so they can import the agent's implementation
    module by relative import exactly like a real hidden test suite would.
    """
    copied: List[Path] = []
    for src in hidden_test_sources:
        dest = workdir / src.name
        shutil.copy2(src, dest)
        copied.append(dest)
    all_names = list(test_files) + [p.name for p in copied]

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *all_names],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return GradeResult(False, f"pytest timed out after {timeout_seconds}s", {"test_files": all_names})
    finally:
        for dest in copied:
            dest.unlink(missing_ok=True)

    passed = proc.returncode == 0
    tail = "\n".join((proc.stdout + "\n" + proc.stderr).splitlines()[-40:])
    reason = "pytest passed" if passed else f"pytest failed (exit {proc.returncode})"
    return GradeResult(passed, reason, {"test_files": all_names, "pytest_tail": tail})


def compare_answer_json(
    workdir: Path,
    answer_key_path: Path,
    answer_filename: str = "answer.json",
    float_tolerance: float = 1e-6,
) -> GradeResult:
    """Generic data-driven grading for research tasks: load the agent's
    `answer.json` and the task's private `answer_key.json`, and compare
    key-by-key with float tolerance and normalized string matching."""
    answer_path = workdir / answer_filename
    if not answer_path.is_file():
        return GradeResult(False, f"expected output file not found: {answer_filename}")

    try:
        actual = json.loads(answer_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return GradeResult(False, f"{answer_filename} is not valid JSON: {exc}")

    expected = json.loads(answer_key_path.read_text(encoding="utf-8"))
    mismatches = _diff_answers(expected, actual, float_tolerance)
    if mismatches:
        return GradeResult(False, f"{len(mismatches)} field(s) incorrect: {mismatches}", {"expected": expected, "actual": actual})
    return GradeResult(True, "all answer fields matched the answer key")


def _diff_answers(expected: Any, actual: Any, float_tolerance: float, path: str = "") -> List[str]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path or '<root>'}: expected an object"]
        mismatches: List[str] = []
        for key, exp_value in expected.items():
            child_path = f"{path}.{key}" if path else key
            if key not in actual:
                mismatches.append(f"{child_path}: missing")
                continue
            mismatches += _diff_answers(exp_value, actual[key], float_tolerance, child_path)
        return mismatches
    if _values_match(expected, actual, float_tolerance):
        return []
    return [f"{path or '<root>'}: expected {expected!r}, got {actual!r}"]


def _values_match(expected: Any, actual: Any, float_tolerance: float) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected == actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) <= float_tolerance
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().casefold() == actual.strip().casefold()
    return expected == actual
