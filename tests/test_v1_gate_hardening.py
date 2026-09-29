"""v1.0.0 final security review (Cyra, 2026-09-29) — gate path listing,
release-proof acceptance and the public-remote push guard.

H1  The gate listed changed paths with `git diff --name-only` (no `-z`, quoted
    paths on). A non-ASCII name came back C-quoted ("\\303\\251.yml"), a name
    with `"` or a newline came back quoted or split, and none of them matched a
    protected glob: adding `.github/workflows/é.yml` PASSED the gate.
H2  A release proof exempted ANY protected path whose bytes equal the same
    path in the proven release, so a re-used `.tess/release-proof.json` could
    reset policy.yaml to the release copy (restoring the upstream maintainers'
    verifier key the wizard removes). `tessctl update` itself restored it too.
H3  The public-remote guard scanned only the pushed tip's tree: data committed
    and then `git rm`-ed was published in history without a word.

Each test here failed on release/v1.0 @ 6f16a7f and passes with the fix.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import HAS_GIT, HAS_GPG, REPO_ROOT, make_upstream
from test_publish_remote_guard import (  # noqa: F401 — fixtures
    GH_URL, ZERO, _add_client, _commit_all, _git as _rg_git, _install, _prepush, fake_path, repo,
)

needs_git = pytest.mark.skipif(not HAS_GIT, reason="git required")
needs_gpg = pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")

WORKFLOW_POLICY = {
    "policy": {
        "version": 1,
        "rules": [{
            "id": "workflows",
            "description": "test-only: CI definitions need a verdict",
            "globs": [".github/workflows/**"],
            "classification": ["prod_touching"],
            "require_verdict": True,
            "allowed_verifiers": ["Reid"],
        }],
        "hard_floor_rules": [],
    }
}

# Names that git C-quotes (non-ASCII, `"`), and one it splits (newline).
TRICKY = [".github/workflows/é.yml", '.github/workflows/a"b.yml', ".github/workflows/a\nb.yml"]


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout


def _commit(root: Path, msg: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)
    return _git(root, "rev-parse", "HEAD").strip()


def _tessctl(root: Path, *args: str):
    return subprocess.run([sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
                          cwd=str(root), env={**os.environ, "TESS_ROOT": str(root)},
                          capture_output=True, text=True)


def _gate_ci(root: Path, base: str, head: str):
    r = _tessctl(root, "gate", "ci", "--base", base, "--head", head, "--json")
    return r, json.loads(r.stdout)


@pytest.fixture
def wf_repo(project):
    root = project.root
    shutil.copytree(REPO_ROOT / "core" / "contracts", root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)
    (root / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(WORKFLOW_POLICY),
                                                         encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "h1@tess.test")
    _git(root, "config", "user.name", "h1")
    _git(root, "config", "commit.gpgsign", "false")
    base = _commit(root, "base")
    return root, base


# ---------------------------------------------------------------------------
# H1 — NUL-separated, unquoted path listing
# ---------------------------------------------------------------------------

@needs_gpg
@pytest.mark.parametrize("rel", TRICKY, ids=["non-ascii", "double-quote", "newline"])
def test_gate_ci_blocks_a_protected_path_git_would_quote(wf_repo, rel):
    root, base = wf_repo
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("on: push\njobs: {}\n", encoding="utf-8")
    head = _commit(root, "sneak a workflow in")
    r, out = _gate_ci(root, base, head)
    assert r.returncode == 1 and out["blocked"] is True, out


@needs_git
def test_every_listing_returns_the_exact_names(engine, wf_repo):
    root, base = wf_repo
    for rel in TRICKY:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n", encoding="utf-8")
    _git(root, "add", "-A")
    assert set(TRICKY) <= set(engine._gate_changed_paths_staged(root))
    assert set(TRICKY) <= set(engine._publish_clean_tracked_paths(root, "staged"))
    assert set(TRICKY) <= set(engine._publish_clean_tracked_paths(root, "all"))
    head = _commit(root, "tricky")
    assert set(engine._gate_diff_paths(root, base, head)) == set(TRICKY)
    assert set(TRICKY) <= engine._gate_git_all_paths(root, [head])
    assert set(TRICKY) <= set(engine._gate_git_ls_tree(root, head))


# ---------------------------------------------------------------------------
# H2 — a release proof exempts only a real update of core-managed files
# ---------------------------------------------------------------------------

GUARD_KEY, GUARD_LIVE = ".tess/core/conductor/guardrails.md", "conductor/guardrails.md"
POL_KEY, POL_LIVE = ".tess/core/policy/policy.yaml", "core/policy/policy.yaml"
EXTRA_WF = ".github/workflows/release-extra.yml"
EXTRA_WF_KEY = ".tess/core/" + EXTRA_WF
NEW_KEY, NEW_LIVE = ".tess/core/conductor/new-rule.md", "conductor/new-rule.md"
OLD = "# Guardrails\n\nRule 1: always dispatch.\n"
NEW = OLD + "Rule 2: verify before shipping.\n"
RELEASE_POLICY = (REPO_ROOT / "core" / "policy" / "policy.yaml").read_text(encoding="utf-8")


def _installed(project, gpg_key, tmp_path, run_cli, engine, policy_extra: str = "") -> str:
    """An install at v2.0.0 whose policy is the release policy with the
    wizard's registry reset, core-managed in the lock, and a signed upstream
    v2.1.0 that changes guardrails and ships the maintainers' policy (with
    their Cyra verifier key), a new core file its own lock adopts, and a
    workflow (core copy + live copy) that neither lock manages."""
    wizard_policy = engine._policy_reset_registries_text(RELEASE_POLICY)
    assert "Cyra:" in RELEASE_POLICY and wizard_policy != RELEASE_POLICY
    project.add(GUARD_LIVE, OLD, tier="security")
    project.add(POL_LIVE, wizard_policy, tier="security", core_key=POL_KEY)
    project.add(None, "# Tess OS\n\nRoot: {{TESS_ROOT}}\n",
                core_key=".tess/core/templates/CLAUDE.md.tpl", render_live=False)
    project.add(None, '{"hooks": {}}\n', core_key=".tess/core/settings-core.json",
                render_live=False)
    up = make_upstream(
        tmp_path / "upstream", gpg_key, "v2.1.0", sign="signed",
        core_files={GUARD_KEY: NEW, GUARD_LIVE: NEW, POL_KEY: RELEASE_POLICY + policy_extra,
                    POL_LIVE: RELEASE_POLICY + policy_extra, EXTRA_WF: "on: push\njobs: {}\n",
                    EXTRA_WF_KEY: "on: push\njobs: {}\n", NEW_KEY: "# New rule\n",
                    NEW_LIVE: "# New rule\n",
                    ".tess/core/templates/CLAUDE.md.tpl": "# Tess OS\n\nRoot: {{TESS_ROOT}}\n",
                    ".tess/core/settings-core.json": '{"hooks": {}}\n'},
        lock_files={GUARD_KEY: {"status": "core-managed", "tier": "security",
                                "live_path": GUARD_LIVE},
                    POL_KEY: {"status": "core-managed", "tier": "security",
                              "live_path": POL_LIVE},
                    NEW_KEY: {"status": "core-managed", "tier": "security",
                              "live_path": NEW_LIVE}},
    )
    project.framework.update(upstream=str(up), upstream_ref="v2.0.0",
                             trusted_key_fingerprint=gpg_key.fpr)
    project.write()
    root = project.root
    shutil.copytree(REPO_ROOT / "core" / "contracts", root / "core" / "contracts")
    pub = subprocess.run(["gpg", "--armor", "--export", gpg_key.fpr], capture_output=True,
                         env={**os.environ, "GNUPGHOME": gpg_key.home}).stdout
    (root / ".tess" / "keys").mkdir(parents=True, exist_ok=True)
    (root / ".tess" / "keys" / "twiss-release-key.asc").write_bytes(pub)
    (root / ".gitignore").write_text(
        ".tess/snapshots/\n.tess/staging/\n.tess/update.lock\n.tess/trace/\n.tess/state/\n",
        encoding="utf-8")
    r = run_cli(root, "render")
    assert r.returncode == 0, r.stdout + r.stderr
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "h2@tess.test")
    _git(root, "config", "user.name", "h2")
    _git(root, "config", "commit.gpgsign", "false")
    return _commit(root, "installed v2.0.0")


def _update(root: Path, run_cli):
    r = run_cli(root, "update", "--ref", "v2.1.0")
    assert r.returncode == 0, f"update failed:\n{r.stdout}\n{r.stderr}"
    return r


def _registries(root: Path, rel: str) -> tuple:
    pol = yaml.safe_load((root / rel).read_text(encoding="utf-8"))["policy"]
    return pol.get("verifier_keys"), pol.get("signoff_keys")


def _reset_policy_to_release(root: Path, engine):
    for rel in (POL_KEY, POL_LIVE):
        (root / rel).write_text(RELEASE_POLICY, encoding="utf-8")
    lock = yaml.safe_load((root / ".tess" / "tess.lock").read_text(encoding="utf-8"))
    lock["files"][POL_KEY]["base_sha"] = engine.sha256_bytes(RELEASE_POLICY.encode("utf-8"))
    (root / ".tess" / "tess.lock").write_text(yaml.safe_dump(lock), encoding="utf-8")


@needs_gpg
def test_update_keeps_the_users_empty_key_registries(project, gpg_key, tmp_path, run_cli, engine):
    """A real `tessctl update` must not re-introduce the maintainers' key."""
    base = _installed(project, gpg_key, tmp_path, run_cli, engine)
    r = _update(project.root, run_cli)
    for rel in (POL_KEY, POL_LIVE):
        assert _registries(project.root, rel) == ({}, {}), r.stdout
    assert (project.root / NEW_KEY).is_file()              # the new core file was adopted
    head = _commit(project.root, "tessctl update v2.1.0")
    r, out = _gate_ci(project.root, base, head)
    assert r.returncode == 0 and out["blocked"] is False, out
    assert out["release_proof"]["status"] == "accepted"
    assert _tessctl(project.root, "verify").returncode == 0


@needs_gpg
def test_update_plus_policy_reset_to_the_release_is_refused(project, gpg_key, tmp_path, run_cli,
                                                           engine):
    base = _installed(project, gpg_key, tmp_path, run_cli, engine)
    _update(project.root, run_cli)
    _reset_policy_to_release(project.root, engine)
    head = _commit(project.root, "update + restore the maintainers' verifier key")
    r, out = _gate_ci(project.root, base, head)
    assert r.returncode == 1 and out["blocked"] is True, out


@needs_gpg
def test_reused_proof_cannot_reset_policy_later(project, gpg_key, tmp_path, run_cli, engine):
    """After a genuine update, the committed proof is re-used: the lock does
    not advance, so nothing is exempt."""
    _installed(project, gpg_key, tmp_path, run_cli, engine)
    _update(project.root, run_cli)
    updated = _commit(project.root, "tessctl update v2.1.0")
    _reset_policy_to_release(project.root, engine)
    head = _commit(project.root, "restore the maintainers' verifier key")
    r, out = _gate_ci(project.root, updated, head)
    assert r.returncode == 1 and out["blocked"] is True, out
    assert out["release_proof"]["status"] == "rejected"
    assert out["release_proof"]["reason_code"] == "lock_not_advanced"


@needs_gpg
def test_release_file_that_is_not_core_managed_needs_a_verdict(project, gpg_key, tmp_path,
                                                                run_cli, engine):
    base = _installed(project, gpg_key, tmp_path, run_cli, engine)
    _update(project.root, run_cli)
    p = project.root / EXTRA_WF
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("on: push\njobs: {}\n", encoding="utf-8")
    head = _commit(project.root, "update + an unmanaged workflow from the release tree")
    r, out = _gate_ci(project.root, base, head)
    assert r.returncode == 1 and out["blocked"] is True, out


@needs_gpg
def test_proof_without_a_lock_change_exempts_nothing(project, gpg_key, tmp_path, run_cli, engine):
    """Copy the release's guardrails + proof in by hand, leave tess.lock alone."""
    base = _installed(project, gpg_key, tmp_path, run_cli, engine)
    root = project.root
    lock_before = (root / ".tess" / "tess.lock").read_bytes()
    _update(root, run_cli)
    (root / ".tess" / "tess.lock").write_bytes(lock_before)
    head = _commit(root, "release bytes without the lock")
    r, out = _gate_ci(root, base, head)
    assert r.returncode == 1 and out["blocked"] is True, out
    assert out["release_proof"]["reason_code"] == "lock_not_advanced"


def test_policy_carry_registries_round_trips(engine):
    wizard = engine._policy_reset_registries_text(RELEASE_POLICY)
    assert engine._policy_carry_registries(RELEASE_POLICY, wizard) == wizard
    assert engine._policy_carry_registries(wizard, RELEASE_POLICY) == RELEASE_POLICY
    assert engine._policy_carry_registries(RELEASE_POLICY, RELEASE_POLICY) == RELEASE_POLICY


# ---------------------------------------------------------------------------
# H3 — every pushed commit is scanned, not just the tip
# ---------------------------------------------------------------------------

@needs_git
def test_data_only_in_history_is_refused(repo, fake_path):
    path_env, set_gh = fake_path
    _install(repo)
    _add_client(repo)
    _rg_git(repo, "rm", "-rq", "brain/clients")
    sha = _commit_all(repo, "remove the client data again")
    set_gh("public")
    r = _prepush(repo, path_env, GH_URL, sha)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "brain/clients/acme/AGENTS.md" in r.stderr


@needs_git
def test_removing_data_the_remote_already_has_is_allowed(repo, fake_path):
    path_env, set_gh = fake_path
    _install(repo)
    leaked = _add_client(repo)
    _rg_git(repo, "rm", "-rq", "brain/clients")
    sha = _commit_all(repo, "remove the leaked client data")
    set_gh("public")
    stdin = f"refs/heads/main {sha} refs/heads/main {leaked}\n"
    r = subprocess.run([str(repo / ".git" / "hooks" / "pre-push"), "origin", GH_URL], cwd=repo,
                       input=stdin, capture_output=True, text=True,
                       env={**os.environ, "PATH": path_env})
    assert r.returncode == 0, r.stdout + r.stderr


@needs_git
def test_non_ascii_data_path_in_history_is_reported_by_name(repo, fake_path):
    path_env, set_gh = fake_path
    _install(repo)
    d = repo / "clients" / "café"
    d.mkdir(parents=True)
    (d / "notes.md").write_text("client notes\n")
    _commit_all(repo, "client data")
    _rg_git(repo, "rm", "-rq", "clients/café")
    sha = _commit_all(repo, "gone again")
    set_gh("public")
    r = _prepush(repo, path_env, GH_URL, sha)
    assert r.returncode == 1 and "clients/café/notes.md" in r.stderr, r.stdout + r.stderr


@needs_gpg
def test_update_with_a_non_trust_policy_change_passes(project, gpg_key, tmp_path, run_cli, engine):
    """The release edits policy.yaml outside rules and key registries: the
    update keeps the user's registries and the gate accepts it."""
    base = _installed(project, gpg_key, tmp_path, run_cli, engine,
                      policy_extra="# upstream note: nothing about trust changed\n")
    _update(project.root, run_cli)
    for rel in (POL_KEY, POL_LIVE):
        text = (project.root / rel).read_text(encoding="utf-8")
        assert "upstream note" in text and _registries(project.root, rel) == ({}, {})
    head = _commit(project.root, "tessctl update v2.1.0")
    changed = _git(project.root, "diff", "--name-only", base, head).split()
    assert POL_KEY in changed and POL_LIVE in changed
    r, out = _gate_ci(project.root, base, head)
    assert r.returncode == 0 and out["blocked"] is False, out


@needs_gpg
def test_forged_lock_entry_for_a_release_file_the_release_does_not_manage(project, gpg_key,
                                                                         tmp_path, run_cli, engine):
    base = _installed(project, gpg_key, tmp_path, run_cli, engine)
    root = project.root
    _update(root, run_cli)
    for rel in (EXTRA_WF_KEY, EXTRA_WF):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("on: push\njobs: {}\n", encoding="utf-8")
    lock = yaml.safe_load((root / ".tess" / "tess.lock").read_text(encoding="utf-8"))
    lock["files"][EXTRA_WF_KEY] = {"status": "core-managed", "tier": "security",
                                   "live_path": EXTRA_WF,
                                   "base_sha": engine.sha256_bytes(b"on: push\njobs: {}\n")}
    (root / ".tess" / "tess.lock").write_text(yaml.safe_dump(lock), encoding="utf-8")
    head = _commit(root, "update + a forged lock entry")
    r, out = _gate_ci(root, base, head)
    assert r.returncode == 1 and out["blocked"] is True, out
