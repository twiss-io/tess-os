"""v1.0.0 final Claude security review (Cyra): the launcher and hook config.

A-1 (High): the enforcement anchor is checked INSIDE `.claude/hooks/run-pinned.py`,
    which lives in the working tree, and the hook commands that start it live in
    `.claude/settings*.json` / `.codex/**`. A route that replaces them skips the
    anchor, so the gate must refuse the route itself: `git pull` in every form
    (the hook never fetches: a pull from `.` is judged exactly, a pull from a
    remote asks in Claude / is denied in Codex), and merge / cherry-pick / am
    of a commit or patch that changes the launcher or the hook configuration.
A-2 (Medium): `tessctl anchor accept|init` and the pty wrappers are judged on
    the parsed words of every sub-command, so quoting and escaping do not hide them.
A-3 (Low): run-pinned.py accepts tessctl's `path-<sha256>` project ids.
A-4 (Low): `tessctl restore` writes git hooks only into the project's own .git/hooks.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
import sys

import pytest

from fixtures.anchor import REPO, real_anchor  # noqa: F401 — fixture
from test_codex_gate import HAS_GIT, _git, proj  # noqa: F401 — fixture
from test_v1_r3_gate_rollback import ID, _claude, _codex, _commit, _fill, repo  # noqa: F401

pytestmark = pytest.mark.skipif(not HAS_GIT, reason="needs git")

STUB = "import sys\nsys.stdin.read()\nsys.exit(0)\n"


@pytest.fixture
def pulls(repo):  # noqa: F811
    """repo + branches that change only the launcher / a settings file / .codex."""
    root, old = repo
    for branch, rel, body in (("launcher", ".claude/hooks/run-pinned.py", STUB),
                              ("localsettings", ".claude/settings.local.json",
                               '{"disableAllHooks": true}\n'),
                              ("codexcfg", ".codex/hooks.json", "{}\n")):
        _git(root, "checkout", "-q", "-b", branch, "main")
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body)
        _git(root, "add", "-f", rel)  # a global excludes file may ignore settings.local.json
        _commit(root, f"change {rel}")
    _git(root, "checkout", "-q", "main")
    return root, old


def _upstream(root, branch, rebase=None):
    _git(root, "config", "branch.main.remote", ".")
    _git(root, "config", "branch.main.merge", f"refs/heads/{branch}")
    if rebase is not None:
        _git(root, "config", "pull.rebase", rebase)


PULL_ASK = [
    "git pull . evil",
    "git pull . launcher",
    "git pull --rebase . launcher",
    "git pull --rebase=merges . launcher",
    "git pull -r . launcher",
    "git pull --ff-only . launcher",
    "git pull --no-rebase . launcher",
    "git pull -q --no-edit . localsettings",
    "git pull . codexcfg",
    "git pull . feature launcher",
    "git pull . +launcher:refs/heads/tmp",
    "git pull origin main",                   # a remote: known only after the fetch
    "git pull --rebase origin",
    "git pull --all",
    "git pull",                               # no upstream configured
    "git pull . does-not-exist",
    "git -C . pull . launcher",
    "cd src && git pull .. launcher",         # `..` is another repository path
]

MERGE_LIKE_ASK = [
    "git merge launcher",
    "git merge --ff-only localsettings",
    "git merge codexcfg",
    "git cherry-pick launcher",
    "git cherry-pick main..localsettings",
    "git rebase launcher",
]


@pytest.mark.parametrize("cmd", PULL_ASK + MERGE_LIKE_ASK)
def test_pull_and_merges_that_change_the_launcher_or_hook_config_need_the_operator(pulls, cmd):
    root, old = pulls
    cmd = _fill(root, old, cmd)
    assert _claude(root, cmd) == "ask", cmd
    assert _codex(root, cmd) == "deny", cmd


@pytest.mark.parametrize("branch,rebase", [("launcher", None), ("launcher", "true"),
                                           ("localsettings", None), ("evil", "merges")])
def test_plain_git_pull_is_judged_against_the_upstream_it_merges(pulls, branch, rebase):
    root, _ = pulls
    _upstream(root, branch, rebase)
    for cmd in ("git pull", "git pull --ff-only", "git pull --rebase", "git pull -q"):
        assert _claude(root, cmd) == "ask", (branch, cmd)
        assert _codex(root, cmd) == "deny", (branch, cmd)


@pytest.mark.parametrize("cmd", ["git pull . feature", "git pull --rebase . feature",
                                 "git pull --ff-only . feature", "git pull -q . feature"])
def test_a_pull_from_this_repository_that_changes_only_normal_files_is_allowed(pulls, cmd):
    root, _ = pulls
    assert _claude(root, cmd) is None, cmd
    assert _codex(root, cmd) is None, cmd


def test_plain_git_pull_of_a_normal_upstream_is_allowed(pulls):
    root, _ = pulls
    _upstream(root, "feature")
    for cmd in ("git pull", "git pull --rebase", "git pull --ff-only"):
        assert _claude(root, cmd) is None, cmd
        assert _codex(root, cmd) is None, cmd


def test_network_pull_names_the_checked_path(pulls):
    root, _ = pulls
    from test_codex_gate import _bash
    d = _bash(root, "git pull origin main")
    assert d[0] == "deny" and "git fetch" in d[1] and "git merge" in d[1], d


def test_patches_and_writes_to_the_hook_config_are_denied(pulls, tmp_path):
    root, _ = pulls
    for rel in (".claude/settings.local.json", ".codex/agents/x.toml", ".claude/hooks/run-pinned.py"):
        patch = tmp_path / (rel.replace("/", "_") + ".patch")
        patch.write_text(f"From 0000 Mon Sep 17 00:00:00 2001\nSubject: x\n\n---\n"
                         f"diff --git a/{rel} b/{rel}\n--- a/{rel}\n+++ b/{rel}\n@@ -0,0 +1 @@\n+x\n")
        for cmd in (f"git am {patch}", f"git apply {patch}"):
            assert _claude(root, cmd) == "deny", cmd
            assert _codex(root, cmd) == "deny", cmd
    for cmd in ("rm .claude/settings.local.json", "echo '{}' > .claude/settings.local.json",
                "mkdir -p .codex/agents && echo x > .codex/agents/a.toml", "rm -rf .codex",
                "cp /tmp/x .claude/settings.local.json"):
        assert _claude(root, cmd) == "deny", cmd
        assert _codex(root, cmd) == "deny", cmd


# --------------------------------------------------------------------------- A-2
OPERATOR_DENY = [
    "./tess''ctl anchor ac''cept",
    "./tessctl \"anchor\" \"accept\"",
    "./tessctl anchor \\a\\c\\c\\e\\p\\t",
    "./tessctl an\\chor init",
    "'./tessctl' 'anchor' 'init'",
    "python3 -I -B .tess/bin/tessctl anchor accept",
    "python3 -I -B '.tess/bin/tess''ctl' anchor 'acc'ept",
    "\"$PWD/.tess/bin/tessctl\" anchor accept",
    "env TESS_ROOT=. ./tessctl --quiet anchor accept",
    "timeout 30 ./tessctl anchor init",
    "sh -c \"./tess''ctl anchor ac''cept\"",
    "bash -lc './tessctl anchor accept'",
    "./TessCtl anchor Accept",
    "un''buffer ./tessctl update",
    "scr\\ipt -q /dev/null ./tessctl update",
    "'expect' -c 'spawn ./tessctl update'",
    "socat - EXEC:./tessctl\\ update,pty",
    "printf 'accept %s\\n' v1.0.1 | ./tessctl update",
    "yes | ./tessctl update",
    "./tessctl update < answers.txt",
    "./tessctl update <<< 'accept v1.0.1'",
    "./tessctl approve 0<answers.txt",
    "tmux send-keys -t main 'accept v1.0.1' Enter",
    "screen -S s -X stuff 'accept safety changes\\n'",
    "python3 -c \"import pty; pty.spawn(['./tess'+'ctl', 'update'])\"",
    "python3 -c 'import os; os.openpty()'",
    "python3 - <<'EOF'\nimport pty\npty.spawn(['./tessctl', 'update'])\nEOF",
    "./tessctl anchor accept'",               # unbalanced quote: fail-closed path
]

OPERATOR_ALLOW = [
    "./tessctl anchor status",
    "python3 -I -B .tess/bin/tessctl anchor status",
    "./tessctl doctor",
    "./tessctl update --check",
    "./tessctl lock --check",
    "grep -n accept .tess/bin/tessctl",
    "git log --grep anchor",
    "python3 -c 'print(1)'",
]


@pytest.mark.parametrize("cmd", OPERATOR_DENY)
def test_quoting_does_not_hide_operator_only_commands(pulls, cmd):
    root, _ = pulls
    assert _claude(root, cmd) == "deny", cmd
    assert _codex(root, cmd) == "deny", cmd


def test_unfed_update_is_the_operators_in_codex(pulls):
    """Integration pass 3: Claude Code lets the operator answer an unfed
    `tessctl update`; Codex denies it (write_stdin can type the answer)."""
    root, _ = pulls
    assert _claude(root, "./tessctl update") is None
    assert _codex(root, "./tessctl update") == "deny"


@pytest.mark.parametrize("cmd", OPERATOR_ALLOW)
def test_normal_tessctl_use_is_allowed(pulls, cmd):
    root, _ = pulls
    assert _claude(root, cmd) is None, cmd
    assert _codex(root, cmd) is None, cmd


# --------------------------------------------------------------------------- A-3
def _load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    sys.dont_write_bytecode = True
    loader.exec_module(mod)
    return mod


def test_launcher_and_engine_agree_on_project_ids():
    rp = _load(REPO / ".claude/hooks/run-pinned.py", "rp_final_ids")
    eng = _load(REPO / ".tess/bin/tessctl", "eng_final_ids")
    assert rp._ANCHOR_ID.pattern == eng._ANCHOR_ID.pattern
    for pid in ("a" * 40, "b" * 64, "path-" + "c" * 64):
        assert rp._ANCHOR_ID.fullmatch(pid) and eng._ANCHOR_ID.fullmatch(pid), pid
    for pid in ("path-" + "c" * 40, "../x", "a" * 39, "path-" + "C" * 64):
        assert not rp._ANCHOR_ID.fullmatch(pid) and not eng._ANCHOR_ID.fullmatch(pid), pid


def test_anchored_repository_without_a_commit_keeps_working(proj, real_anchor):  # noqa: F811
    """tessctl anchors a repository with no commit as `path-<sha256>`; the
    launcher used to read that as a lost anchor and stop every call for good."""
    import shutil
    shutil.rmtree(proj / ".git")
    _git(proj.parent, "init", "-b", "main", "-q", str(proj))
    where = real_anchor(proj)
    assert where.parent.name.startswith("path-"), where
    assert _claude(proj, "ls") is None
    assert _claude(proj, "rm .claude/hooks/tess-gate.py") == "deny"  # the REAL gate decides
    (proj / ".claude/hooks/tess-gate.py").write_text(STUB)
    r = subprocess.run(["sh", "-c", __import__("test_v1_claude_gate_parity")._gate_hook()["command"]],
                       input='{"session_id":"s","hook_event_name":"PreToolUse","cwd":"%s",'
                             '"permission_mode":"default","tool_name":"Bash",'
                             '"tool_input":{"command":"ls"}}' % proj,
                       capture_output=True, text=True, cwd=str(proj),
                       env={**os.environ, "CLAUDE_PROJECT_DIR": str(proj),
                            "TESS_GATE_LOG": os.devnull})
    assert r.returncode == 2 and "safety files have changed" in r.stderr, r.stderr


# --------------------------------------------------------------------------- A-4
def _hooks_dir(root):
    code = ("import sys, importlib.machinery as m, importlib.util as u\n"
            "from pathlib import Path\n"
            "l = m.SourceFileLoader('e', sys.argv[1]); e = u.module_from_spec(u.spec_from_loader('e', l))\n"
            "l.exec_module(e); print(e._anchor_restore_hooks_dir(Path(sys.argv[2])))\n")
    r = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(REPO / ".tess/bin/tessctl"),
                        str(root)], capture_output=True, text=True,
                       env={**os.environ, "GIT_DIR": "/nonexistent"})
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_restore_writes_git_hooks_only_into_the_projects_own_git_dir(proj, tmp_path):  # noqa: F811
    real = os.path.realpath(str(proj / ".git" / "hooks"))
    assert _hooks_dir(proj) == real  # GIT_DIR in the environment is ignored
    elsewhere = tmp_path / "elsewhere.git"
    os.rename(proj / ".git", elsewhere)
    (proj / ".git").write_text(f"gitdir: {elsewhere}\n")
    assert _hooks_dir(proj) == "None", "a .git file pointer is not followed for writes"
    (proj / ".git").unlink()
    os.symlink(elsewhere, proj / ".git")
    assert _hooks_dir(proj) == "None", "a symlinked .git is refused"
    (proj / ".git").unlink()
    os.rename(elsewhere, proj / ".git")
    hooks = proj / ".git" / "hooks"
    if hooks.exists():
        os.rename(hooks, tmp_path / "hooks-real")
    os.symlink(tmp_path / "hooks-real", hooks)
    assert _hooks_dir(proj) == "None", "a symlinked hooks folder is refused"


def test_restore_refuses_a_git_hook_behind_a_gitdir_pointer(proj, real_anchor, tmp_path):  # noqa: F811
    hook = proj / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\n# tess-gate\nexit 0\n")
    real_anchor(proj)
    elsewhere = tmp_path / "elsewhere.git"
    os.rename(proj / ".git", elsewhere)
    (proj / ".git").write_text(f"gitdir: {elsewhere}\n")
    (elsewhere / "hooks" / "pre-commit").unlink()
    r = subprocess.run([sys.executable, "-I", "-B", str(proj / ".tess/bin/tessctl"), "restore"],
                       cwd=str(proj), capture_output=True, text=True,
                       env={**os.environ, "TESS_ROOT": str(proj)})
    assert "git-hooks/pre-commit" in r.stdout + r.stderr, r.stdout + r.stderr
    assert "will not write there" in r.stdout + r.stderr, r.stdout + r.stderr
    assert not (elsewhere / "hooks" / "pre-commit").exists()
