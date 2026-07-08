"""Proves the pytest-hijack cheat is closed.

HIGH finding (Fable, reproduced end-to-end): `run_pytest_in_workdir` ran
`python -m pytest -q <files>` with `cwd=workdir` and no plugin/conftest
isolation. An agent under test could drop a `conftest.py` with a
`pytest_runtest_makereport` hook that flips every failed test to passed
into its workdir, forcing `grade_task` to report PASS on an unfixed bug —
without touching the protected test file at all, so the existing
anti-cheat check (`check_protected_paths`) never even fires.

This module is the exact case the rest of the grader test suite dodged:
every other test in `test_graders_*` only ever exercises "did the agent's
*implementation* file change", never "did the agent plant a file the
grading harness itself would blindly execute."
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pg_lib.grading import PYTEST_HIJACK_FILENAMES, detect_pytest_hijack_files, grade_task
from pg_lib.paths import REPO_ROOT_DEFAULT
from pg_lib.scaffolds import TESS_OS_SCAFFOLD_RELATIVE_PATHS

# The real, live attack payload: a hookwrapper that intercepts every
# TestReport at the "call" phase and rewrites failed -> passed. This is
# not a toy — it's exactly what closed 01's fixture's failing test to
# green in the pre-fix reproduction.
FAIL_TO_PASS_CONFTEST = """
import pytest

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" and rep.failed:
        rep.outcome = "passed"
        rep.longrepr = None
"""


def test_unfixed_bug_plus_hijack_conftest_still_fails_grading(stage_task):
    """The exact reproduced attack: task 01's bug is left UNFIXED, and the
    fail->pass conftest hook is planted alongside it. Before the fix, this
    combination made `grade_task` return PASS on a broken implementation.
    It must now FAIL, and the reason must name the cheat, not just
    incidentally report a pytest failure."""
    manifest, workdir = stage_task("01-bug-average-empty-list")
    # calc.py is left exactly as shipped -- the ZeroDivisionError bug is
    # still there. Only the hijack file is added.
    (workdir / "conftest.py").write_text(FAIL_TO_PASS_CONFTEST)

    result = grade_task(manifest, workdir)

    assert result.passed is False
    assert "cheat-attempt" in result.reason.lower()
    assert "conftest.py" in result.reason


def test_hijack_conftest_defeats_a_hidden_test_task_too(stage_task):
    """Same attack against a hidden-test-graded task (03), proving the
    fix isn't specific to the fixture-shipped-test style — both flavors
    of pytest-graded task funnel through the same hardened
    `run_pytest_in_workdir`."""
    manifest, workdir = stage_task("03-feature-token-bucket-ratelimiter")
    # ratelimiter.py is left as the unimplemented stub (raises
    # NotImplementedError) -- only the hijack file is added.
    (workdir / "conftest.py").write_text(FAIL_TO_PASS_CONFTEST)

    result = grade_task(manifest, workdir)

    assert result.passed is False
    assert "cheat-attempt" in result.reason.lower()


def test_legitimate_correct_fix_with_no_hijack_file_still_passes(stage_task):
    """Sanity control: the hardening must not collaterally break a real,
    honest fix that plants no stray files. Locks in requirement #1 — the
    task's own hidden/fixture test suite still runs correctly under
    `--noconftest` / `-I`."""
    manifest, workdir = stage_task("01-bug-average-empty-list")
    (workdir / "calc.py").write_text(
        "def average(values):\n"
        "    if not values:\n"
        "        return 0.0\n"
        "    return sum(values) / len(values)\n"
    )
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason


@pytest.mark.parametrize("filename", sorted(PYTEST_HIJACK_FILENAMES))
def test_detect_pytest_hijack_files_flags_every_known_vector(tmp_path, filename):
    """Direct unit test of the detector for each of the six vectors named
    in the finding: conftest.py, pytest.ini, tox.ini, sitecustomize.py,
    setup.cfg, pyproject.toml."""
    (tmp_path / filename).write_text("# planted\n")
    found = detect_pytest_hijack_files(tmp_path)
    assert found == [filename]


def test_detect_pytest_hijack_files_clean_workdir_reports_nothing(stage_task):
    """A workdir holding only what a task actually ships must never false-
    positive."""
    _manifest, workdir = stage_task("01-bug-average-empty-list")
    assert detect_pytest_hijack_files(workdir) == []


def test_tess_os_scaffold_never_legitimately_contains_a_hijack_filename():
    """Guards the detector's false-positive-free claim against future
    scaffold changes: if `conductor/`, `agents/`, `.claude/`, or `core/`
    ever grows a `conftest.py`/`pytest.ini`/etc. of its own, the `tess-os`
    scaffold cells would start failing every pytest-graded task with a
    false cheat-attempt flag. This test fails loudly, at authoring time,
    before that ever reaches a real matrix run."""
    hits = []
    for rel in TESS_OS_SCAFFOLD_RELATIVE_PATHS:
        source = REPO_ROOT_DEFAULT / rel
        if source.is_dir():
            hits += [
                str(p.relative_to(REPO_ROOT_DEFAULT))
                for p in source.rglob("*")
                if p.is_file() and p.name in PYTEST_HIJACK_FILENAMES
            ]
        elif source.is_file() and source.name in PYTEST_HIJACK_FILENAMES:
            hits.append(str(source.relative_to(REPO_ROOT_DEFAULT)))
    assert hits == []


def test_hidden_test_source_filenames_are_never_hijack_filenames():
    """The hijack check runs before hidden test sources are copied into
    the workdir (see `run_pytest_in_workdir`), so a legitimate hidden test
    file could never trip its own scan even if the check ran after the
    copy. This test locks that invariant in directly, so nobody
    "fixes" a future false positive by reordering the copy ahead of the
    check."""
    from pg_lib.manifest import load_manifest
    from pg_lib.paths import TASKS_ROOT

    for task_dir in sorted(TASKS_ROOT.iterdir()):
        if not task_dir.is_dir():
            continue
        manifest = load_manifest(task_dir)
        for hidden_path in manifest.hidden_test_paths():
            assert hidden_path.name not in PYTEST_HIJACK_FILENAMES
