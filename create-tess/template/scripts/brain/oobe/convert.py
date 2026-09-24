"""`onboard.py convert-clone`: turn a `git clone` of tess-os into an instance.

Renames `origin` to `upstream` when origin matches framework_remote_patterns
(so brain commits can never be pushed to the public framework repo), writes
brain/brain.json with onboarding status `pending` (which switches the
source-repo guard off for this clone), and asks for a private remote.
Never deletes or rewrites history, never pushes.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Dict, List

from . import state


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root)] + list(args), capture_output=True, text=True)


def remotes(root: Path) -> Dict[str, str]:
    out = {}
    for name in _git(root, "remote").stdout.split():
        out[name] = _git(root, "remote", "get-url", name).stdout.strip()
    return out


def is_framework(url: str, patterns: List[str]) -> bool:
    return any(re.search(p, url or "") for p in patterns)


def plan(root: Path) -> List[str]:
    if not state.is_source_repo(root):
        raise state.BrainError("convert-clone only runs in a fresh clone of the Tess OS source repo "
                               "(create-tess/package.json present, no brain/brain.json)", 3)
    steps = []
    rems = remotes(root)
    origin = rems.get("origin", "")
    if origin and is_framework(origin, state.FRAMEWORK_REMOTE_PATTERNS):
        if "upstream" in rems:
            raise state.BrainError("both origin (framework) and upstream exist; rename or remove one "
                                   "yourself, then re-run convert-clone", 3)
        steps.append("rename remote origin -> upstream (%s)" % origin)
    steps.append("write brain/brain.json with onboarding status pending")
    steps.append("then: create a PRIVATE repository and run `git remote add origin <url>`")
    return steps


def run(root: Path, yes: bool) -> List[str]:
    steps = plan(root)
    if not yes:
        return steps
    rems = remotes(root)
    if rems.get("origin") and is_framework(rems["origin"], state.FRAMEWORK_REMOTE_PATTERNS):
        done = _git(root, "remote", "rename", "origin", "upstream")
        if done.returncode != 0:
            raise state.BrainError("git remote rename failed: %s" % done.stderr.strip(), 4)
    brain = state.default_brain(root)
    brain["remote"]["name"] = "origin"
    state.save_brain(root, brain)
    return steps
