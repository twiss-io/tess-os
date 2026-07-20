"""
DATA-LEAK-SAFETY (issue #92) — the commit-side PUBLISH-CLEAN gate.

The manifest write-gate (check_manifest_write_gate / guarded_write,
tests/test_write_gate.py) stops tessctl itself from ever WRITING to a
never_touch path. Nothing previously stopped the operator's own `git commit`
from COMMITTING one — a plain `git add -A` picks up whatever gitignore
didn't already exclude, and gitignore had drifted from the manifest (see
.gitignore in this same PR). `tessctl doctor --publish-clean` is the
symmetric commit-side control; this file proves it at three levels:

  1. Unit — `_publish_clean_violations` against a synthetic git index.
  2. CLI  — `tessctl doctor --publish-clean` via subprocess (exit codes,
     --publish-clean-all audit scope).
  3. E2E  — the real pre-commit hook (`tessctl gate install-hooks`) actually
     blocks a real `git commit`, coexists with the vault/gate guards (same
     splice discipline tests/test_gate_hooks.py and
     tests/test_hook_coexistence.py already prove for each other), and
     allows a normal framework-file change through.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HAS_GIT = shutil.which("git") is not None
pytestmark = pytest.mark.skipif(not HAS_GIT, reason="git required")

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_SRC = REPO_ROOT / "tess.manifest.json"

USER_SENTINEL = "TESS-TEST-USER-HOOK-RAN"


def _git(root, *args, check=True, input_text=None):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@tess.test",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@tess.test",
    }
    r = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, env=env, input=input_text,
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}\n{r.stdout}")
    return r


def _init_repo(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@tess.test")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")


def _write_user_hook(root, name):
    hp = root / ".git" / "hooks" / name
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text(
        "#!/usr/bin/env bash\n"
        "# operator's own pre-existing hook\n"
        f'echo "{USER_SENTINEL}" >> "$(git rev-parse --show-toplevel)/.user_hook_log"\n'
        "exit 0\n"
    )
    os.chmod(str(hp), 0o755)
    return hp


def _real_manifest() -> dict:
    return json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Consistency: the curated private-data glob set must not silently drift from
# the manifest it claims to derive from.
# ---------------------------------------------------------------------------

def test_curated_globs_are_manifest_never_touch_members(engine):
    """Every glob in _PUBLISH_CLEAN_PRIVATE_GLOBS that ISN'T one of the
    hardcoded vault-parity additions (never in the manifest — mirrors the
    write-gate's own hardcoded vault hard-guard, Step 3b) must be a literal
    member of tess.manifest.json's never_touch array. Catches silent drift
    between the manifest and the curated commit-side subset."""
    never_touch = set(_real_manifest()["never_touch"])
    vault_hardcoded = {"**/*.age", ".claude/vault/**", "clients/*/.vault/**"}
    for glob in engine._PUBLISH_CLEAN_PRIVATE_GLOBS:
        if glob in vault_hardcoded:
            continue
        assert glob in never_touch, (
            f"{glob!r} is in _PUBLISH_CLEAN_PRIVATE_GLOBS but not in the "
            f"manifest's never_touch — drift between the write-gate and the "
            f"publish-clean gate's private-data definition."
        )


def test_curated_globs_are_not_the_full_never_touch_list(engine):
    """The regression this whole design change exists to prevent: using the
    FULL manifest never_touch list (instead of the curated subset) flags
    ~155 legitimately-tracked framework paths in this repo alone (docs/**,
    adapters/**, starter/**, README.md, main.py, ...) — a gate that
    permanently blocks ordinary framework development. Pin that the curated
    set deliberately excludes at least the biggest offenders."""
    curated = set(engine._PUBLISH_CLEAN_PRIVATE_GLOBS)
    for non_private in ("docs/**", "adapters/**", "starter/**", "README.md",
                        "main.py", "pyproject.toml", "uv.lock"):
        assert non_private not in curated


# ---------------------------------------------------------------------------
# Unit: _publish_clean_violations against a synthetic git index
# ---------------------------------------------------------------------------

@pytest.fixture
def priv_repo(tmp_path, engine):
    """A minimal git repo with the real manifest, for unit-level violation
    checks (no tess.lock / .tess scaffolding needed — this check only reads
    tess.manifest.json and the git index)."""
    _init_repo(tmp_path)
    shutil.copy2(MANIFEST_SRC, tmp_path / "tess.manifest.json")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def _stage(root, rel, content="x"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    _git(root, "add", "-f", rel)


@pytest.mark.parametrize("rel", [
    "operator/leaked-notes.md",
    "operator/profile.json",
    "notes.local.md",
    "sub/dir/shadow.local.md",
    "kb/wiki/log.md",
    "kb/wiki/newmission.md",
    "clients/AcmeCorp/contract.md",
    ".env",
    "missions/m1/mission.md",
    "UPGRADE-NOTES.md",
    ".mcp.json",
    # Phase 0.1 — cross-harness shared-brain state root (docs/STATE_LAYER.md)
    ".tess/state/memory/note.md",
    ".tess/state/tasks/graph.json",
    ".tess/state/ledger/entry.md",
    ".tess/state/locks/task.lock",
])
def test_blocks_each_private_path(engine, priv_repo, rel):
    _stage(priv_repo, rel)
    manifest = engine.load_manifest(priv_repo)
    violations = engine._publish_clean_violations(priv_repo, manifest, scope="staged")
    flagged = {v[0] for v in violations}
    assert rel in flagged, f"{rel} should have been flagged as a private-data violation"


@pytest.mark.parametrize("rel,content", [
    ("README.md", "docs change"),
    ("docs/NEW_DOC.md", "new doc"),
    ("adapters/README.md", "adapter doc"),
    ("starter/CLAUDE.md", "starter template"),
    ("main.py", "print(1)\n"),
])
def test_allows_normal_framework_file(engine, priv_repo, rel, content):
    _stage(priv_repo, rel, content)
    manifest = engine.load_manifest(priv_repo)
    violations = engine._publish_clean_violations(priv_repo, manifest, scope="staged")
    flagged = {v[0] for v in violations}
    assert rel not in flagged, f"{rel} is ordinary framework content and must not be flagged"


@pytest.mark.parametrize("rel", [
    "operator/build-facts-stub.md",
    "operator/identity-stub.md",
    "operator/org-channels.md",
    "operator/user-profile.md",
    "missions/README.md",
    ".env.example",
    "clients/_template/CLAUDE.md",
])
def test_allowlists_shipped_templates(engine, priv_repo, rel):
    """Paths that match a private-data glob by shape but are deliberately
    shipped, tracked framework scaffold (mirrors the .gitignore `!` overrides
    in this same PR) must never be flagged."""
    _stage(priv_repo, rel)
    manifest = engine.load_manifest(priv_repo)
    violations = engine._publish_clean_violations(priv_repo, manifest, scope="staged")
    flagged = {v[0] for v in violations}
    assert rel not in flagged


def test_gitkeep_placeholder_always_allowed(engine, priv_repo):
    _stage(priv_repo, "kb/wiki/concepts/.gitkeep", "")
    manifest = engine.load_manifest(priv_repo)
    violations = engine._publish_clean_violations(priv_repo, manifest, scope="staged")
    assert violations == []


def test_deleting_an_already_leaked_path_is_never_blocked(engine, priv_repo):
    """The documented remediation for an already-committed leak (`git rm
    --cached`) must itself never be blocked by the gate that exists to fix
    the leak."""
    _stage(priv_repo, "operator/oops.md")
    _git(priv_repo, "commit", "-q", "-m", "accidental leak")
    _git(priv_repo, "rm", "--cached", "-q", "operator/oops.md")
    manifest = engine.load_manifest(priv_repo)
    violations = engine._publish_clean_violations(priv_repo, manifest, scope="staged")
    assert violations == []


def test_staged_scope_does_not_reflag_pre_existing_grandfathered_tracked_file(engine, priv_repo):
    """A never_touch path that is ALREADY tracked (e.g. this repo's own
    generic operator/profile.json, grandfathered per the .gitignore
    reconciliation's documented design) must not re-fail every future
    UNRELATED commit forever — only a commit that actually touches it."""
    _stage(priv_repo, "operator/profile.json", '{"operator_name": "Operator"}')
    _git(priv_repo, "commit", "-q", "-m", "grandfathered tracked file")

    # An unrelated, later commit that never touches operator/profile.json:
    _stage(priv_repo, "README.md", "unrelated change")
    manifest = engine.load_manifest(priv_repo)
    violations = engine._publish_clean_violations(priv_repo, manifest, scope="staged")
    assert violations == [], (
        "staged-scope must not re-flag a pre-existing tracked file that "
        "this commit doesn't touch"
    )


def test_all_scope_reports_pre_existing_grandfathered_tracked_file(engine, priv_repo):
    """--publish-clean-all (full `git ls-files` audit) DOES report the
    grandfathered file — it's a diagnostic tool, not the commit gate."""
    _stage(priv_repo, "operator/profile.json", '{"operator_name": "Operator"}')
    _git(priv_repo, "commit", "-q", "-m", "grandfathered tracked file")

    manifest = engine.load_manifest(priv_repo)
    violations = engine._publish_clean_violations(priv_repo, manifest, scope="all")
    flagged = {v[0] for v in violations}
    assert "operator/profile.json" in flagged


def test_owned_globs_wins_clients_template(engine, priv_repo):
    _stage(priv_repo, "clients/_template/kb/wiki/index.md")
    manifest = engine.load_manifest(priv_repo)
    violations = engine._publish_clean_violations(priv_repo, manifest, scope="staged")
    assert violations == []


# ---------------------------------------------------------------------------
# Phase 0.1 — .tess/state/** (memory/tasks/ledger/locks), the canonical
# cross-harness shared-brain state root (docs/STATE_LAYER.md). Same family
# as the create-tess scaffold-strip tests (Quinn-MED, units.test.js) and
# tests/test_patch_no_clobber.py: prove data can never survive ANY of the
# write paths that could otherwise carry it into a public/shared place, not
# just one of them.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("subdir", ["memory", "tasks", "ledger", "locks", "skills"])
def test_state_never_publishable(engine, priv_repo, subdir):
    """Three independent guarantees, proven together for each subdir:

    1. `.tess/state/**` is declared in the manifest's never_touch (so the
       write-gate — `check_manifest_write_gate` — refuses any tessctl write
       there; ported explicitly in tests/test_write_gate.py's GATE_CASES).
    2. The publish-clean commit gate flags real content staged under it as
       a violation, regardless of scope.
    3. The curated `_PUBLISH_CLEAN_PRIVATE_GLOBS` set — the thing that
       actually implements #2 — is not silently missing the glob (would
       make #2 pass here for the wrong reason: manifest says never_touch,
       but the commit-side gate forgot to look).
    """
    never_touch = _real_manifest()["never_touch"]
    assert ".tess/state/**" in never_touch

    assert any(
        engine.path_matches_globs(f".tess/state/{subdir}", [g])
        for g in engine._PUBLISH_CLEAN_PRIVATE_GLOBS
    ), f".tess/state/{subdir}/** is not covered by _PUBLISH_CLEAN_PRIVATE_GLOBS"

    _stage(priv_repo, f".tess/state/{subdir}/real-instance-data.md", "real data")
    manifest = engine.load_manifest(priv_repo)
    violations = engine._publish_clean_violations(priv_repo, manifest, scope="staged")
    flagged = {v[0] for v in violations}
    assert f".tess/state/{subdir}/real-instance-data.md" in flagged


def test_state_write_gate_denies_every_subdir(engine, gate_root_with_state_manifest):
    """The write-gate half of the guarantee (`check_manifest_write_gate`,
    the mechanism `.tess/bin/tessctl` itself uses before ANY write) — proven
    directly here rather than only via the parametrized GATE_CASES table in
    tests/test_write_gate.py, so this file's own guard does not silently
    depend on that other file staying in sync."""
    manifest = engine.load_manifest(gate_root_with_state_manifest)
    for subdir, name in (
        ("memory", "note.md"), ("tasks", "graph.json"),
        ("ledger", "entry.md"), ("locks", "task.lock"),
        ("skills", "drafts/x/SKILL.md"),
    ):
        with pytest.raises(engine.GateError):
            engine.check_manifest_write_gate(
                gate_root_with_state_manifest, manifest,
                f".tess/state/{subdir}/{name}", op="test",
            )


def test_state_scaffold_ships_empty():
    """The repo's own checked-in `.tess/state/**` tree (what create-tess's
    local-source scaffold path would copy verbatim before ignore.js's
    EXCLUDE_CONTENT_PREFIXES strips it — see create-tess/test/units.test.js
    for that strip proven end-to-end) contains ONLY `.gitkeep` placeholders
    today. Adopters inherit the structure, never data — this is the static
    half of that guarantee; the dynamic half (a local source WITH real
    content in it) is proven in create-tess's own test suite."""
    state_root = REPO_ROOT / ".tess" / "state"
    assert state_root.is_dir(), ".tess/state/ must exist in the repo"
    for sub in ("memory", "tasks", "ledger", "locks", "skills"):
        subdir = state_root / sub
        assert subdir.is_dir(), f".tess/state/{sub}/ must exist"
        entries = [p for p in subdir.rglob("*") if p.is_file()]
        assert entries == [subdir / ".gitkeep"], (
            f".tess/state/{sub}/ must ship with ONLY .gitkeep, found: {entries}"
        )


@pytest.fixture
def gate_root_with_state_manifest(tmp_path):
    shutil.copy2(MANIFEST_SRC, tmp_path / "tess.manifest.json")
    return tmp_path


# ---------------------------------------------------------------------------
# CLI: `tessctl doctor --publish-clean`
# ---------------------------------------------------------------------------

def test_cli_publish_clean_ok_exit_zero(run_cli, priv_repo, engine):
    # priv_repo has no .tess scaffolding, but --publish-clean only needs
    # tess.manifest.json + git — run the engine directly via subprocess.
    r = subprocess.run(
        ["python3", str(REPO_ROOT / ".tess" / "bin" / "tessctl"), "doctor", "--publish-clean"],
        cwd=str(priv_repo), capture_output=True, text=True,
        env={**os.environ, "TESS_ROOT": str(priv_repo)},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "publish-clean: OK" in r.stdout


def test_cli_publish_clean_blocks_and_exits_one(priv_repo):
    _stage(priv_repo, "operator/leak.md")
    r = subprocess.run(
        ["python3", str(REPO_ROOT / ".tess" / "bin" / "tessctl"), "doctor", "--publish-clean"],
        cwd=str(priv_repo), capture_output=True, text=True,
        env={**os.environ, "TESS_ROOT": str(priv_repo)},
    )
    assert r.returncode == 1
    assert "BLOCKED" in r.stdout
    assert "operator/leak.md" in r.stdout


def test_cli_publish_clean_all_audits_full_tree(priv_repo):
    _stage(priv_repo, "operator/profile.json", '{"operator_name": "Operator"}')
    _git(priv_repo, "commit", "-q", "-m", "tracked")
    r = subprocess.run(
        ["python3", str(REPO_ROOT / ".tess" / "bin" / "tessctl"), "doctor",
         "--publish-clean", "--publish-clean-all"],
        cwd=str(priv_repo), capture_output=True, text=True,
        env={**os.environ, "TESS_ROOT": str(priv_repo)},
    )
    assert r.returncode == 1
    assert "operator/profile.json" in r.stdout


def test_publish_clean_outside_git_repo_skips_not_crashes(tmp_path):
    shutil.copy2(MANIFEST_SRC, tmp_path / "tess.manifest.json")
    r = subprocess.run(
        ["python3", str(REPO_ROOT / ".tess" / "bin" / "tessctl"), "doctor", "--publish-clean"],
        cwd=str(tmp_path), capture_output=True, text=True,
        env={**os.environ, "TESS_ROOT": str(tmp_path)},
    )
    assert r.returncode == 0
    assert "SKIPPED" in r.stdout


def test_publish_clean_missing_manifest_skips_not_crashes(tmp_path):
    """Regression: a git repo with NO tess.manifest.json (an unrelated repo,
    an early bootstrap state, or a minimal test fixture like
    tests/test_gate_hooks.py's e2e_repo, which never ships a manifest) must
    SKIP gracefully, not hard-crash via load_manifest's own sys.exit — a
    crash here would BLOCK every commit in that repo forever, for a reason
    having nothing to do with an actual private-data violation. Found via a
    real regression: this exact gap broke 5 pre-existing e2e tests in
    tests/test_gate_hooks.py when the publish-clean guard was first spliced
    into the same pre-commit hook."""
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init, no manifest at all")

    r = subprocess.run(
        ["python3", str(REPO_ROOT / ".tess" / "bin" / "tessctl"), "doctor", "--publish-clean"],
        cwd=str(tmp_path), capture_output=True, text=True,
        env={**os.environ, "TESS_ROOT": str(tmp_path)},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED" in r.stdout
    assert "tess.manifest.json" in r.stdout


# ---------------------------------------------------------------------------
# E2E: the real pre-commit hook fires, blocks, allows, and coexists
# ---------------------------------------------------------------------------

@pytest.fixture
def hook_repo(tmp_path):
    """A minimal but real Tess OS root (engine + manifest + tess.lock) as an
    actual git repo — enough for `tessctl gate install-hooks` /
    `tessctl doctor --publish-clean` to run for real."""
    (tmp_path / ".tess" / "bin").mkdir(parents=True)
    engine_src = REPO_ROOT / ".tess" / "bin" / "tessctl"
    shutil.copy2(engine_src, tmp_path / ".tess" / "bin" / "tessctl")
    os.chmod(tmp_path / ".tess" / "bin" / "tessctl", 0o755)
    shutil.copy2(MANIFEST_SRC, tmp_path / "tess.manifest.json")
    (tmp_path / ".tess" / "tess.lock").write_text(
        json.dumps({"schema": 1, "framework": {}, "files": {}}), encoding="utf-8"
    )
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_e2e_precommit_blocks_operator_pii(run_cli, hook_repo):
    r = run_cli(hook_repo, "gate", "install-hooks")
    assert r.returncode == 0, r.stdout + r.stderr

    _stage(hook_repo, "operator/profile.json", '{"operator_name": "RealFounder"}')
    r = _git(hook_repo, "commit", "-m", "leak", check=False)
    assert r.returncode != 0, "pre-commit hook did not fire / did not block operator PII"
    assert "publish-clean" in (r.stdout + r.stderr)
    assert "BLOCKED" in (r.stdout + r.stderr)


@pytest.mark.parametrize("rel,content", [
    ("operator/leak.md", "real identity"),
    ("some.local.md", "shadow override"),
    ("kb/wiki/log.md", "2026-07-18 real mission entry"),
    ("clients/AcmeCorp/notes.md", "real client data"),
    (".env", "SECRET=1"),
])
def test_e2e_precommit_blocks_each_required_case(run_cli, hook_repo, rel, content):
    r = run_cli(hook_repo, "gate", "install-hooks")
    assert r.returncode == 0, r.stdout + r.stderr

    _stage(hook_repo, rel, content)
    r = _git(hook_repo, "commit", "-m", "leak", check=False)
    assert r.returncode != 0, f"pre-commit hook did not block {rel}"
    assert "BLOCKED" in (r.stdout + r.stderr)


def test_e2e_precommit_allows_normal_framework_change(run_cli, hook_repo):
    r = run_cli(hook_repo, "gate", "install-hooks")
    assert r.returncode == 0, r.stdout + r.stderr

    (hook_repo / "README.md").write_text("hello\nan ordinary doc update\n", encoding="utf-8")
    _git(hook_repo, "add", "README.md")
    r = _git(hook_repo, "commit", "-m", "normal change", check=False)
    assert r.returncode == 0, f"pre-commit hook blocked an ordinary framework change: {r.stdout}{r.stderr}"


def test_e2e_precommit_coexists_with_operator_own_hook(run_cli, hook_repo):
    _write_user_hook(hook_repo, "pre-commit")
    r = run_cli(hook_repo, "gate", "install-hooks")
    assert r.returncode == 0, r.stdout + r.stderr

    text = (hook_repo / ".git" / "hooks" / "pre-commit").read_text()
    assert "# tess-publish-guard v1" in text
    assert USER_SENTINEL not in text or "operator's own pre-existing hook" in text

    (hook_repo / "README.md").write_text("hello\nclean edit\n", encoding="utf-8")
    _git(hook_repo, "add", "README.md")
    r = _git(hook_repo, "commit", "-m", "clean", check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (hook_repo / ".user_hook_log").exists(), "operator's own pre-existing hook must still run"


def test_e2e_precommit_coexists_with_vault_and_gate_guards(engine, run_cli, hook_repo):
    """Install order: vault, then gate, then (via install-hooks) publish.
    All three guards must be present and a violation caught by ANY of them
    still blocks; a clean commit still runs all three and succeeds."""
    engine._vault_install_git_hooks(hook_repo)
    r = run_cli(hook_repo, "gate", "install-hooks")
    assert r.returncode == 0, r.stdout + r.stderr

    text = (hook_repo / ".git" / "hooks" / "pre-commit").read_text()
    assert "# tess-vault-guard v2" in text
    assert "# tess-gate-guard v1" in text
    assert "# tess-publish-guard v1" in text
    assert subprocess.run(["bash", "-n", str(hook_repo / ".git" / "hooks" / "pre-commit")]).returncode == 0

    # A publish-clean violation still blocks even with all three installed.
    _stage(hook_repo, "operator/leak.md", "real identity")
    r = _git(hook_repo, "commit", "-m", "leak", check=False)
    assert r.returncode != 0
    assert "BLOCKED" in (r.stdout + r.stderr)

    # Clean-up the failed stage, then a clean commit succeeds.
    _git(hook_repo, "restore", "--staged", "operator/leak.md", check=False)
    (hook_repo / "operator" / "leak.md").unlink()
    (hook_repo / "README.md").write_text("hello\nclean\n", encoding="utf-8")
    _git(hook_repo, "add", "README.md")
    r = _git(hook_repo, "commit", "-m", "clean", check=False)
    assert r.returncode == 0, r.stdout + r.stderr


def test_install_hooks_installs_publish_guard_idempotently(engine, tmp_path):
    _init_repo(tmp_path)
    engine._publish_install_git_hooks(tmp_path)
    first = (tmp_path / ".git" / "hooks" / "pre-commit").read_text()
    engine._publish_install_git_hooks(tmp_path)
    second = (tmp_path / ".git" / "hooks" / "pre-commit").read_text()
    assert first == second
    assert second.count("# tess-publish-guard v1") == 1
