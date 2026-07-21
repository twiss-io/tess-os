"""
DATA-LEAK-SAFETY (issue #92), fix 4 — promote gitleaks to a LOCAL pre-push
hook, in addition to CI's already-existing `secret-scan` job
(.github/workflows/ci.yml). Clearly secrets-only: it does NOT cover PII or
business-data paths (that's tests/test_publish_clean_gate.py's job). CI
remains the enforced backstop regardless of whether gitleaks happens to be
installed on a given contributor's machine — a missing local binary WARNS
and falls through rather than blocking every push.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

HAS_GIT = shutil.which("git") is not None
HAS_GITLEAKS = shutil.which("gitleaks") is not None
pytestmark = pytest.mark.skipif(not HAS_GIT, reason="git required")

USER_SENTINEL = "TESS-TEST-USER-PREPUSH-RAN"


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


def _write_user_prepush_hook(root):
    hp = root / ".git" / "hooks" / "pre-push"
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text(
        "#!/usr/bin/env bash\n"
        "cat > /dev/null\n"  # consume stdin like a real hook would
        f'echo "{USER_SENTINEL}" >> "$(git rev-parse --show-toplevel)/.user_prepush_log"\n'
        "exit 0\n"
    )
    os.chmod(str(hp), 0o755)
    return hp


# ---------------------------------------------------------------------------
# Structural: standalone install, idempotency, splice, coexistence
# ---------------------------------------------------------------------------

def test_no_existing_hook_installs_standalone(engine, tmp_path):
    _init_repo(tmp_path)
    engine._gitleaks_install_git_hooks(tmp_path)
    text = (tmp_path / ".git" / "hooks" / "pre-push").read_text()
    assert "# tess-gitleaks-guard v1" in text
    assert "# tess-gitleaks-guard end" not in text
    assert subprocess.run(["bash", "-n", str(tmp_path / ".git" / "hooks" / "pre-push")]).returncode == 0
    assert os.access(tmp_path / ".git" / "hooks" / "pre-push", os.X_OK)


def test_install_is_idempotent(engine, tmp_path):
    _init_repo(tmp_path)
    engine._gitleaks_install_git_hooks(tmp_path)
    first = (tmp_path / ".git" / "hooks" / "pre-push").read_text()
    engine._gitleaks_install_git_hooks(tmp_path)
    second = (tmp_path / ".git" / "hooks" / "pre-push").read_text()
    assert first == second
    assert second.count("# tess-gitleaks-guard v1") == 1


def test_splices_above_pre_existing_hook_and_feeds_it_the_same_stdin(engine, tmp_path):
    _init_repo(tmp_path)
    _write_user_prepush_hook(tmp_path)
    engine._gitleaks_install_git_hooks(tmp_path)

    text = (tmp_path / ".git" / "hooks" / "pre-push").read_text()
    assert "# tess-gitleaks-guard v1" in text
    assert "# tess-gitleaks-guard end" in text
    assert text.index("# tess-gitleaks-guard end") < text.index(USER_SENTINEL.split()[0])
    assert subprocess.run(["bash", "-n", str(tmp_path / ".git" / "hooks" / "pre-push")]).returncode == 0


# ---------------------------------------------------------------------------
# Real end-to-end: the hook actually fires against a real git push
# ---------------------------------------------------------------------------

@pytest.fixture
def push_repo(tmp_path):
    repo = tmp_path / "repo"
    bare = tmp_path / "origin.git"
    repo.mkdir()
    _init_repo(repo)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "init", "--bare", "-q", str(bare))
    _git(repo, "remote", "add", "origin", str(bare))
    assert _git(repo, "push", "-u", "origin", "HEAD:main", check=False).returncode == 0
    return repo


@pytest.mark.skipif(not HAS_GITLEAKS, reason="gitleaks binary required for the e2e fire test")
def test_e2e_blocks_a_real_secret(engine, push_repo):
    engine._gitleaks_install_git_hooks(push_repo)
    # Built at runtime, never as one contiguous literal in THIS file's own
    # source bytes: gitleaks' full-history CI scan (.github/workflows/ci.yml)
    # scans tess-os's own tracked source, and an AKIA[0-9A-Z]{16}-shaped
    # literal sitting directly in a committed .py file matches its
    # aws-access-token rule regardless of test-fixture intent (this exact
    # false positive was hit and fixed during this PR's own CI run). The
    # THROWAWAY test repo's committed content still gets the full contiguous
    # shape at test-execution time, so the real gitleaks binary still has a
    # genuine pattern to detect.
    fake_aws_key = "AKIA" + "ABCDEFGHIJKLMNOP"
    (push_repo / "creds.txt").write_text(f"AWS_KEY={fake_aws_key}\n", encoding="utf-8")
    _git(push_repo, "add", "-A")
    _git(push_repo, "commit", "-q", "-m", "oops a secret")

    r = _git(push_repo, "push", "origin", "HEAD:main", check=False)
    assert r.returncode != 0, "local gitleaks pre-push hook did not fire / did not block a real secret"
    assert "tess-gitleaks-guard" in (r.stdout + r.stderr) or "BLOCKED" in (r.stdout + r.stderr)


@pytest.mark.skipif(not HAS_GITLEAKS, reason="gitleaks binary required")
def test_e2e_allows_a_clean_push(engine, push_repo):
    engine._gitleaks_install_git_hooks(push_repo)
    (push_repo / "docs.md").write_text("just some prose, no secrets here\n", encoding="utf-8")
    _git(push_repo, "add", "-A")
    _git(push_repo, "commit", "-q", "-m", "clean change")

    r = _git(push_repo, "push", "origin", "HEAD:main", check=False)
    assert r.returncode == 0, f"clean push blocked: {r.stdout}{r.stderr}"


def test_missing_gitleaks_binary_warns_and_falls_through(engine, push_repo, monkeypatch):
    """A contributor without gitleaks installed locally must not be blocked
    from pushing at all — CI's secret-scan job is the enforced backstop
    regardless. Simulated by installing the hook then invoking it with a
    PATH that has no `gitleaks` on it."""
    engine._gitleaks_install_git_hooks(push_repo)
    (push_repo / "docs.md").write_text("clean\n", encoding="utf-8")
    _git(push_repo, "add", "-A")
    _git(push_repo, "commit", "-q", "-m", "clean change, no gitleaks on PATH")

    # Build a PATH with bash + git (needed by the hook's own shebang / `git
    # rev-parse`) but no gitleaks — /bin + /usr/bin cover bash/sh on macOS and
    # Linux without pulling in a package-manager bin dir that might have
    # gitleaks (e.g. Homebrew's /opt/homebrew/bin or /usr/local/bin).
    git_dir = os.path.dirname(shutil.which("git"))
    env = {**os.environ, "PATH": f"/bin:/usr/bin:{git_dir}"}
    assert shutil.which("gitleaks", path=env["PATH"]) is None, (
        "test setup bug: gitleaks is still reachable on the stripped-down PATH"
    )
    r = subprocess.run(
        ["git", "-C", str(push_repo), "push", "origin", "HEAD:main"],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, f"push must succeed (warn, not block) when gitleaks is absent: {r.stdout}{r.stderr}"
    assert "gitleaks not installed locally" in (r.stdout + r.stderr)
