"""
Codex render target ENABLED + shared-brain pointers — issue #118.

The `codex` render target (`CodexRenderTarget`, Phase 2) was fully built but
never enabled for this repo's own install, and the worker-profile AGENTS.md
digest carried a pointer at the cross-harness Session Memory store
(`.tess/state/memory/`, #117) with no equivalent pointer at the cross-harness
Task Store (`.tess/state/tasks/`, #113/#115) — so a Codex session reading the
rendered AGENTS.md had no doctrine-level way to discover it could see, claim,
or update work on the same task board a Claude Code session already uses.

This suite proves, against the REAL shipped repo (not a synthetic fixture —
same convention `tests/test_worker_profile_denylist.py` uses for "the real
render is clean"):

  1. `codex` is enabled in the real tess.manifest.json, `generic` is not.
  2. The real rendered AGENTS.md carries BOTH cross-harness state-mount
     pointers — Session Memory AND Shared Tasks — with the specific
     `tessctl tasks pull` / `claim` / `set` / `tessctl log` commands and the
     "claim with your own identity" instruction issue #118 asked for.
  3. The committed, live AGENTS.md at the repo root is BYTE-IDENTICAL to
     `render_agents_md(repo_root)` — i.e. `tessctl render` is deterministic
     and the checked-in artifact is not stale relative to its own template.
  4. The new fragment introduces no G3 worker-profile doctrine-denylist
     violation (mirrors `tests/test_memory_adopt_fence.py`'s equivalent
     assertion for the memory pointer).
  5. `tessctl render --target codex` is idempotent against a COPY of the
     real repo (`tests/test_run.py`'s own `real_root` convention — never
     write through subprocess CLI calls directly into REPO_ROOT) and leaves
     `doctor`/`verify`/`lock --check` green, with plain `tessctl render`
     (no `--target`) now covering codex too.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest

from conftest import MANIFEST_SRC, REPO_ROOT


# ---------------------------------------------------------------------------
# 1. codex enabled, generic not — the real manifest
# ---------------------------------------------------------------------------

def test_codex_enabled_in_real_manifest():
    manifest = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))
    enabled = manifest["render_targets"]["enabled"]
    assert "codex" in enabled
    assert "claude-code" in enabled
    assert "generic" not in enabled


# ---------------------------------------------------------------------------
# 2. The real rendered AGENTS.md carries BOTH shared-brain pointers
#    (read-only: render_agents_md() never writes to disk)
# ---------------------------------------------------------------------------

def test_real_agents_md_has_session_memory_pointer(engine):
    rendered = engine.render_agents_md(REPO_ROOT)
    assert "## Session Memory (Shared)" in rendered
    assert ".tess/state/memory/MEMORY.md" in rendered
    assert "tessctl memory adopt" in rendered


def test_real_agents_md_has_shared_tasks_pointer(engine):
    rendered = engine.render_agents_md(REPO_ROOT)
    assert "## Shared Tasks" in rendered
    assert ".tess/state/tasks/" in rendered
    # The commands issue #118 explicitly asked for.
    assert "tessctl tasks pull" in rendered
    assert "tessctl tasks claim" in rendered
    assert "tessctl tasks set" in rendered
    assert "tessctl log append" in rendered
    # Claim with the worker's OWN identity before working it.
    assert "--host" in rendered
    assert "--pid" in rendered
    assert "--uuid" in rendered
    assert "OWN" in rendered


def test_shared_tasks_section_comes_after_session_memory():
    """Ordering sanity: Shared Tasks is Session Memory's sibling section,
    not a replacement — both must be present, memory first (#117), tasks
    second (#118), matching AGENTS.md.tpl's own section order."""
    tpl_path = REPO_ROOT / ".tess" / "core" / "templates" / "agents-md" / "AGENTS.md.tpl"
    tpl_text = tpl_path.read_text(encoding="utf-8")
    mem_idx = tpl_text.index("{{WORKER_SESSION_MEMORY}}")
    tasks_idx = tpl_text.index("{{WORKER_SHARED_TASKS}}")
    assert mem_idx < tasks_idx


# ---------------------------------------------------------------------------
# 3. The committed live AGENTS.md is not stale relative to its own template
#    (read-only)
# ---------------------------------------------------------------------------

def test_committed_agents_md_matches_render_output(engine):
    """The AGENTS.md checked into the repo root must be byte-identical to
    what `render_agents_md(REPO_ROOT)` produces right now — i.e. whoever
    last edited the template/fragments re-ran `tessctl render` and committed
    the result, exactly as AGENTS.md.tpl's own banner instructs. This is the
    same invariant `tessctl doctor`/`verify` enforce at the untracked-render-
    generated layer, pinned here as a direct unit assertion."""
    live_bytes = (REPO_ROOT / "AGENTS.md").read_bytes()
    expected_bytes = engine.render_agents_md(REPO_ROOT).encode("utf-8")
    assert live_bytes == expected_bytes, (
        "committed AGENTS.md is STALE relative to AGENTS.md.tpl + its fragments — "
        "run `tessctl render --target codex` (or plain `tessctl render`, now that "
        "codex is enabled) and commit the result."
    )


# ---------------------------------------------------------------------------
# 4. No G3 worker-profile doctrine-denylist violation introduced (read-only)
# ---------------------------------------------------------------------------

def test_shared_tasks_fragment_introduces_no_denylist_violation(engine):
    violations = engine._check_worker_profile_denylist(REPO_ROOT)
    assert violations == [], (
        f"the new Shared Tasks fragment leaked worker-profile-denylisted "
        f"doctrine into AGENTS.md: {violations}"
    )


def test_shared_tasks_fragment_file_exists_and_is_registered(engine):
    frag_rel = engine.AGENTS_TOKEN_MAP["{{WORKER_SHARED_TASKS}}"]
    frag_path = REPO_ROOT / frag_rel
    assert frag_path.exists(), f"{frag_rel} referenced by AGENTS_TOKEN_MAP but missing on disk"
    content = frag_path.read_text(encoding="utf-8")
    assert "tessctl tasks" in content


# ---------------------------------------------------------------------------
# 5. Deterministic re-render + doctor/verify/lock green — against a COPY of
#    the real repo (tests/test_run.py's `real_root` convention: writing
#    render targets is a real filesystem side effect, so it must never run
#    directly against REPO_ROOT / the developer's own working tree).
# ---------------------------------------------------------------------------

_COPY_IGNORE = shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".github", ".venv")


@pytest.fixture
def real_root(tmp_path):
    dst = tmp_path / "os"
    shutil.copytree(REPO_ROOT, dst, ignore=_COPY_IGNORE)
    return dst


def test_real_codex_render_is_idempotent(real_root, run_cli):
    """Mirrors test_render_targets_codex_generic.py's synthetic idempotency
    coverage, but against a COPY of the REAL repo tree — proves `tessctl
    render --target codex` run twice in a row on the actual shipped core
    produces byte-identical AGENTS.md and stays clean end to end."""
    r1 = run_cli(real_root, "render", "--target", "codex")
    assert r1.returncode == 0, r1.stderr
    first = (real_root / "AGENTS.md").read_bytes()

    r2 = run_cli(real_root, "render", "--target", "codex")
    assert r2.returncode == 0, r2.stderr
    second = (real_root / "AGENTS.md").read_bytes()

    assert first == second, "tessctl render --target codex is not idempotent on the real repo"

    d = run_cli(real_root, "doctor")
    assert d.returncode == 0, f"doctor not clean on the real repo after render:\n{d.stdout}\n{d.stderr}"
    v = run_cli(real_root, "verify")
    assert v.returncode == 0, f"verify not clean on the real repo after render:\n{v.stdout}\n{v.stderr}"
    lc = run_cli(real_root, "lock", "--check")
    assert lc.returncode == 0, f"lock --check not clean on the real repo after render:\n{lc.stdout}\n{lc.stderr}"


def test_real_plain_render_now_includes_codex(real_root):
    """`tessctl render` with NO --target flag renders every ENABLED target
    for this install — now includes codex (issue #118), so a plain render
    on this repo produces AGENTS.md/.codex/** without needing an explicit
    --target flag."""
    r = subprocess.run(
        [sys.executable, str(real_root / ".tess" / "bin" / "tessctl"), "render"],
        cwd=str(real_root), capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "rendered  AGENTS.md" in r.stdout
    assert "rendered  .codex/config.toml" in r.stdout
