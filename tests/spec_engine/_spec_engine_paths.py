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

import sys
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
