"""The two scaffold conditions the matrix compares.

`bare`     — nothing beyond the task fixture. No CLAUDE.md, no conductor/
             doctrine, no roster, no guard hooks. Whatever the model does,
             it does unassisted.
`tess-os`  — the task fixture PLUS this repo's own governance surface,
             copied in verbatim: `CLAUDE.md` (the entry point), `conductor/`
             (doctrine), `agents/` (roster), `.claude/` (compiled agents,
             guard hooks, commands, skills), `core/` (contracts + policy).

Deliberately excludes `.tess/` (the upgrade engine) — the doctrine itself
says a fresh clone works without it ("Claude reads the doctrine directly
and the engine is committed" is about *upgrades*, not runtime), and this
harness must never depend on `.tess/bin/tessctl` at all, since another
agent may be actively editing it in a sibling clone.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

BARE = "bare"
TESS_OS = "tess-os"
ALL_SCAFFOLDS = (BARE, TESS_OS)

TESS_OS_SCAFFOLD_RELATIVE_PATHS: List[str] = [
    "CLAUDE.md",
    "conductor",
    "agents",
    ".claude",
    "core",
]


def scaffold_source_paths(repo_root: Path, scaffold: str) -> List[Path]:
    """Absolute paths to copy into a cell's workdir for the given scaffold.

    An empty list for `bare` is the whole point, not an oversight.
    """
    if scaffold == BARE:
        return []
    if scaffold == TESS_OS:
        return [repo_root / rel for rel in TESS_OS_SCAFFOLD_RELATIVE_PATHS]
    raise ValueError(f"unknown scaffold: {scaffold!r} (expected one of {ALL_SCAFFOLDS})")


def validate_tess_os_scaffold_available(repo_root: Path) -> List[str]:
    """Dry-run check: every path the tess-os scaffold needs actually exists
    under `repo_root`. Returns a list of problems (empty = OK)."""
    problems = []
    for path in scaffold_source_paths(repo_root, TESS_OS):
        if not path.exists():
            problems.append(f"tess-os scaffold source missing: {path}")
    return problems
