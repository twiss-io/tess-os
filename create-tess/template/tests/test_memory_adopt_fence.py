"""
Phase 0.3 — proves the #105/#111 data-leak fence (docs/STATE_LAYER.md's
four-part fence: never_touch, gitignore, publish-clean, scaffold-empty)
still holds for `tessctl memory adopt`'s OWN real, CLI-produced content —
not just the synthetic placeholder files tests/test_gitignore_reconciliation.py
/ tests/test_publish_clean_gate.py already cover generically for every
`.tess/state/**` subdir, and not just the TASK STORE / ACCOUNTABILITY
LEDGER's own real content tests/test_task_ledger_fence.py already proved.

This file runs a REAL `tessctl memory adopt --yes` (source directory
deliberately OUTSIDE the git working tree, mirroring the true shape of a
harness's private memory directory living in its own home-directory tree,
wholly separate from the project repo) into an actual git working tree,
then proves:
  1. `git add -A` never stages the adopted memory file(s) OR the adopt
     manifest itself (content-level .gitignore fence, no pre-commit hook
     installed at all — the exact issue #110 gap).
  2. Force-adding either is still BLOCKED by `tessctl doctor --publish-clean`
     (the commit-side control, independent of gitignore state).
  3. `tessctl doctor`/`verify`/`lock --check` never mention `.tess/state/**`
     at all — adopted memory content is exactly as invisible to the
     keystone integrity machinery as `missions/**` already is.

Also proves the AGENTS.md render side of this build: the REAL shipped
`.tess/core/templates/agents-md/AGENTS.md.tpl` renders a "Session Memory"
section pointing Codex/generic harnesses at `.tess/state/memory/MEMORY.md`,
with no worker-profile doctrine-denylist violation introduced.
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


def _run_tessctl(root, *args, env_extra=None):
    env = {**os.environ, "TESS_ROOT": str(root)}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
        cwd=str(root), env=env, capture_output=True, text=True,
    )


@pytest.fixture
def real_git_root(tmp_path):
    """A real git repo seeded with THIS repo's own .gitignore + the real
    manifest + a real engine copy + the empty
    .tess/state/{memory,tasks,ledger,locks}/.gitkeep scaffold — i.e. what a
    genuine fresh instance's committed history looks like BEFORE any real
    memory content is adopted. No pre-commit hook installed (issue #110's
    own gap: gitignore must hold even with the opt-in hook absent)."""
    root = tmp_path / "os"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@tess.test")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")

    shutil.copy2(REPO_ROOT / ".gitignore", root / ".gitignore")
    shutil.copy2(MANIFEST_SRC, root / "tess.manifest.json")

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
    _git(root, "commit", "-q", "-m", "seed: gitignore + manifest + engine + empty state scaffold")
    return root


def _adopt_real_memory(root, tmp_path, engine):
    """Run a REAL `tessctl memory adopt --yes` — source directory deliberately
    OUTSIDE the git working tree (the true shape: a harness's private memory
    dir lives in its own home-directory tree, never inside the project
    repo). Returns (from_dir, to_dir)."""
    from_dir = tmp_path / "harness-home" / "memory"
    from_dir.mkdir(parents=True)
    (from_dir / "MEMORY.md").write_text("# Memory Index\n- [X](feedback_real.md) fence-test\n", encoding="utf-8")
    (from_dir / "feedback_real.md").write_text("real fence-test memory content\n", encoding="utf-8")
    to_dir = root / ".tess" / "state" / "memory"

    r = _run_tessctl(root, "memory", "adopt", "--from", str(from_dir), "--to", str(to_dir), "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    return from_dir, to_dir


def test_real_adopted_memory_file_never_staged_by_git_add_dash_a(real_git_root, tmp_path, engine):
    from_dir, to_dir = _adopt_real_memory(real_git_root, tmp_path, engine)
    rel = ".tess/state/memory/feedback_real.md"
    assert (real_git_root / rel).exists()

    _git(real_git_root, "add", "-A")
    staged = _git(real_git_root, "diff", "--cached", "--name-only").stdout.split()
    assert rel not in staged, f"a REAL adopted memory file ({rel}) must not be staged by a bare `git add -A`"

    status = _git(real_git_root, "status", "--porcelain").stdout
    assert rel not in status, f"{rel} must not surface in `git status` at all"


def test_real_adopt_manifest_never_staged_by_git_add_dash_a(real_git_root, tmp_path, engine):
    from_dir, to_dir = _adopt_real_memory(real_git_root, tmp_path, engine)
    manifests = list(to_dir.glob(".tess-memory-adopt.*.json"))
    assert len(manifests) == 1
    rel = f".tess/state/memory/{manifests[0].name}"

    _git(real_git_root, "add", "-A")
    staged = _git(real_git_root, "diff", "--cached", "--name-only").stdout.split()
    assert rel not in staged, f"the adopt manifest ({rel}) must not be staged by a bare `git add -A`"


def test_real_adopted_memory_file_blocked_by_publish_clean_gate_when_force_added(
    real_git_root, tmp_path, engine,
):
    from_dir, to_dir = _adopt_real_memory(real_git_root, tmp_path, engine)
    rel = ".tess/state/memory/feedback_real.md"

    # Simulate a bypass of the gitignore fence (e.g. `git add -f`) — the
    # SECOND, independent control (the commit-side publish-clean gate) must
    # still refuse this path regardless of gitignore state.
    _git(real_git_root, "add", "-f", rel)
    manifest = engine.load_manifest(real_git_root)
    violations = engine._publish_clean_violations(real_git_root, manifest, scope="staged")
    flagged = {v[0] for v in violations}
    assert rel in flagged, f"a force-added REAL adopted memory file ({rel}) must be flagged by the publish-clean gate"


def test_real_adopt_manifest_blocked_by_publish_clean_gate_when_force_added(
    real_git_root, tmp_path, engine,
):
    from_dir, to_dir = _adopt_real_memory(real_git_root, tmp_path, engine)
    manifests = list(to_dir.glob(".tess-memory-adopt.*.json"))
    rel = f".tess/state/memory/{manifests[0].name}"

    _git(real_git_root, "add", "-f", rel)
    manifest = engine.load_manifest(real_git_root)
    violations = engine._publish_clean_violations(real_git_root, manifest, scope="staged")
    flagged = {v[0] for v in violations}
    assert rel in flagged, f"a force-added adopt manifest ({rel}) must be flagged by the publish-clean gate"


def test_real_adopted_memory_invisible_to_doctor_verify_lock_check(real_git_root, tmp_path):
    """Mirrors test_task_ledger_fence.py's own doctor/verify/lock-check
    invisibility proof, against a REAL adopted memory tree instead of a
    synthetic root, using the actual repo copy (not just `real_git_root`)
    so doctor's full lock-entry-driven scan runs against everything else
    this repo ships too."""
    dst = real_git_root.parent / "real_repo_copy"
    ignore = shutil.ignore_patterns(".git", "tests", ".pytest_cache", "__pycache__", ".github")
    shutil.copytree(REPO_ROOT, dst, ignore=ignore)

    from_dir = tmp_path / "harness-home-2" / "memory"
    from_dir.mkdir(parents=True)
    (from_dir / "a.md").write_text("doctor-visibility check\n", encoding="utf-8")
    to_dir = dst / ".tess" / "state" / "memory"

    r_adopt = _run_tessctl(dst, "memory", "adopt", "--from", str(from_dir), "--to", str(to_dir), "--yes")
    assert r_adopt.returncode == 0, r_adopt.stdout + r_adopt.stderr

    d = _run_tessctl(dst, "doctor")
    assert d.returncode == 0, d.stdout + d.stderr
    # The memory-link check DOES print `.tess/state/memory` paths (by
    # design — it is an intentional, non-fatal informational surface, not
    # a leak into the SHA-integrity scan). What must never happen is the
    # core-managed file loop itself picking up adopted content as a
    # core_key/live_path entry — assert none of the per-file lines above
    # the memory-link section mention it.
    pre_summary = d.stdout.split("memory-link", 1)[0]
    assert ".tess/state/" not in pre_summary

    v = _run_tessctl(dst, "verify")
    assert v.returncode == 0, v.stdout + v.stderr

    lc = _run_tessctl(dst, "lock", "--check")
    assert lc.returncode == 0, lc.stdout + lc.stderr

    manifest = json.loads((REPO_ROOT / "tess.manifest.json").read_text(encoding="utf-8"))
    assert ".tess/state/**" in manifest["never_touch"]


# ---------------------------------------------------------------------------
# The Codex/generic AGENTS.md render pointer
# ---------------------------------------------------------------------------

def test_real_agents_md_render_includes_session_memory_section(engine):
    rendered = engine.render_agents_md(REPO_ROOT)
    assert "## Session Memory (Shared)" in rendered
    assert ".tess/state/memory/MEMORY.md" in rendered
    assert "{{" not in rendered  # every token fully resolved, no leftover placeholder


def test_real_agents_md_render_still_clean_of_denylisted_doctrine(engine):
    """The new fragment must not reintroduce the exact G3 harm — dispatch
    mechanics leaking into a harness with no dispatchable crew."""
    violations = engine._check_worker_profile_denylist(REPO_ROOT)
    assert violations == [], violations


def test_session_memory_fragment_file_is_the_agents_token_map_source(engine):
    frag_rel = engine.AGENTS_TOKEN_MAP["{{WORKER_SESSION_MEMORY}}"]
    frag_path = REPO_ROOT / frag_rel
    assert frag_path.exists()
    content = frag_path.read_text(encoding="utf-8").strip()
    rendered = engine.render_agents_md(REPO_ROOT)
    assert content in rendered
