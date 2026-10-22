"""
v1.0 security review round 3, N2 (HIGH): the publish-remote guard must never
let a separate advertisement from an UNTRUSTED destination waive enforcement.

The round-2 fix asked the destination (`git ls-remote`) which commits it
already holds and excluded them from the check. `ls-remote` is a separate
upload-pack conversation from the push's own receive-pack negotiation, so a
malicious server could advertise NO refs to the push (git then uploads the
whole history) while advertising the pushed SHA to `ls-remote` (the guard then
excluded that commit and all of its history and allowed the push).

Now the only history the guard excludes for an unknown or public destination
is each ref's pre-push `remote_sha` (git's own push negotiation). Trusted
destinations (a local path, a GitHub repository `gh` confirms private, or a
`tess.privateRemote` allowlist entry) are allowed without asking the remote.

The "lying server" is simulated with a `url.<bare>.insteadOf` rewrite: every
query to the GitHub URL reaches a local bare repository that holds the pushed
history, while the pre-push stdin says the push negotiation advertised nothing
(remote_sha all zeros). A logging `git` wrapper on PATH proves the guard never
asks the destination (`ls-remote`) at all.
"""

from __future__ import annotations

import os
import subprocess
import shutil

import pytest

from test_publish_remote_guard import (  # noqa: F401  (pytest fixtures)
    GH_URL, ZERO, _add_client, _commit_all, _git, _install, fake_path, repo,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git required")


@pytest.fixture
def git_log(fake_path, tmp_path):
    """Replace the fake PATH's git with a wrapper that logs every call."""
    path_env, set_gh = fake_path
    bindir = path_env.split(":", 1)[0]
    log = tmp_path / "git-calls.log"
    wrapper = os.path.join(bindir, "git")
    os.unlink(wrapper)
    with open(wrapper, "w") as fh:
        fh.write(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\nexec "{shutil.which("git")}" "$@"\n')
    os.chmod(wrapper, 0o755)
    log.write_text("")
    return path_env, set_gh, log


def _lying_server(repo, tmp_path, push_rev):
    """A 'server' whose upload-pack side (ls-remote) advertises `push_rev`."""
    srv = tmp_path / "srv"
    srv.mkdir()
    bare = srv / "brain.git"
    _git(tmp_path, "init", "-b", "main", "-q", "--bare", str(bare))
    _git(repo, "push", "-q", "--no-verify", str(bare), f"{push_rev}:refs/heads/main")
    _git(repo, "config", f"url.file://{srv}/.insteadOf", "https://github.com/acme-agency/")
    # sanity: a query to the GitHub URL really does advertise the pushed commit
    adv = _git(repo, "ls-remote", GH_URL).stdout
    assert _git(repo, "rev-parse", push_rev).stdout.strip() in adv


def _prepush(root, path_env, stdin, url=GH_URL, remote="origin"):
    return subprocess.run([str(root / ".git" / "hooks" / "pre-push"), remote, url],
                          cwd=root, input=stdin, capture_output=True, text=True,
                          env={**os.environ, "PATH": path_env})


def _line(sha, remote_sha=ZERO, ref="refs/heads/main"):
    return f"{ref} {sha} {ref} {remote_sha}\n"


@pytest.mark.parametrize("gh_mode", ["error", None, "public"])
def test_lying_server_advertising_the_pushed_sha_is_refused(repo, git_log, tmp_path, gh_mode):
    path_env, set_gh, log = git_log
    _install(repo)
    sha = _add_client(repo)
    _lying_server(repo, tmp_path, sha)
    set_gh(gh_mode)
    log.write_text("")
    r = _prepush(repo, path_env, _line(sha))  # receive-pack advertised nothing
    assert r.returncode == 1, r.stdout + r.stderr
    assert "REFUSED" in r.stderr and "brain/clients/acme/AGENTS.md" in r.stderr
    assert "Nothing was pushed." in r.stderr
    assert "ls-remote" not in log.read_text()  # the destination is never asked


def test_public_remote_with_data_only_in_old_history_is_refused(repo, git_log, tmp_path):
    """Data added then removed, and the destination claims (ls-remote) to hold
    that old history: a public remote that did not advertise it to the push
    still gets it, so the push is refused."""
    path_env, set_gh, _ = git_log
    _install(repo)
    _add_client(repo)
    _git(repo, "rm", "-rq", "brain/clients")
    tip = _commit_all(repo, "scrub")
    _lying_server(repo, tmp_path, "HEAD~1")
    set_gh("public")
    r = _prepush(repo, path_env, _line(tip))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "PUBLIC GitHub repository" in r.stderr
    assert "brain/clients/acme/AGENTS.md" in r.stderr


@pytest.mark.parametrize("gh_mode", ["public", "error"])
def test_genuine_prepush_remote_sha_still_excludes_known_history(repo, git_log, gh_mode):
    """Git's own push negotiation (the pre-push remote_sha) says the branch is
    already at the data commit: only the new, clean commit is published."""
    path_env, set_gh, log = git_log
    _install(repo)
    old = _add_client(repo)
    (repo / "README.md").write_text("framework only change\n")
    tip = _commit_all(repo, "clean")
    set_gh(gh_mode)
    log.write_text("")
    r = _prepush(repo, path_env, _line(tip, remote_sha=old))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ls-remote" not in log.read_text()


@pytest.mark.parametrize("trust", ["gh-private", "allowlist"])
def test_trusted_private_remote_with_genuine_history_is_allowed(repo, git_log, tmp_path, trust):
    path_env, set_gh, log = git_log
    _install(repo)
    sha = _add_client(repo)
    _lying_server(repo, tmp_path, sha)  # the remote really holds it
    if trust == "gh-private":
        set_gh("private")
    else:
        set_gh(None)
        _git(repo, "config", "--add", "tess.privateRemote", GH_URL)
    log.write_text("")
    r = _prepush(repo, path_env, _line(sha))
    assert r.returncode == 0, r.stdout + r.stderr
    calls = log.read_text()
    assert "ls-remote" not in calls
    assert calls.count(" log ") <= 1  # one scan; known history is not rescanned


def test_deletions_stay_pushable_to_a_lying_public_remote(repo, git_log, tmp_path):
    path_env, set_gh, _ = git_log
    _install(repo)
    sha = _add_client(repo)
    _lying_server(repo, tmp_path, sha)
    set_gh("public")
    stdin = f"(delete) {ZERO} refs/heads/old {sha}\n(delete) {ZERO} refs/heads/older {'b' * 40}\n"
    r = _prepush(repo, path_env, stdin)
    assert r.returncode == 0, r.stdout + r.stderr


def test_engine_has_no_destination_advertisement_path():
    """The ls-remote query is gone, not merely unused."""
    from test_publish_remote_guard import ENGINE
    src = ENGINE.read_text()
    assert "_publish_remote_held" not in src
    assert '"ls-remote"' not in src
