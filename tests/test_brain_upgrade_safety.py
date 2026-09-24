"""Upgrade safety (spec 13, G12, acceptance O6): framework lifecycle commands never touch the brain.

In a create-tess-shaped instance that has been onboarded, the sha256 of every
brain file and of the brain-onboard skill copies is identical before and after
`tessctl render`, `tessctl restore` and `tessctl doctor --fix`, and
`tessctl restore --dry-run` never lists a brain path. Needs PyYAML (tessctl).
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict

import pytest

import _brain_oobe_helpers as h

WATCHED = ("brain", ".agents/skills/brain-onboard", ".claude/skills/brain-onboard")
BRAIN_PATH = re.compile(r"(^|\s)(brain/|\.agents/skills/brain-|\.claude/skills/brain-)")


def hashes(root: Path) -> Dict[str, str]:
    out = {}
    for top in WATCHED:
        for path in sorted((root / top).rglob("*")):
            if path.is_file():
                out[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def tessctl(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(root / ".tess" / "bin" / "tessctl")] + list(args),
                          cwd=str(root), capture_output=True, text=True, timeout=600,
                          env=h.env({"TESS_ROOT": str(root)}))


@pytest.fixture(scope="module")
def onboarded(tmp_path_factory):
    root = h.full_instance(tmp_path_factory.mktemp("upgrade"), operator="Mira Okafor")
    done = h.onboard_fixture(root, "agency-solo")
    assert done.returncode == 0, done.stdout + done.stderr
    assert h.git(root, "status", "--porcelain").stdout == ""
    return root


def test_render_restore_doctor_fix_leave_brain_bytes_identical(onboarded):
    before = hashes(onboarded)
    assert any(p.startswith("brain/clients/") for p in before)
    assert ".claude/skills/brain-onboard/SKILL.md" in before
    for args in (["render"], ["restore"], ["doctor", "--fix"]):
        done = tessctl(onboarded, *args)
        assert done.returncode == 0, (args, done.stdout[-2000:], done.stderr[-2000:])
    assert hashes(onboarded) == before


def test_restore_dry_run_lists_no_brain_path(onboarded):
    done = tessctl(onboarded, "restore", "--dry-run")
    assert done.returncode == 0, done.stdout + done.stderr
    hits = [ln for ln in (done.stdout + done.stderr).splitlines() if BRAIN_PATH.search(ln)]
    assert hits == []


def test_doctor_is_ok_after_onboarding(onboarded):
    done = tessctl(onboarded, "doctor")
    assert done.stdout.strip().splitlines()[-1].startswith("doctor: OK"), done.stdout[-2000:]
