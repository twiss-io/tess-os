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

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INTENT_ROUTER_ROOT = REPO_ROOT / "intent-router"
SPEC_ENGINE_ROOT = REPO_ROOT / "spec-engine"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EXAMPLE_ROUTING_TABLE = INTENT_ROUTER_ROOT / "routing_table.example.yaml"
