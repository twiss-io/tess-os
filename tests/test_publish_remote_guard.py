"""
v0.2.1 (2026-09-29 security review, HIGH): agency client data must not leak
to a public remote.

Agency mode stores real client data at brain/clients/<slug>/ (committed by
design), and nothing stopped a push of it to a public GitHub repository.
`tessctl gate install-hooks` now installs a pre-push guard
(`tessctl doctor --publish-remote`) that refuses a push carrying brain/ or
clients/ data unless the destination is local, confirmed private through
`gh`, or allowlisted in .git/config (`tess.privateRemote`) when visibility
cannot be checked. A confirmed-public remote is refused even if allowlisted.

Also: publish-clean (pre-commit) now blocks brain/**/.private/** and
**/.private/**.

These tests run the REAL installed hook script with the arguments and stdin
git passes it, a fake `gh` on PATH to stand in for GitHub, and one real
`git push` to a local bare remote to prove the hook is wired and stdin flows.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git required")

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE = REPO_ROOT / ".tess" / "bin" / "tessctl"
MANIFEST_SRC = REPO_ROOT / "tess.manifest.json"
GH_URL = "https://github.com/acme-agency/brain.git"
ZERO = "0" * 40
SENTINEL = "TESS-TEST-OPERATOR-PREPUSH-RAN"


def _git(root, *args, check=True, env=None, input_text=None):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                       env=env or os.environ, input=input_text)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr}")
    return r


def _commit_all(root, msg):
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@tess.test", "-c", "user.name=T", "-c", "commit.gpgsign=false",
         "commit", "-q", "-m", msg)
    return _git(root, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def fake_path(tmp_path):
    """PATH with python3 (this interpreter), git and bash, a switchable fake gh, and nothing else."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "python3").symlink_to(sys.executable)
    (bindir / "git").symlink_to(shutil.which("git"))
    gh = bindir / "gh"

    def set_gh(mode):
        if mode is None:
            gh.unlink(missing_ok=True)
            return
        body = {"public": "echo false", "private": "echo true",
                "error": "echo 'HTTP 404: Not Found' >&2; exit 1"}[mode]
        gh.write_text(f"#!/bin/sh\n{body}\n")
        gh.chmod(0o755)

    set_gh(None)
    return f"{bindir}:/bin:/usr/bin", set_gh


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "inst"
    (root / ".tess" / "bin").mkdir(parents=True)
    shutil.copy2(ENGINE, root / ".tess" / "bin" / "tessctl")
    shutil.copy2(MANIFEST_SRC, root / "tess.manifest.json")
    (root / ".tess" / "tess.lock").write_text('{"schema": 1, "framework": {}, "files": {}}')
    _git(tmp_path, "init", "-b", "main", "-q", str(root))
    (root / "README.md").write_text("hello\n")
    (root / "clients" / "_template").mkdir(parents=True)
    (root / "clients" / "_template" / "CLAUDE.md").write_text("scaffold\n")
    (root / "brain").mkdir()
    (root / "brain" / ".gitkeep").write_text("")
    _commit_all(root, "framework only")
    return root


def _engine():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("tessctl_remote_guard_under_test", str(ENGINE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _install(root, path_env=None):
    """Install ONLY the public-remote guard (the gate/gitleaks guards that
    `gate install-hooks` also installs need gpg/gitleaks and are tested elsewhere)."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _engine()._remote_install_git_hooks(root)
    return buf.getvalue()


def test_gate_install_hooks_installs_the_remote_guard(repo):
    r = subprocess.run([sys.executable, str(ENGINE), "gate", "install-hooks"], cwd=repo,
                       capture_output=True, text=True, env={**os.environ, "TESS_ROOT": str(repo)})
    assert r.returncode == 0, r.stdout + r.stderr
    hook = (repo / ".git" / "hooks" / "pre-push").read_text()
    assert "# tess-remote-guard v1" in hook and "doctor --publish-remote" in hook
    # it sits above the other pre-push guards, so it runs first
    assert hook.index("# tess-remote-guard v1") < hook.index("# tess-gitleaks-guard v1")


def _prepush(root, path_env, url, sha, remote="origin"):
    """Run the installed pre-push hook exactly as git would call it."""
    stdin = f"refs/heads/main {sha} refs/heads/main {ZERO}\n"
    return subprocess.run([str(root / ".git" / "hooks" / "pre-push"), remote, url],
                          cwd=root, input=stdin, capture_output=True, text=True,
                          env={**os.environ, "PATH": path_env})


def _add_client(root):
    d = root / "brain" / "clients" / "acme"
    d.mkdir(parents=True)
    (d / "AGENTS.md").write_text("# START HERE\nAcme Pte Ltd, contract value S$120k\n")
    return _commit_all(root, "client data")


def test_public_github_remote_is_refused(repo, fake_path):
    path_env, set_gh = fake_path
    _install(repo, path_env)
    sha = _add_client(repo)
    set_gh("public")
    r = _prepush(repo, path_env, GH_URL, sha)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "PUBLIC GitHub repository" in r.stderr
    assert "brain/clients/acme/AGENTS.md" in r.stderr


def test_public_remote_refused_even_when_allowlisted(repo, fake_path):
    path_env, set_gh = fake_path
    _install(repo, path_env)
    sha = _add_client(repo)
    _git(repo, "config", "--add", "tess.privateRemote", GH_URL)
    set_gh("public")
    assert _prepush(repo, path_env, GH_URL, sha).returncode == 1


def test_private_github_remote_is_allowed(repo, fake_path):
    path_env, set_gh = fake_path
    _install(repo, path_env)
    sha = _add_client(repo)
    set_gh("private")
    r = _prepush(repo, path_env, GH_URL, sha)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("gh_mode", [None, "error"])
def test_unverifiable_remote_refused_until_allowlisted(repo, fake_path, gh_mode):
    path_env, set_gh = fake_path
    _install(repo, path_env)
    sha = _add_client(repo)
    set_gh(gh_mode)
    r = _prepush(repo, path_env, GH_URL, sha)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "could not" in r.stderr and "git config --add tess.privateRemote" in r.stderr
    _git(repo, "config", "--add", "tess.privateRemote", GH_URL)
    r = _prepush(repo, path_env, GH_URL, sha)
    assert r.returncode == 0, r.stdout + r.stderr


def test_non_github_host_needs_allowlist(repo, fake_path):
    path_env, set_gh = fake_path
    _install(repo, path_env)
    sha = _add_client(repo)
    set_gh("private")  # gh cannot vouch for a non-GitHub host
    assert _prepush(repo, path_env, "git@gitlab.example.com:acme/brain.git", sha).returncode == 1


@pytest.mark.parametrize("rel", ["clients/acme/CLAUDE.md", "brain/agency/AGENTS.md"])
def test_any_brain_or_clients_path_counts_as_data(repo, fake_path, rel):
    path_env, set_gh = fake_path
    _install(repo, path_env)
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text("real data\n")
    sha = _commit_all(repo, "data")
    set_gh("public")
    assert _prepush(repo, path_env, GH_URL, sha).returncode == 1


def test_framework_only_push_to_public_remote_is_allowed(repo, fake_path):
    """The framework repo itself (clients/_template, brain/.gitkeep) stays pushable."""
    path_env, set_gh = fake_path
    _install(repo, path_env)
    set_gh("public")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    r = _prepush(repo, path_env, GH_URL, sha)
    assert r.returncode == 0, r.stdout + r.stderr


def test_ref_deletion_carries_no_data(repo, fake_path):
    path_env, set_gh = fake_path
    _install(repo, path_env)
    _add_client(repo)
    set_gh("public")
    stdin = f"(delete) {ZERO} refs/heads/old {'a' * 40}\n"
    r = subprocess.run([str(repo / ".git" / "hooks" / "pre-push"), "origin", GH_URL], cwd=repo,
                       input=stdin, capture_output=True, text=True, env={**os.environ, "PATH": path_env})
    assert r.returncode == 0, r.stdout + r.stderr


def test_real_push_to_local_remote_runs_guard_and_operator_hook(repo, fake_path, tmp_path):
    """End to end through git: the guard is spliced above an operator's own
    pre-push hook, a local remote is allowed, and the operator hook still runs."""
    path_env, _ = fake_path
    hook = repo / ".git" / "hooks" / "pre-push"
    hook.write_text(f'#!/usr/bin/env bash\ncat > /dev/null\necho {SENTINEL} >> "{tmp_path}/op.log"\n')
    hook.chmod(0o755)
    out = _install(repo)
    assert "public-remote guard was spliced ABOVE" in out
    assert "already v1" in _install(repo)
    _add_client(repo)
    bare = tmp_path / "remote.git"
    _git(tmp_path, "init", "-b", "main", "-q", "--bare", str(bare))
    _git(repo, "remote", "add", "origin", str(bare))
    env = {**os.environ, "PATH": path_env}
    r = _git(repo, "push", "-q", "origin", "HEAD:refs/heads/main", check=False, env=env)
    assert r.returncode == 0, r.stderr
    assert SENTINEL in (tmp_path / "op.log").read_text()


@pytest.mark.parametrize("rel", ["brain/.private/journal.md",
                                 "brain/life/areas/health/.private/labs.md",
                                 ".private/notes.md"])
def test_publish_clean_blocks_private_brain_folders(repo, rel):
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text("private\n")
    _git(repo, "add", "-f", rel)
    r = subprocess.run([sys.executable, str(ENGINE), "doctor", "--publish-clean"], cwd=repo,
                       capture_output=True, text=True, env={**os.environ, "TESS_ROOT": str(repo)})
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"BLOCKED  {rel}" in r.stdout
