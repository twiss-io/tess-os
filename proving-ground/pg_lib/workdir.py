"""Stage a fresh, isolated working directory for one (cell, task, attempt).

Nothing here ever touches the actual tess-os repo checkout — it only reads
from it (fixture + scaffold sources) and writes into a caller-supplied,
disposable destination root.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from pg_lib.scaffolds import scaffold_source_paths
from pg_lib.types import Manifest


def stage_workdir(manifest: Manifest, scaffold: str, repo_root: Path, dest_root: Path, cell_id: str) -> Path:
    """Create `dest_root/<cell_id>/` containing the task's fixture files
    plus (for `tess-os`) the governance scaffold. Safe to call repeatedly
    with the same `cell_id` — any prior contents are wiped first, so a
    retried attempt always starts from a clean fixture, never from a
    previous attempt's edits."""
    workdir = dest_root / cell_id
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    _copy_directory_contents(manifest.fixture_path, workdir)
    for source in scaffold_source_paths(repo_root, scaffold):
        _copy_scaffold_entry(source, workdir)
    return workdir


def _copy_directory_contents(src_dir: Path, dest_dir: Path) -> None:
    for item in sorted(src_dir.iterdir()):
        target = dest_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _copy_scaffold_entry(src: Path, dest_dir: Path) -> None:
    if not src.exists():
        return
    target = dest_dir / src.name
    if src.is_dir():
        shutil.copytree(src, target, dirs_exist_ok=True)
    else:
        shutil.copy2(src, target)
