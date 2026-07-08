"""Shared pytest fixtures for the proving-ground test suite.

Note: this `tests/` directory is intentionally OUTSIDE the repo's own
`pytest.ini` `testpaths = tests` (that points at the top-level `tests/`,
the tessctl engine suite). Run this suite explicitly:

    python -m pytest proving-ground/tests/

`pytest.ini`'s `testpaths` only applies when pytest is invoked with no
path arguments — passing this directory explicitly always works.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

PROVING_GROUND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROVING_GROUND_ROOT))

from pg_lib.manifest import load_manifest  # noqa: E402
from pg_lib.paths import TASKS_ROOT  # noqa: E402
from pg_lib.types import Manifest  # noqa: E402


@pytest.fixture
def stage_task(tmp_path):
    """`stage_task("01-bug-average-empty-list")` -> (Manifest, workdir Path)
    with a fresh copy of that task's fixture/ contents, ready to be
    mutated by a test (as a "hand-authored solution") and graded."""

    def _stage(task_id: str):
        manifest: Manifest = load_manifest(TASKS_ROOT / task_id)
        workdir = tmp_path / task_id
        shutil.copytree(manifest.fixture_path, workdir)
        return manifest, workdir

    return _stage
