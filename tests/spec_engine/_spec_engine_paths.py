"""Path bootstrap for the spec-engine test suite.

Deliberately NOT named `conftest.py` (same collision reason
`tests/intent_router/_paths.py` documents for its own file) AND
deliberately NOT named `_paths.py` either, despite that being
`tests/intent_router/`'s own convention: neither `tests/spec_engine/` nor
`tests/intent_router/` carries an `__init__.py`, so pytest's default
"prepend" import mode loads every helper file under its bare module name
regardless of directory — two sibling test directories each shipping a
file literally named `_paths.py` would collide exactly the same way two
`conftest.py` files would (whichever is collected first squats on
`sys.modules['_paths']`, and the second one's `import _paths` silently
resolves to the FIRST one's contents instead of its own). This was caught
empirically the same way: `python -m pytest` at repo root failed every
`tests/spec_engine/` test module with `ImportError` / `AttributeError`
until this file was renamed to something unique to this component.

Each test file in this directory does `import _spec_engine_paths` (a
side-effecting import that inserts `spec-engine/` onto `sys.path`) before
importing `spec_engine`.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COMPONENT_ROOT = REPO_ROOT / "spec-engine"
INTENT_ROUTER_ROOT = REPO_ROOT / "intent-router"
SCHEMA_DIR = COMPONENT_ROOT / "schema"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
EVAL_FIXTURES_DIR = COMPONENT_ROOT / "eval" / "fixtures"

if str(COMPONENT_ROOT) not in sys.path:
    sys.path.insert(0, str(COMPONENT_ROOT))

# Only needed by test_intent_router_bridge.py, but harmless to insert
# unconditionally — mirrors intent-router's own sys.path bootstrap so a
# test can `import intent_router` directly without a package install.
if INTENT_ROUTER_ROOT.is_dir() and str(INTENT_ROUTER_ROOT) not in sys.path:
    sys.path.insert(0, str(INTENT_ROUTER_ROOT))

# Test-suite-wide isolation (codegen-boundary hardening epic): as of this
# epic, spec_engine.pipeline.finalize_spec()/run_spec_engine() (and,
# transitively, spec_engine.gate_approval.sign_local_approval()/
# spec_builder.build_spec()) mint a genuine, HMAC-signed local approval by
# default — identity_dir=None resolves to spec_engine.gate_identity.
# default_identity_dir(), which would otherwise be the REAL machine's own
# ~/.tess-os/approval-identity/. Rather than threading identity_dir=
# through every one of this suite's many call sites individually, this
# side-effecting import (every test file in this directory already does
# `import _spec_engine_paths`) points default_identity_dir()'s own
# documented TESS_OS_APPROVAL_IDENTITY_DIR env-var override at a single
# throwaway directory for the WHOLE test session, cleaned up at process
# exit. Deliberately NOT a conftest.py autouse fixture (a per-test
# tmp_path-scoped conftest.py in this directory was tried and reverted —
# pytest's default "prepend" import mode imports EVERY conftest.py under
# its own bare module name too, exactly the same collision class
# `_spec_engine_paths.py`'s own docstring already documents for regular
# test/helper files; a second `conftest.py` here collided with the
# unrelated, pre-existing `tests/conftest.py` shared by the tessctl
# merge-engine suite and broke roughly 30 unrelated test files that do
# `from conftest import ...` expecting THAT file). Session-scoped (not
# per-test) is a deliberate, safe tradeoff here — every signed approval
# gets a fresh, random nonce (spec_engine.content.new_id("nonce"), 48 bits
# of entropy), so sharing one identity directory across this suite's many
# tests carries no meaningful collision or cross-test-leakage risk; an
# explicit `identity_dir=` argument on any individual call always
# overrides this default regardless.
if "TESS_OS_APPROVAL_IDENTITY_DIR" not in os.environ:
    _identity_tmp_dir = tempfile.mkdtemp(prefix="spec-engine-tests-approval-identity-")
    os.environ["TESS_OS_APPROVAL_IDENTITY_DIR"] = _identity_tmp_dir
    atexit.register(shutil.rmtree, _identity_tmp_dir, ignore_errors=True)
