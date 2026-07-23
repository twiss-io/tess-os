"""Shared teardown helper for SIGKILL-based kill-test child processes
(tess-os #165, reviewer follow-up on #164's DoD B.9 wedge-loop e2e).

Both `tests/orchestrator/test_e2e_wedge_loop.py`'s mid-`generate_app()`
kill test and `tests/spec_engine/test_codegen_atomic_staging.py`'s three
SIGKILL tests spawn a real child process that calls `tempfile.mkdtemp()`
for its own throwaway `TESS_OS_APPROVAL_IDENTITY_DIR` (and, for the e2e
wedge-loop test, `TESS_OS_TELEMETRY_DIR` too) before the parent SIGKILLs
it. SIGKILL is unblockable, so none of the child's own Python-level
cleanup (atexit, try/finally, context managers) ever runs -- and the
directory `tempfile.mkdtemp()` actually created (its exact path is
randomly suffixed INSIDE the child's own process, so the parent has no
way to predict it) is never removed by anyone. Low impact (OS-tmp
accumulation only, test-scope, no production path), but the pattern
existed unaddressed in `test_codegen_atomic_staging.py` first and #164
duplicated it into a second file, doubling it.

Fix: each child script prints a `KILL_TEST_TMPDIR:<path>` line (alongside
its existing `REACHED:`/`REACHED_SWAP_ASIDE` marker) for every
`tempfile.mkdtemp()` directory it creates, right after creating it and
BEFORE doing anything else that might get SIGKILLed mid-way. The parent's
own marker-reading loop feeds every line it reads off the child's stdout
through `KillTestTmpDirs.observe_line()`, which tracks any such path;
once the SIGKILL has landed and the test is done asserting against the
killed child's on-disk aftermath, `KillTestTmpDirs.cleanup()` removes
every tracked directory -- using the exact real path the child reported,
never a blind prefix-glob sweep of the shared system tempdir (a sweep
would risk deleting a genuinely in-flight parallel run of the same test,
e.g. under pytest-xdist, whose own mkdtemp() call could share the same
prefix).

Deliberately named `_kill_test_helpers.py`, not `conftest.py`: neither
`tests/orchestrator/` nor `tests/spec_engine/` (nor `tests/` itself)
carries an `__init__.py`, so pytest's default "prepend" import mode loads
every helper file under its bare module name regardless of directory --
see `tests/orchestrator/_orchestrator_paths.py`'s own docstring for the
collision this discipline avoids. `pytest.ini`'s `pythonpath = tests`
setting is what makes `import _kill_test_helpers` resolve from any test
file under `tests/`, the same mechanism `tests/_node_server.py` already
relies on for its own cross-directory reuse.
"""

from __future__ import annotations

import shutil
from pathlib import Path

MARKER_PREFIX = "KILL_TEST_TMPDIR:"


class KillTestTmpDirs:
    """Collects `tempfile.mkdtemp()` paths a SIGKILLed child process
    reported (via `MARKER_PREFIX`-prefixed stdout lines) and removes them
    all in `cleanup()`.

    Usage: construct one per test, call `observe_line(line)` on every raw
    line read off the child's stdout while polling for the child's own
    `REACHED`-style marker (it returns True and tracks the path if `line`
    was a tmp-dir marker -- the caller should treat that as "consumed,
    keep polling" rather than the `REACHED` marker it is separately
    looking for), then call `cleanup()` exactly once, in a `finally:`
    block, after the test is done asserting against the killed child's
    on-disk state.
    """

    def __init__(self) -> None:
        self._paths: list[str] = []

    def observe_line(self, line: str) -> bool:
        stripped = line.strip()
        if stripped.startswith(MARKER_PREFIX):
            self._paths.append(stripped[len(MARKER_PREFIX):])
            return True
        return False

    def cleanup(self) -> None:
        for raw in self._paths:
            shutil.rmtree(Path(raw), ignore_errors=True)
        self._paths.clear()
