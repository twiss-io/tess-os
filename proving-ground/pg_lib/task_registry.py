"""Discover and validate every task under `proving-ground/tasks/`."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from pg_lib.manifest import ManifestError, load_manifest
from pg_lib.types import Manifest


def discover_task_dirs(tasks_root: Path) -> List[Path]:
    """Every immediate subdirectory of `tasks/` that contains a manifest.yaml.

    Sorted by name so task ordering (and therefore report ordering) is
    deterministic across machines and runs.
    """
    if not tasks_root.is_dir():
        return []
    return sorted(
        p for p in tasks_root.iterdir()
        if p.is_dir() and (p / "manifest.yaml").is_file()
    )


def load_all_manifests(tasks_root: Path) -> Tuple[Dict[str, Manifest], List[str]]:
    """Load every task manifest. Never raises — collects errors instead.

    Returns (id -> Manifest for every task that validated, [error strings]).
    This is the function `--dry-run` and the unit tests both call: a task
    suite is only as trustworthy as its worst manifest, so one bad task
    must never silently disappear from validation output.
    """
    manifests: Dict[str, Manifest] = {}
    errors: List[str] = []
    for task_dir in discover_task_dirs(tasks_root):
        try:
            manifest = load_manifest(task_dir)
        except ManifestError as exc:
            errors.append(str(exc))
            continue
        manifests[manifest.id] = manifest
    return manifests, errors


def resolve_task_ids(tasks_root: Path, requested: List[str]) -> List[str]:
    """Expand a `--tasks` CLI value ("all" or a comma-split id list) against
    what's actually on disk, raising on any id that doesn't exist — a typo
    in `--tasks` must fail loudly, not silently run zero tasks."""
    all_ids = sorted(p.name for p in discover_task_dirs(tasks_root))
    if not requested or requested == ["all"]:
        return all_ids
    unknown = [t for t in requested if t not in all_ids]
    if unknown:
        raise ValueError(f"unknown task id(s): {unknown}. Known task ids: {all_ids}")
    return requested
