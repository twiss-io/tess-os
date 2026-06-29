"""
D2 regression — scaffold-default.sh must preserve the working directory across
the dependency-install step so a RELATIVE project path still resolves correctly.

The buggy version ran a bare `cd "$PROJECT_PATH"` for `pnpm install` and never
restored the CWD. For a relative PROJECT_PATH (e.g. `./my-app`):
  * `os.path.realpath("$PROJECT_PATH")` (registry write) resolved against the
    now-changed CWD -> a wrong, doubly-nested path stored in the registry, and
  * `find "$PROJECT_PATH" | wc -l` (summary) ran from inside the project dir ->
    `find` errored on the missing relative path -> under `set -euo pipefail` the
    whole script ABORTED *after* the project was already created (a successful
    scaffold reported as a failure).

The fix runs the install in a subshell, so the parent CWD is preserved.

Network-free: `pnpm` is stubbed via a PATH shim so no real install runs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
STARTER_KIT = REPO_ROOT / "starter"
SCRIPT = STARTER_KIT / "scripts" / "scaffold-default.sh"

pytestmark = pytest.mark.skipif(
    not (
        SCRIPT.exists()
        and shutil.which("bash")
        and shutil.which("git")
        and shutil.which("python3")
    ),
    reason="scaffold-default.sh + bash + git + python3 required",
)


def _pnpm_shim(bindir: Path) -> None:
    """A no-op `pnpm` so the install step needs no network."""
    bindir.mkdir(parents=True, exist_ok=True)
    shim = bindir / "pnpm"
    shim.write_text("#!/usr/bin/env bash\nexit 0\n")
    shim.chmod(0o755)


def _run_scaffold(tmp_path: Path, project_arg: str):
    home = tmp_path / "home"
    home.mkdir()
    workdir = tmp_path / "work"
    workdir.mkdir()
    shim = tmp_path / "shim"
    _pnpm_shim(shim)

    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{shim}{os.pathsep}{os.environ.get('PATH', '')}",
        # Deterministic commit identity (no reliance on global git config).
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    proc = subprocess.run(
        ["bash", str(SCRIPT), project_arg, "my-app", str(STARTER_KIT)],
        cwd=str(workdir),
        env=env,
        capture_output=True,
        text=True,
    )
    registry = home / ".claude" / "starter-kit-projects.json"
    return proc, workdir, registry


def test_relative_project_path_completes_and_registers_absolute_path(tmp_path):
    # A RELATIVE project path is the trigger for the bug.
    proc, workdir, registry = _run_scaffold(tmp_path, "./my-app")

    # (1) The script must COMPLETE — the summary `find` no longer aborts it.
    assert proc.returncode == 0, (
        f"scaffold aborted (rc={proc.returncode}).\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )

    # The project was actually created at <workdir>/my-app.
    project_dir = workdir / "my-app"
    assert project_dir.is_dir(), "project dir was not created"

    # (2) The registry must store the CORRECT absolute path — the realpath of the
    # created project, NOT a nested `.../my-app/my-app` from a leaked CWD change.
    assert registry.is_file(), "project registry was not written"
    data = json.loads(registry.read_text())
    stored = data["projects"][-1]["path"]
    expected = os.path.realpath(project_dir)
    assert stored == expected, (
        f"registry stored wrong path: {stored!r} (expected {expected!r})"
    )
    # Guard explicitly against the buggy doubly-nested resolution.
    assert not stored.rstrip("/").endswith(
        os.path.join("my-app", "my-app")
    ), f"registry stored a doubly-nested path: {stored!r}"
