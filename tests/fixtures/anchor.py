"""Shared test helper: a REAL enforcement anchor for a throwaway project.

The hooks start `.claude/hooks/run-pinned.py` as `python3 -I -B`, and -I
ignores PYTHONPATH, so tests/fixtures/fake_os_home cannot reach them: the
launcher reads the anchor under the real OS user record's home, exactly as in
production. `real_anchor(root)` records one there through the engine's own
`_anchor_write` (in an isolated interpreter, so it resolves the same home) and
the fixture removes that project's anchor directory and path marker after the
test. Every temp project has its own root commit and path, so nothing is
shared with a real Tess project. Production code has no test switch.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ENGINE = REPO / ".tess" / "bin" / "tessctl"
REAL_HOME = Path(subprocess.run(
    [sys.executable, "-I", "-c", "import os, pwd; print(pwd.getpwuid(os.getuid()).pw_dir)"],
    capture_output=True, text=True, check=True).stdout.strip())
PROJECTS = REAL_HOME / ".config" / "tess" / "projects"

_WRITE = (
    "import sys\n"
    "import importlib.machinery as m, importlib.util as u\n"
    "from pathlib import Path\n"
    "l = m.SourceFileLoader('tess_engine_anchor', sys.argv[1])\n"
    "s = u.spec_from_loader(l.name, l)\n"
    "e = u.module_from_spec(s)\n"
    "l.exec_module(e)\n"
    "print(e._anchor_write(Path(sys.argv[2]), sys.argv[3]))\n"
)


def write_real_anchor(root: Path, source: str = "test") -> Path:
    r = subprocess.run([sys.executable, "-I", "-B", "-c", _WRITE, str(ENGINE), str(root), source],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return Path(r.stdout.strip().splitlines()[-1])


def marker_path(root: Path) -> Path:
    key = hashlib.sha256(os.path.realpath(str(root)).encode()).hexdigest()
    return PROJECTS / "by-path" / f"{key}.json"


def forget_real_anchor(root: Path, anchor: Path | None) -> None:
    if anchor is not None and anchor.parent.parent == PROJECTS:
        shutil.rmtree(anchor.parent, ignore_errors=True)
    marker_path(root).unlink(missing_ok=True)


@pytest.fixture
def real_anchor():
    made: list = []

    def make(root: Path, source: str = "test") -> Path:
        path = write_real_anchor(root, source)
        made.append((root, path))
        return path

    yield make
    for root, path in made:
        forget_real_anchor(root, path)
