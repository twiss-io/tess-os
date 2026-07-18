"""Path bootstrap for the telemetry test suite.

Deliberately NOT named `conftest.py`, `_paths.py`, `_spec_engine_paths.py`,
or `_orchestrator_paths.py` -- same collision reason those files document
for themselves: neither `tests/telemetry/` nor its siblings carry an
`__init__.py`, so pytest's default "prepend" import mode loads every
helper file under its bare module name regardless of directory; a new
sibling test directory reusing any existing basename would squat on
`sys.modules[...]` the exact way earlier collisions were caught
empirically. `tests/telemetry/` gets its own unique name for the same
reason.

`telemetry` is a plain top-level package directly under the repo root
(unlike `intent-router`/`spec-engine`, which are hyphenated directories
whose inner package name differs from the directory name) -- so `import
telemetry` resolves as soon as REPO_ROOT is on sys.path, exactly like
`import orchestrator` / `import connectors` already do; no
sibling-directory sys.path insertion is needed here.

Each test file in this directory does `import _telemetry_paths` (a
side-effecting import) before importing `telemetry`.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Defense-in-depth isolation, mirroring tests/orchestrator/
# _orchestrator_paths.py's own TESS_OS_TELEMETRY_DIR safety net (see that
# file's docstring for the full rationale). Every test in THIS directory
# passes an explicit `telemetry_dir=tmp_path/...` to every call it makes
# -- this is a safety net for any test that forgets to, so a missed
# explicit `telemetry_dir=` still cannot touch the real machine's own
# ~/.tess-os/telemetry/ by accident.
if "TESS_OS_TELEMETRY_DIR" not in os.environ:
    _telemetry_tmp_dir = tempfile.mkdtemp(prefix="telemetry-tests-")
    os.environ["TESS_OS_TELEMETRY_DIR"] = _telemetry_tmp_dir
    atexit.register(shutil.rmtree, _telemetry_tmp_dir, ignore_errors=True)
