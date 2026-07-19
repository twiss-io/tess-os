"""
Phase 0.2 — proves the #105/#111 data-leak fence (docs/STATE_LAYER.md's
four-part fence: never_touch, gitignore, publish-clean, scaffold-empty)
still holds for the TASK STORE + ACCOUNTABILITY LEDGER's OWN real,
CLI-produced content, not just the synthetic placeholder files
tests/test_gitignore_reconciliation.py / tests/test_publish_clean_gate.py
already cover generically for every `.tess/state/**` subdir.

This file writes a REAL task (`tessctl tasks new`) and a REAL ledger event
(`tessctl log append`) into an actual git working tree, then proves:
  1. `git add -A` never stages either file (content-level .gitignore fence,
     no pre-commit hook installed at all — the exact issue #110 gap).
  2. Force-adding either file (`git add -f`, simulating a bypass) is still
     BLOCKED by `tessctl doctor --publish-clean` (the commit-side control,
     independent of gitignore state).
  3. `tessctl doctor`/`verify`/`lock --check` never mention `.tess/state/**`
     at all — this region's OWN new files are exactly as invisible to the
     keystone integrity machinery as `missions/**` already is.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT, ENGINE_SRC, MANIFEST_SRC

HAS_GIT = shutil.which("git") is not None
pytestmark = pytest.mark.skipif(not HAS_GIT, reason="git required")

CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"


def _git(root, *args, check=True):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@tess.test",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@tess.test",
    }
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}\n{r.stdout}")
    return r


def _run_tessctl(root, *args):
    env = {**os.environ, "TESS_ROOT": str(root)}
    return subprocess.run(
        [sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
        cwd=str(root), env=env, capture_output=True, text=True,
    )


@pytest.fixture
def real_git_root(tmp_path):
    """A real git repo seeded with THIS repo's own .gitignore + the real
    manifest + a real engine copy + the two new contract schemas + the
    empty .tess/state/{tasks,ledger,locks}/.gitkeep scaffold — i.e. what a
    genuine fresh instance's committed history looks like BEFORE any real
    task/ledger data is written. No pre-commit hook installed (the exact
    issue #110 gap: gitignore must hold even with the opt-in hook absent)."""
    root = tmp_path / "os"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@tess.test")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")

    shutil.copy2(REPO_ROOT / ".gitignore", root / ".gitignore")
    shutil.copy2(MANIFEST_SRC, root / "tess.manifest.json")

    contracts_dir = root / "core" / "contracts"
    contracts_dir.mkdir(parents=True)
    for f in ("task.schema.json", "ledger-event.schema.json"):
        shutil.copy2(CONTRACTS_SRC / f, contracts_dir / f)

    bin_dir = root / ".tess" / "bin"
    bin_dir.mkdir(parents=True)
    dst_engine = bin_dir / "tessctl"
    shutil.copy2(ENGINE_SRC, dst_engine)
    os.chmod(dst_engine, 0o755)

    for sub in ("memory", "tasks", "ledger", "locks"):
        d = root / ".tess" / "state" / sub
        d.mkdir(parents=True)
        (d / ".gitkeep").write_text("", encoding="utf-8")

    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed: gitignore + manifest + engine + contracts + empty state scaffold")
    return root


def test_real_task_file_never_staged_by_git_add_dash_a(real_git_root):
    r = _run_tessctl(real_git_root, "tasks", "new", "Real fence-test task", "--harness", "claude-code")
    assert r.returncode == 0, r.stdout + r.stderr
    task_id = r.stdout.splitlines()[0].split("—")[1].strip()
    rel = f".tess/state/tasks/{task_id}.json"
    assert (real_git_root / rel).exists()

    _git(real_git_root, "add", "-A")
    staged = _git(real_git_root, "diff", "--cached", "--name-only").stdout.split()
    assert rel not in staged, f"a REAL task file ({rel}) must not be staged by a bare `git add -A`"

    status = _git(real_git_root, "status", "--porcelain").stdout
    assert rel not in status, f"{rel} must not surface in `git status` at all"


def test_real_ledger_shard_never_staged_by_git_add_dash_a(real_git_root):
    r = _run_tessctl(
        real_git_root, "log", "append", "--origin", "ada", "--event", "dispatch",
        "--summary", "real fence-test ledger event", "--harness", "claude-code",
    )
    assert r.returncode == 0, r.stdout + r.stderr

    ledger_files = list((real_git_root / ".tess" / "state" / "ledger").glob("*.jsonl"))
    assert len(ledger_files) == 1
    rel = f".tess/state/ledger/{ledger_files[0].name}"

    _git(real_git_root, "add", "-A")
    staged = _git(real_git_root, "diff", "--cached", "--name-only").stdout.split()
    assert rel not in staged, f"a REAL ledger shard ({rel}) must not be staged by a bare `git add -A`"


def test_real_task_file_blocked_by_publish_clean_gate_when_force_added(real_git_root, engine):
    r = _run_tessctl(real_git_root, "tasks", "new", "Force-add fence-test task", "--harness", "claude-code")
    assert r.returncode == 0, r.stdout + r.stderr
    task_id = r.stdout.splitlines()[0].split("—")[1].strip()
    rel = f".tess/state/tasks/{task_id}.json"

    # Simulate a bypass of the gitignore fence (e.g. `git add -f`) — the
    # SECOND, independent control (the commit-side publish-clean gate) must
    # still refuse this path regardless of gitignore state.
    _git(real_git_root, "add", "-f", rel)
    manifest = engine.load_manifest(real_git_root)
    violations = engine._publish_clean_violations(real_git_root, manifest, scope="staged")
    flagged = {v[0] for v in violations}
    assert rel in flagged, f"a force-added REAL task file ({rel}) must be flagged by the publish-clean gate"


def test_real_ledger_shard_blocked_by_publish_clean_gate_when_force_added(real_git_root, engine):
    r = _run_tessctl(
        real_git_root, "log", "append", "--origin", "ada", "--event", "dispatch",
        "--summary", "force-add fence-test ledger event", "--harness", "claude-code",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    ledger_files = list((real_git_root / ".tess" / "state" / "ledger").glob("*.jsonl"))
    rel = f".tess/state/ledger/{ledger_files[0].name}"

    _git(real_git_root, "add", "-f", rel)
    manifest = engine.load_manifest(real_git_root)
    violations = engine._publish_clean_violations(real_git_root, manifest, scope="staged")
    flagged = {v[0] for v in violations}
    assert rel in flagged, f"a force-added REAL ledger shard ({rel}) must be flagged by the publish-clean gate"


def test_real_task_and_ledger_activity_invisible_to_doctor_verify_lock_check(real_git_root):
    """Mirrors test_mission_ledger.py's test_missions_dir_invisible_to_
    doctor_verify_lock_check for missions/** — proves `.tess/state/tasks/**`
    and `.tess/state/ledger/**` get the SAME invisibility from the keystone
    integrity machinery even after genuine task/ledger activity, using the
    REAL repo tree (not a synthetic root) so `doctor`'s full lock-entry-
    driven scan runs against everything this PR actually added, including
    the new task.schema.json/ledger-event.schema.json contract entries."""
    dst = real_git_root.parent / "real_repo_copy"
    ignore = shutil.ignore_patterns(".git", "tests", ".pytest_cache", "__pycache__", ".github")
    shutil.copytree(REPO_ROOT, dst, ignore=ignore)

    r_new = _run_tessctl(dst, "tasks", "new", "Doctor-visibility check", "--harness", "claude-code")
    assert r_new.returncode == 0, r_new.stdout + r_new.stderr
    r_log = _run_tessctl(
        dst, "log", "append", "--origin", "ada", "--event", "dispatch",
        "--summary", "doctor-visibility ledger event", "--harness", "claude-code",
    )
    assert r_log.returncode == 0, r_log.stdout + r_log.stderr

    d = _run_tessctl(dst, "doctor")
    assert d.returncode == 0, d.stdout + d.stderr
    assert ".tess/state/" not in d.stdout

    v = _run_tessctl(dst, "verify")
    assert v.returncode == 0, v.stdout + v.stderr

    lc = _run_tessctl(dst, "lock", "--check")
    assert lc.returncode == 0, lc.stdout + lc.stderr

    manifest = json.loads((REPO_ROOT / "tess.manifest.json").read_text(encoding="utf-8"))
    assert ".tess/state/**" in manifest["never_touch"]
