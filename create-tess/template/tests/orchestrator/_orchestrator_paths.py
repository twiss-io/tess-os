"""Path bootstrap for the orchestrator test suite.

Deliberately NOT named `conftest.py` or `_paths.py`/`_spec_engine_paths.py`
(same collision reason those two files document for themselves): neither
`tests/orchestrator/` nor its siblings carry an `__init__.py`, so pytest's
default "prepend" import mode loads every helper file under its bare
module name regardless of directory — a third sibling test directory
reusing either existing basename would squat on `sys.modules[...]` exactly
the way the first two collisions were caught empirically. `tests/orchestrator/`
gets its own unique name for the same reason.

`orchestrator/__init__.py` itself already puts `intent-router/` and
`spec-engine/` onto `sys.path` (see its own module docstring) the moment
it is imported — this bootstrap only needs to add the REPO ROOT so `import
orchestrator` resolves in the first place.

Each test file in this directory does `import _orchestrator_paths` (a
side-effecting import) before importing `orchestrator`.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INTENT_ROUTER_ROOT = REPO_ROOT / "intent-router"
SPEC_ENGINE_ROOT = REPO_ROOT / "spec-engine"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EXAMPLE_ROUTING_TABLE = INTENT_ROUTER_ROOT / "routing_table.example.yaml"

# Defense-in-depth isolation, mirroring tests/spec_engine/_spec_engine_paths.py's
# own (see its docstring for the full rationale, including why this is a
# side-effecting import rather than a conftest.py autouse fixture). Every
# test in THIS directory already scopes LocalIdentityApprovalGate
# explicitly (identity_dir=tmp_path/"identity" on every construction) —
# this is a safety net for any test (this PR's new ones, or a future one)
# that forgets to, so a missed explicit identity_dir= still cannot touch
# the real machine's own ~/.tess-os/approval-identity/ by accident. An
# explicit identity_dir= argument always takes precedence.
if "TESS_OS_APPROVAL_IDENTITY_DIR" not in os.environ:
    _identity_tmp_dir = tempfile.mkdtemp(prefix="orchestrator-tests-approval-identity-")
    os.environ["TESS_OS_APPROVAL_IDENTITY_DIR"] = _identity_tmp_dir
    atexit.register(shutil.rmtree, _identity_tmp_dir, ignore_errors=True)

# Same defense-in-depth, same rationale, for telemetry (added alongside
# orchestrator.pipeline.run_pipeline()'s Hop 6 -- see telemetry/README.md
# and docs/TELEMETRY.md). Every test in this directory that exercises
# telemetry explicitly enables it against its OWN tmp_path-scoped
# telemetry_dir (never the default); this is a safety net so a test that
# forgets to still cannot touch the real machine's own
# ~/.tess-os/telemetry/ by accident -- and so every OTHER test in this
# suite (which never touches telemetry at all) keeps observing the
# default OFF/disabled state it already expects, scoped to a directory
# that is guaranteed empty rather than whatever happens to exist on the
# machine actually running the tests.
if "TESS_OS_TELEMETRY_DIR" not in os.environ:
    _telemetry_tmp_dir = tempfile.mkdtemp(prefix="orchestrator-tests-telemetry-")
    os.environ["TESS_OS_TELEMETRY_DIR"] = _telemetry_tmp_dir
    atexit.register(shutil.rmtree, _telemetry_tmp_dir, ignore_errors=True)
