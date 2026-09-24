"""`onboard.py restore`: rebuild operator/profile.json from brain/brain.json.

operator/profile.json is gitignored and publish-clean-blocked, so a fresh
clone of an instance lacks it and `tessctl render` would fall back to the
default names. When a PyYAML-capable python3 is on PATH, restore goes through
`./tessctl set-operator` and `./tessctl rename` (which also re-render);
otherwise it writes the JSON file directly with the stdlib and says so.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, List

from . import state


def has_pyyaml() -> bool:
    try:
        done = subprocess.run(["python3", "-c", "import yaml"], capture_output=True, timeout=20)
        return done.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _tessctl(root: Path, args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run([str(root / "tessctl")] + args, cwd=str(root), capture_output=True,
                          text=True, timeout=300)


def run(root: Path, dry: bool = False) -> Dict[str, str]:
    brain = state.load_brain(root)
    if brain is None:
        raise state.BrainError("no brain/brain.json: nothing to restore from (onboard first)", 3)
    ident = brain.get("identity") or {}
    op, asst = ident.get("operator_name") or "", ident.get("assistant_name") or "Tess"
    if not op:
        raise state.BrainError("brain.json has no identity.operator_name", 3)
    current = state.read_operator_profile(root)
    if current.get("operator_name") == op and current.get("assistant_name") == asst:
        return {"result": "unchanged", "operator_name": op, "assistant_name": asst}
    if dry:
        return {"result": "would-restore", "operator_name": op, "assistant_name": asst}
    if (root / "tessctl").exists() and has_pyyaml():
        for args in (["set-operator", op], ["rename", asst]):
            done = _tessctl(root, args)
            if done.returncode != 0:
                raise state.BrainError("tessctl %s failed: %s" % (args[0], (done.stderr or done.stdout)[-400:]), 4)
        return {"result": "restored-via-tessctl", "operator_name": op, "assistant_name": asst}
    profile = dict(current)
    profile.update({"operator_name": op, "assistant_name": asst})
    profile.setdefault("pathway", ident.get("pathway") or "chief-of-staff")
    state.atomic_write(root / "operator" / "profile.json", json.dumps(profile, indent=2) + "\n")
    return {"result": "restored-json-only (install PyYAML, then run ./tessctl render)",
            "operator_name": op, "assistant_name": asst}
