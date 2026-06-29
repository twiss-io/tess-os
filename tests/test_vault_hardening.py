"""
Vault hardening regression tests (fix/tess-vault-hardening).

Each test fails on the pre-fix engine and passes after the fix:

  B1  _vault_store_identity_keychain — the macOS branch must hand the vault AGE
      private key to `security` on STDIN, never on argv (argv is world-visible
      via `ps`, leaking the vault master key).
  B2  installed pre-commit / pre-push secret-guard — the content scan must read
      the VERSIONED blob (`git show`) instead of the working-tree file, so a
      secret staged-then-scrubbed (pre-commit) or pushed-then-altered (pre-push)
      is still caught.
  B3  _vault_mask_value — a short value must be fully redacted; a 4-char prefix
      plus a 4-char suffix would otherwise reveal the whole of any value of 12
      chars or fewer.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

HAS_GIT = shutil.which("git") is not None

# Secret-shaped literals are assembled at runtime so this source file carries no
# contiguous secret the repo's own vault pre-commit guard would flag.
AGE_SECRET = "AGE-SECRET-KEY-" + "A" * 59


# ===========================================================================
# B1 — keychain store never leaks the key on argv
# ===========================================================================

def test_keychain_store_passes_key_on_stdin_not_argv(engine, monkeypatch):
    """The macOS `security add-generic-password` invocation must carry the key on
    stdin (input=...), never as an argv element (which `ps` exposes)."""
    monkeypatch.setattr(engine.sys, "platform", "darwin")
    priv = AGE_SECRET
    calls = []

    def fake_run(argv, *a, **kw):
        calls.append((argv, kw))
        if "find-generic-password" in argv:
            # read-back verification path returns the stored key
            return subprocess.CompletedProcess(
                argv, 0, stdout=(priv + "\n").encode(), stderr=b""
            )
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(engine.subprocess, "run", fake_run)

    assert engine._vault_store_identity_keychain(priv) is True

    add_argv, add_kw = calls[0]
    assert "add-generic-password" in add_argv
    # The key must NOT appear in ANY argv element.
    assert all(priv not in str(part) for part in add_argv), \
        f"vault key leaked onto argv: {add_argv}"
    # The key MUST be delivered on stdin.
    assert "input" in add_kw and add_kw["input"] is not None
    assert priv.encode() in add_kw["input"]
    # argv terminates with a bare -w (value sourced from stdin).
    assert add_argv[-1] == "-w"


def test_keychain_store_returns_false_on_readback_mismatch(engine, monkeypatch):
    """If `security` exits 0 but the read-back does not match, the store is
    treated as failed so init falls back to the 0600 identity file rather than
    persisting a corrupted (unusable) key."""
    monkeypatch.setattr(engine.sys, "platform", "darwin")

    def fake_run(argv, *a, **kw):
        if "find-generic-password" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=b"WRONG\n", stderr=b"")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(engine.subprocess, "run", fake_run)
    assert engine._vault_store_identity_keychain(AGE_SECRET) is False


# ===========================================================================
# B2 — installed hooks scan the versioned blob, not the working tree
# ===========================================================================

def _git(root, *args, check=True, input_text=None):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@tess.test",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@tess.test",
    }
    r = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True, env=env, input=input_text)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}\n{r.stdout}")
    return r


def _init_repo(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@tess.test")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")


def test_generated_hooks_scan_with_git_show(engine, tmp_path):
    """Both hook bodies must scan versioned content via `git show`, not a bare
    working-tree grep ([ -f "$file" ] gate is gone)."""
    if not HAS_GIT:
        pytest.skip("git required")
    _init_repo(tmp_path)
    engine._vault_install_git_hooks(tmp_path)
    pre_commit = (tmp_path / ".git" / "hooks" / "pre-commit").read_text()
    pre_push = (tmp_path / ".git" / "hooks" / "pre-push").read_text()

    for body in (pre_commit, pre_push):
        assert "git show" in body
        # the old working-tree existence gate must be gone
        assert '[ -f "$file" ]' not in body
        # secret patterns are still present
        assert "AGE-SECRET-KEY-" in body
    # pre-commit reads the staged index blob, pre-push the pushed sha blob
    assert 'git show "$blob"' in pre_commit
    assert "${local_sha}:${_f}" in pre_push


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_precommit_blocks_staged_then_scrubbed_secret(engine, tmp_path):
    """A secret staged then scrubbed from the working tree must still be blocked
    (the pre-fix hook grepped the clean working tree and let it through)."""
    _init_repo(tmp_path)
    engine._vault_install_git_hooks(tmp_path)

    cfg = tmp_path / "config.txt"
    cfg.write_text(f"key = {AGE_SECRET}\n")
    _git(tmp_path, "add", "config.txt")
    # Scrub the working-tree copy; the STAGED index blob still holds the secret.
    cfg.write_text("key = REDACTED\n")

    r = _git(tmp_path, "commit", "-m", "sneaky", check=False)
    assert r.returncode != 0, "staged-then-scrubbed secret slipped past pre-commit"
    assert "AGE PRIVATE KEY" in (r.stderr + r.stdout)


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_precommit_allows_clean_staged_file(engine, tmp_path):
    """A clean staged file must commit normally (no false positive)."""
    _init_repo(tmp_path)
    engine._vault_install_git_hooks(tmp_path)
    (tmp_path / "ok.txt").write_text("just some prose, nothing secret\n")
    _git(tmp_path, "add", "ok.txt")
    r = _git(tmp_path, "commit", "-m", "clean", check=False)
    assert r.returncode == 0, f"clean commit was blocked: {r.stderr}\n{r.stdout}"


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_prepush_blocks_secret_in_pushed_commit_altered_in_worktree(engine, tmp_path):
    """A secret present in a pushed commit but altered in the working tree must
    still be blocked — the pre-push scan reads the pushed sha blob, not HEAD's
    working tree."""
    _init_repo(tmp_path)
    engine._vault_install_git_hooks(tmp_path)
    hook_path = tmp_path / ".git" / "hooks" / "pre-push"

    # Base commit (benign), then a commit that introduces the secret.
    (tmp_path / "a.txt").write_text("hello\n")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "c1")
    base_sha = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    cfg = tmp_path / "config.txt"
    cfg.write_text(f"key = {AGE_SECRET}\n")
    _git(tmp_path, "add", "config.txt")
    _git(tmp_path, "commit", "--no-verify", "-m", "c2-with-secret")
    head_sha = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    # Scrub the working tree: a working-tree grep would now see nothing.
    cfg.write_text("key = REDACTED\n")

    ref_line = f"refs/heads/main {head_sha} refs/heads/main {base_sha}\n"
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@tess.test",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@tess.test",
    }
    r = subprocess.run(
        ["bash", str(hook_path), "origin", "git@example.com:repo.git"],
        cwd=str(tmp_path), input=ref_line, capture_output=True, text=True, env=env,
    )
    assert r.returncode != 0, "secret in pushed commit slipped past pre-push"
    assert "AGE PRIVATE KEY" in (r.stderr + r.stdout)


# ===========================================================================
# B3 — short values are fully redacted (no overlapping prefix/suffix leak)
# ===========================================================================

@pytest.mark.parametrize("value", [
    "abcdefgh",       # 8 chars: first4 + last4 == whole value under the old rule
    "abcdefg",        # 7 chars: prefix/suffix overlap
    "abcdefghijkl",   # 12 chars: boundary — still fully redacted
])
def test_mask_short_value_is_fully_redacted(engine, value):
    masked = engine._vault_mask_value(value, "svc/key")
    assert value not in masked
    assert value[:4] not in masked
    assert value[-4:] not in masked
    assert set(masked) == {"•"}


def test_mask_long_value_shows_only_ends(engine):
    value = "ABCD" + "m" * 32 + "WXYZ"   # 40 chars, not secret-shaped
    masked = engine._vault_mask_value(value, "svc/key")
    assert value not in masked            # whole value never present
    assert masked.startswith("ABCD")      # short prefix shown
    assert "WXYZ" in masked               # short suffix shown
    assert "•" * 8 in masked              # masked middle
    assert value[4:-4] not in masked      # the sensitive middle is absent
