"""The one place proving-ground's root paths are computed.

Every other module (`grade.py`, `run.py`, `pg_lib/dry_run.py`, the test
suite) imports these rather than re-deriving `Path(__file__).resolve()...`
in five different places with five chances to get the `.parent` count
wrong.
"""
from __future__ import annotations

from pathlib import Path

PROVING_GROUND_ROOT = Path(__file__).resolve().parent.parent
TASKS_ROOT = PROVING_GROUND_ROOT / "tasks"
REPO_ROOT_DEFAULT = PROVING_GROUND_ROOT.parent
RESULTS_ROOT = PROVING_GROUND_ROOT / "results"
