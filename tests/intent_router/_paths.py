"""Path bootstrap + shared fixtures for the intent-router test suite.

Deliberately named `_paths.py`, NOT `conftest.py`. The existing root
`tests/conftest.py` is imported by ~30 pre-existing test modules via a
bare `from conftest import ...` — this works because `tests/` carries no
`__init__.py`, so pytest's default ("prepend") import mode inserts that
directory onto `sys.path` and loads the file under the bare module name
`conftest`. A SECOND file also literally named `conftest.py`, nested
under `tests/intent_router/` (which likewise carries no `__init__.py`),
would import under that SAME bare name `conftest` and squat on
`sys.modules['conftest']` — breaking every pre-existing `from conftest
import ...` in the root suite the moment collection order picks this one
up first (this was caught empirically: `python -m pytest` at repo root
failed 31 unrelated test modules with `ImportError: cannot import name
... from 'conftest'` until this file was renamed away from `conftest.py`).

Each test file in this directory does `import _paths` (a side-effecting
import that inserts `intent-router/` onto `sys.path`) before importing
`intent_router`, then can optionally also do
`from _paths import example_routing_table, example_routing_table_path`
to reuse the two fixtures below (importing a fixture function into a test
module's namespace is a pytest-supported way to share fixtures without a
conftest.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COMPONENT_ROOT = REPO_ROOT / "intent-router"
EXAMPLE_ROUTING_TABLE = COMPONENT_ROOT / "routing_table.example.yaml"

if str(COMPONENT_ROOT) not in sys.path:
    sys.path.insert(0, str(COMPONENT_ROOT))


@pytest.fixture()
def example_routing_table_path() -> Path:
    return EXAMPLE_ROUTING_TABLE


@pytest.fixture()
def example_routing_table():
    from intent_router import RoutingTable

    return RoutingTable.load(EXAMPLE_ROUTING_TABLE)
