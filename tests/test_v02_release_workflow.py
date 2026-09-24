"""Regression tests for .github/workflows/release.yml (v0.2.0).

Bug 1 (every Release run since v0.1.0 failed at Gate 1): actions/checkout re-fetches
`+<sha>:refs/tags/<tag>` for a tag push, which turns an annotated tag into a lightweight
ref, so Gate 1's `git cat-file -t "$TAG"` saw 'commit' and refused a correctly signed tag.
These tests reproduce checkout's two fetches against a local origin, then EXECUTE the
workflow's own steps between checkout and Gate 1, and assert the tag is annotated again.

Bug 2: Gate 3 ran `gitleaks git .` with gitleaks' default `--all`, so every fetched branch
was scanned instead of the history being released. The test executes Gate 3's run script
with a stub `gitleaks` on PATH and asserts it was asked to scan only the tag.

Guard: the tag name reaches the shell only through `env:`, never an inline
`${{ github.ref_name }}` inside a `run:` script (script injection via a crafted tag name).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"
TAG = "v9.8.7"

pytestmark = [
    pytest.mark.skipif(shutil.which("git") is None or shutil.which("bash") is None,
                       reason="needs git and bash"),
    # release.yml is Tess OS's own release pipeline; create-tess excludes it from every
    # scaffolded project (create-tess/src/ignore.js), where this file has nothing to test.
    pytest.mark.skipif(not RELEASE_YML.exists(), reason="no .github/workflows/release.yml in this project"),
]


def _steps() -> list:
    wf = yaml.safe_load(RELEASE_YML.read_text(encoding="utf-8"))
    return wf["jobs"]["release"]["steps"]


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


def _render_env(step: dict, tag: str) -> dict:
    """The step's env block as GitHub would evaluate it for a push of `tag`."""
    out = {}
    for k, v in (step.get("env") or {}).items():
        v = str(v).replace("${{ github.ref_name }}", tag)
        assert "${{" not in v or "secrets." in v or "runner.temp" in v, f"unexpected expression in env {k}: {v}"
        out[k] = v
    return out


def _run_step(step: dict, cwd: Path, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           **_render_env(step, TAG), **(extra_env or {})}
    return subprocess.run(["bash", "-e", "-c", step["run"]], cwd=str(cwd), env=env,
                          capture_output=True, text=True)


@pytest.fixture()
def checked_out_tag(tmp_path: Path) -> Path:
    """A clone left exactly as actions/checkout@v4 leaves it for a push of an annotated tag."""
    origin_work = tmp_path / "origin-work"
    origin_work.mkdir()
    _git(origin_work, "init", "-q")
    (origin_work / "f.txt").write_text("x\n")
    _git(origin_work, "add", "f.txt")
    _git(origin_work, "commit", "-q", "-m", "c1")
    _git(origin_work, "tag", "-a", TAG, "-m", "annotated release tag")
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(origin_work), str(origin)], check=True,
                   capture_output=True)
    ws = tmp_path / "workspace"
    ws.mkdir()
    _git(ws, "init", "-q")
    _git(ws, "remote", "add", "origin", str(origin))
    # checkout's first fetch (fetch-depth: 0, fetch-tags: true)
    _git(ws, "fetch", "-q", "--prune", "--no-recurse-submodules", "origin",
         "+refs/heads/*:refs/remotes/origin/*", "+refs/tags/*:refs/tags/*")
    sha = _git(ws, "rev-parse", f"{TAG}^{{commit}}")
    # checkout's second fetch: the tag ref does not resolve to the commit, so it re-fetches
    # +<sha>:refs/tags/<tag>, overwriting the annotated tag with a lightweight ref
    _git(ws, "fetch", "-q", "--no-tags", "--prune", "--no-recurse-submodules", "origin",
         f"+{sha}:refs/tags/{TAG}")
    _git(ws, "checkout", "-q", "--detach", sha)
    assert _git(ws, "cat-file", "-t", TAG) == "commit", "fixture must reproduce checkout's lightweight tag"
    return ws


def test_steps_before_gate1_restore_the_annotated_tag(checked_out_tag: Path):
    steps = _steps()
    names = [s.get("name", "") for s in steps]
    checkout = next(i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/checkout"))
    gate1 = next(i for i, n in enumerate(names) if n.startswith("Gate 1"))
    for step in steps[checkout + 1:gate1]:
        if "run" in step:
            r = _run_step(step, checked_out_tag)
            assert r.returncode == 0, f"step {step.get('name')!r} failed: {r.stderr}"
    assert _git(checked_out_tag, "cat-file", "-t", TAG) == "tag", (
        "after the workflow's pre-Gate-1 steps the release tag is still lightweight, so Gate 1 "
        "can never pass for a correctly signed annotated tag"
    )


def test_gate3_scans_only_the_history_of_the_tag(tmp_path: Path):
    step = next(s for s in _steps() if s.get("name", "").startswith("Gate 3"))
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    argv_file = tmp_path / "argv.txt"
    stub = stub_dir / "gitleaks"
    stub.write_text(f"#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > '{argv_file}'\n")
    stub.chmod(0o755)
    r = _run_step(step, tmp_path, {"PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}"})
    assert r.returncode == 0, r.stderr
    argv = argv_file.read_text().splitlines()
    assert f"--log-opts={TAG}" in argv, (
        f"Gate 3 must scan only the history reachable from the tag; gitleaks got {argv}"
    )


def test_ref_name_never_inlined_into_a_run_script():
    text = RELEASE_YML.read_text(encoding="utf-8")
    for step in _steps():
        run = step.get("run") or ""
        assert "${{" not in run, (
            f"step {step.get('name')!r} inlines an expression into its shell script; pass it via env:"
        )
    # every ref_name use is an env value
    for line in text.splitlines():
        if "github.ref_name" in line:
            assert re.match(r"^\s+TAG: \$\{\{ github\.ref_name \}\}\s*$", line), line
