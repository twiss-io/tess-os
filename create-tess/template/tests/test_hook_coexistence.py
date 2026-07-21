"""
Finding 9 (Cyra MEDIUM) — git hook coexistence.

`_vault_install_git_hooks()` must never silently neuter an adopter's pre-existing
pre-commit / pre-push hook. When a hook already exists, the vault guard is spliced
ABOVE it inside a containment subshell so that:

  * a secret/vault VIOLATION still BLOCKS the commit/push (exit non-zero), but
  * a CLEAN result FALLS THROUGH to the operator's original hook, which still runs.

These tests prove both directions end-to-end with a real git repo, plus the
structural / idempotency / legacy-upgrade invariants.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess

import pytest

HAS_GIT = shutil.which("git") is not None

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
    """A pre-existing operator hook that records that it ran, then exits 0."""
    hp = root / ".git" / "hooks" / name
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text(
        "#!/usr/bin/env bash\n"
        "# operator's own pre-existing hook (e.g. a linter / secret scanner)\n"
        f'echo "{USER_SENTINEL}" >> "$(git rev-parse --show-toplevel)/.user_hook_log"\n'
        "exit 0\n"
    )
    os.chmod(str(hp), 0o755)
    return hp


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_precommit_splice_falls_through_on_clean(engine, tmp_path):
    """A pre-existing pre-commit hook STILL RUNS after a clean guard pass."""
    _init_repo(tmp_path)
    _write_user_hook(tmp_path, "pre-commit")

    engine._vault_install_git_hooks(tmp_path)

    hook_text = (tmp_path / ".git" / "hooks" / "pre-commit").read_text()
    # Guard + user hook coexist; guard is contained in a subshell; end sentinel
    # sits BEFORE the user content so the user hook is reachable (not dead code).
    assert "# tess-vault-guard v2" in hook_text
    assert "if (" in hook_text
    assert "# tess-vault-guard end" in hook_text
    assert USER_SENTINEL in hook_text
    assert hook_text.index("# tess-vault-guard end") < hook_text.index(USER_SENTINEL)
    # bash must accept the spliced script.
    assert subprocess.run(["bash", "-n", str(tmp_path / ".git" / "hooks" / "pre-commit")]).returncode == 0

    # Clean commit: must succeed AND the operator's hook must have run.
    (tmp_path / "main.py").write_text("print('hi')\n")
    _git(tmp_path, "add", "main.py")
    r = _git(tmp_path, "commit", "-m", "clean", check=False)
    assert r.returncode == 0, f"clean commit was blocked: {r.stderr}"
    log = tmp_path / ".user_hook_log"
    assert log.exists() and USER_SENTINEL in log.read_text(), "operator hook was neutered"


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_precommit_splice_still_blocks_violation(engine, tmp_path):
    """A staged vault/secret file is BLOCKED, and the user hook does NOT run."""
    _init_repo(tmp_path)
    _write_user_hook(tmp_path, "pre-commit")
    engine._vault_install_git_hooks(tmp_path)

    # Stage a forbidden vault artifact (path-shape violation: *.age).
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "leak.age").write_text("ciphertext\n")
    _git(tmp_path, "add", "-f", "secrets/leak.age")

    r = _git(tmp_path, "commit", "-m", "should-block", check=False)
    assert r.returncode != 0, "guard failed to block a staged .age file"
    assert "TESS VAULT GUARD" in (r.stderr + r.stdout)
    # The block happened BEFORE fall-through — operator hook must not have run.
    assert not (tmp_path / ".user_hook_log").exists(), "user hook ran despite a blocked commit"


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_install_is_idempotent_and_preserves_user_hook(engine, tmp_path):
    """Re-running install detects v2 and leaves the operator's hook intact."""
    _init_repo(tmp_path)
    _write_user_hook(tmp_path, "pre-commit")
    engine._vault_install_git_hooks(tmp_path)
    first = (tmp_path / ".git" / "hooks" / "pre-commit").read_text()

    engine._vault_install_git_hooks(tmp_path)  # second run — should skip (v2)
    second = (tmp_path / ".git" / "hooks" / "pre-commit").read_text()

    assert first == second, "second install mutated an already-v2 hook"
    assert second.count("# tess-vault-guard v2") == 1, "guard marker duplicated"
    assert USER_SENTINEL in second


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_no_existing_hook_installs_standalone(engine, tmp_path):
    """With no pre-existing hook, the standalone guard (terminal exit 0) installs."""
    _init_repo(tmp_path)
    engine._vault_install_git_hooks(tmp_path)
    hook_text = (tmp_path / ".git" / "hooks" / "pre-commit").read_text()
    assert "# tess-vault-guard v2" in hook_text
    # Standalone form has no splice subshell / end sentinel.
    assert "# tess-vault-guard end" not in hook_text
    assert subprocess.run(["bash", "-n", str(tmp_path / ".git" / "hooks" / "pre-commit")]).returncode == 0


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_legacy_prepend_is_re_spliced_to_fall_through(engine, tmp_path):
    """
    A hook left in the OLD buggy prepend form (guard ends with terminal `exit 0`,
    operator content stranded below as dead code) is re-spliced on upgrade so the
    operator's hook becomes reachable again.
    """
    _init_repo(tmp_path)
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    # Synthesize a legacy-form hook: marker + minimal guard body ending in the
    # terminal `fi\nexit 0`, then the operator's hook stranded below.
    legacy = (
        "#!/usr/bin/env bash\n"
        "# tess-vault-guard v1\n"
        "set -euo pipefail\n"
        'STAGED="$(git diff --cached --name-only 2>/dev/null || true)"\n'
        'if [ -n "$STAGED" ]; then :; fi\n'
        "exit 0\n"
        "\n"
        f'echo "{USER_SENTINEL}" >> "$(git rev-parse --show-toplevel)/.user_hook_log"\n'
        "exit 0\n"
    )
    lp = hooks_dir / "pre-commit"
    lp.write_text(legacy)
    os.chmod(str(lp), 0o755)

    engine._vault_install_git_hooks(tmp_path)
    upgraded = lp.read_text()

    assert "# tess-vault-guard v2" in upgraded
    assert "# tess-vault-guard end" in upgraded
    assert USER_SENTINEL in upgraded
    assert upgraded.index("# tess-vault-guard end") < upgraded.index(USER_SENTINEL)
    assert subprocess.run(["bash", "-n", str(lp)]).returncode == 0

    # The recovered operator hook now actually runs on a clean commit.
    (tmp_path / "main.py").write_text("ok\n")
    _git(tmp_path, "add", "main.py")
    r = _git(tmp_path, "commit", "-m", "clean", check=False)
    assert r.returncode == 0, f"clean commit blocked after re-splice: {r.stderr}"
    log = tmp_path / ".user_hook_log"
    assert log.exists() and USER_SENTINEL in log.read_text(), "operator hook still neutered after upgrade"


# ---------------------------------------------------------------------------
# Reid HIGH — pre-push stdin tee.
#
# git delivers the pushed ref ranges on STDIN. The vault guard's `while read`
# loop consumes ALL of it; without a tee, a coexisting operator pre-push hook
# spliced below would see EOF instead of the ref lines. The splice must capture
# stdin once and re-feed the SAME bytes to the operator's hook on a clean pass —
# while still BLOCKING when a secret is in the pushed range.
# ---------------------------------------------------------------------------

# A real git pre-push stdin line: <local-ref> <local-sha> <remote-ref> <remote-sha>


def _write_user_prepush_echo_hook(root):
    """An operator pre-push hook that records EXACTLY what it received on stdin."""
    hp = root / ".git" / "hooks" / "pre-push"
    hp.parent.mkdir(parents=True, exist_ok=True)
    # `cat` the entire stdin into a log file so the test can assert the operator
    # hook saw the ref line the guard had already consumed.
    hp.write_text(
        "#!/usr/bin/env bash\n"
        "# operator's own pre-existing pre-push hook (e.g. a policy check)\n"
        'cat >> "$(git rev-parse --show-toplevel)/.user_prepush_stdin"\n'
        f'echo "{USER_SENTINEL}" >> "$(git rev-parse --show-toplevel)/.user_hook_log"\n'
        "exit 0\n"
    )
    os.chmod(str(hp), 0o755)
    return hp


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_prepush_splice_feeds_user_hook_stdin(engine, tmp_path):
    """
    After a CLEAN guard pass, the spliced operator pre-push hook must still
    receive the ref line git put on stdin (not be starved by the guard's read),
    and the guard must still BLOCK when a secret is in the pushed range.
    """
    _init_repo(tmp_path)
    _write_user_prepush_echo_hook(tmp_path)

    engine._vault_install_git_hooks(tmp_path)

    hook_path = tmp_path / ".git" / "hooks" / "pre-push"
    hook_text = hook_path.read_text()
    # Structural: stdin captured once, teed to guard and to the operator hook.
    assert "# tess-vault-guard v2" in hook_text
    assert 'GUARD_STDIN="$(cat; printf x)"' in hook_text
    assert 'printf \'%s\' "$GUARD_STDIN" | (' in hook_text       # fed to the guard
    assert 'printf \'%s\' "$GUARD_STDIN" | {' in hook_text       # fed to the operator hook
    assert "# tess-vault-guard end" in hook_text
    assert USER_SENTINEL in hook_text
    assert hook_text.index("# tess-vault-guard end") < hook_text.index(USER_SENTINEL)
    assert subprocess.run(["bash", "-n", str(hook_path)]).returncode == 0

    # Build a real, clean (no-secret) pushed range: two commits, a benign file.
    (tmp_path / "a.txt").write_text("hello\n")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "c1")
    base_sha = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    (tmp_path / "b.txt").write_text("world\n")
    _git(tmp_path, "add", "b.txt")
    _git(tmp_path, "commit", "-m", "c2")
    head_sha = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    # The stdin line git would feed an UPDATE of an existing remote ref
    # (remote_sha = base_sha → guard diffs base..head, no all-zeros new-branch path).
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
    assert r.returncode == 0, f"clean push blocked: {r.stderr}"

    # The operator hook ran AND saw the exact ref line on stdin (not starved).
    log = tmp_path / ".user_hook_log"
    assert log.exists() and USER_SENTINEL in log.read_text(), "operator pre-push hook was starved/neutered"
    seen = (tmp_path / ".user_prepush_stdin").read_text()
    assert head_sha in seen and base_sha in seen, (
        f"operator hook did not receive the ref line on stdin; got: {seen!r}"
    )

    # Now prove the guard STILL BLOCKS a secret in the pushed range, and that the
    # operator hook does NOT run when the push is blocked.
    (tmp_path / ".user_hook_log").unlink(missing_ok=True)
    (tmp_path / ".user_prepush_stdin").unlink(missing_ok=True)
    (tmp_path / "leak.age").write_text("ciphertext\n")
    _git(tmp_path, "add", "-f", "leak.age")
    # --no-verify: bypass the (also-installed) pre-COMMIT guard — this test
    # isolates the pre-PUSH path, which must catch the secret in the range.
    _git(tmp_path, "commit", "--no-verify", "-m", "add-secret")
    leak_sha = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    secret_ref_line = f"refs/heads/main {leak_sha} refs/heads/main {head_sha}\n"

    r2 = subprocess.run(
        ["bash", str(hook_path), "origin", "git@example.com:repo.git"],
        cwd=str(tmp_path), input=secret_ref_line, capture_output=True, text=True, env=env,
    )
    assert r2.returncode != 0, "guard failed to block a .age file in the pushed range"
    assert "TESS VAULT GUARD" in (r2.stderr + r2.stdout)
    assert not (tmp_path / ".user_hook_log").exists(), "operator hook ran despite a blocked push"
