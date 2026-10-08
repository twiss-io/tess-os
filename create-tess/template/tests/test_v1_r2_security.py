"""v1.0 security review, round 2 (Cyra): git output-file writes, remote-ref
trust, flag abbreviations, key reads, log redaction, permission modes and the
vault hooks' name listing.

Threat model: a prompt-injected or overeager agent with a shell running as the
operator's own user, planted documents, a malicious upstream PR. Every gate
case runs the REAL rendered hook command in BOTH runtimes:

  * Codex: `.codex/config.toml`'s PreToolUse command, payload with `turn_id`
    (Codex cannot ask, so an ask must leave as a deny);
  * Claude Code: `.claude/settings.json`'s tess-gate command, payload with a
    `permission_mode` (an ask stays an ask in an interactive mode).

On release/v1.0 at 8b2987d 114 of these cases failed (allowed, or leaked);
the rest are allow-direction regression guards and rules that already held
(exact `--no-verify` on merge/cherry-pick, `git remote set-url`, the known
permission modes), kept so the fix cannot regress them.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_codex_gate import HAS_GIT, HOOK_CMD, _decision, _git, proj  # noqa: F401  (fixture)

REPO = Path(__file__).resolve().parent.parent
RUNTIMES = ("claude", "codex")


def _claude_cmd() -> str:
    data = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    for entry in data["hooks"]["PreToolUse"]:
        for hook in entry["hooks"]:
            if "tess-gate.py" in hook["command"]:
                return hook["command"]
    raise AssertionError("no tess-gate.py hook in .claude/settings.json")


CLAUDE_CMD = _claude_cmd()


def run(root, runtime, tool, tin, mode="default", path=None):
    payload = {"session_id": "s", "hook_event_name": "PreToolUse", "cwd": str(root),
               "tool_name": tool, "tool_input": tin}
    if runtime == "codex":
        payload["turn_id"] = "t1"
    else:
        payload["permission_mode"] = mode
    env = {"HOME": str(root / "home"), "PATH": path or os.environ["PATH"],
           "TESS_GATE_LOG": str(root / "home" / "gate.log"), "CLAUDE_PROJECT_DIR": str(root)}
    r = subprocess.run(["sh", "-c", HOOK_CMD if runtime == "codex" else CLAUDE_CMD],
                       input=json.dumps(payload), capture_output=True, text=True,
                       cwd=str(root), env=env, timeout=120)
    got = _decision(r)
    return got[0] if got else None


def bash(root, runtime, cmd, **kw):
    return run(root, runtime, "Bash", {"command": cmd}, **kw)


def asked(root, runtime, cmd):
    """An approval case: Claude (default mode) asks, Codex denies."""
    return bash(root, runtime, cmd) == ("ask" if runtime == "claude" else "deny")


def _engine():
    loader = importlib.machinery.SourceFileLoader("tessctl_r2", str(REPO / ".tess/bin/tessctl"))
    spec = importlib.util.spec_from_loader("tessctl_r2", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    loader.exec_module(mod)
    return mod


def _commit(root, msg, *paths):
    _git(root, "add", "-A", *paths)
    _git(root, "-c", "user.email=t@tess.test", "-c", "user.name=T", "-c", "commit.gpgsign=false",
         "commit", "-q", "--no-verify", "-m", msg)


# ------------------------------------------------------------------ H-A: git writes a file

@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("cmd", [
    "git log -1 --format='#!/bin/sh%nexit 0' --output=.git/hooks/pre-push",
    "git log -1 --output .claude/settings.json",
    "git log -1 --outp=.tess/gate/policy-approvals/a.json",
    "git show HEAD --ou=notes.txt",
    "git -C . --no-pager diff HEAD --output=x.txt",
    "git format-patch -o .claude/hooks HEAD~0",
    "git format-patch -o.claude HEAD",
    "git format-patch --output-directory out HEAD",
    "git whatchanged --output=x",
    "git archive -o x.tar HEAD",
    "git diff --no-index /etc/hosts src/app.py",
    "git diff --no-ind a b",
    "git diff --ext-diff",
    "git log -p --textconv",
    "git grep -Ocat print",
    "git -c core.pager='cp /tmp/x .git/hooks/pre-push' log",
    "GIT_EXTERNAL_DIFF='rm -rf .claude/hooks' git diff",
    "git config diff.evil.textconv 'sh -c id'",
    "git config core.pager 'tee .claude/settings.json'",
])
def test_git_output_file_and_helper_options_are_denied(proj, runtime, cmd):
    assert bash(proj, runtime, cmd) == "deny", (runtime, cmd)


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("cmd", [
    "git log --oneline -5",
    "git log -Sfoo --stat",
    "git log -p --output-indicator-new=+",
    "git diff --stat",
    "git diff --text HEAD",
    "git show HEAD --stat",
    "git -c core.pager=cat log -1",
    "git config core.pager 'less -R'",
    "git log --no-ext-diff --no-textconv -1",
])
def test_ordinary_git_reads_stay_allowed(proj, runtime, cmd):
    assert bash(proj, runtime, cmd) is None, (runtime, cmd)


def test_git_diff_log_show_are_no_longer_pre_approved():
    for rel in (".claude/settings.json", ".tess/core/settings-core.json"):
        perms = json.loads((REPO / rel).read_text())["permissions"]
        for sub in ("diff", "log", "show"):
            assert not any(a.startswith(f"Bash(git {sub}") for a in perms["allow"]), (rel, sub)
        assert "Bash(git log *--output*)" in perms["deny"]
        assert "Read(~/.config/tess/**)" in perms["deny"]


# ------------------------------------------------------------------ H-B: remote-ref trust

@pytest.fixture
def leaked(proj):
    """brain/ data committed and then removed: absent at the tip, still in history."""
    (proj / "brain" / "decisions").mkdir(parents=True)
    (proj / "brain" / "decisions" / "D-1.md").write_text("client pricing\n")
    _commit(proj, "data")
    _git(proj, "rm", "-q", "brain/decisions/D-1.md")
    _commit(proj, "scrub")
    return proj


@pytest.mark.skipif(not HAS_GIT, reason="git required")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_forged_tracking_ref_no_longer_hides_published_history(leaked, runtime):
    _git(leaked, "remote", "add", "origin", "https://tess-review.invalid/acme/brain.git")
    _git(leaked, "update-ref", "refs/remotes/origin/zz", "HEAD~1")  # the forgery
    assert bash(leaked, runtime, "git push origin HEAD") == "deny"


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_publish_remote_trusts_only_the_push_negotiation(leaked):
    eng = _engine()
    head = _git(leaked, "rev-parse", "HEAD")
    stdin = f"refs/heads/main {head} refs/heads/main {'0' * 40}\n"
    _git(leaked, "update-ref", "refs/remotes/origin/zz", "HEAD~1")
    # tracking refs are ignored: the leaked history is still found
    assert eng._publish_remote_data_paths(leaked, stdin, "origin") == ["brain/decisions/D-1.md"]
    # the push's own remote_sha (git's receive-pack negotiation) is honoured
    prev = _git(leaked, "rev-parse", "HEAD~1")
    assert eng._publish_remote_data_paths(
        leaked, f"refs/heads/main {head} refs/heads/main {prev}\n") == []
    # round 3, N2: a separate destination advertisement can no longer waive it
    # (tests/test_v1_r3_remote_trust.py drives the lying-server scenario)
    assert not hasattr(eng, "_publish_remote_held")


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("cmd", [
    "git config remote.origin.url https://github.com/x/public.git",
    "git config remote.origin.pushurl https://github.com/x/public.git",
    "git config --add tess.privateRemote https://github.com/x/public.git",
    "git config url.https://github.com/x/pub.insteadOf https://github.com/x/priv",
    "git update-ref refs/remotes/origin/zz HEAD",
    "git fetch . HEAD:refs/remotes/origin/zz",
    "git remote set-url origin https://github.com/x/public.git",
    "git -c remote.origin.pushurl=https://github.com/x/public.git status",
    "git push --delete origin old",
    "git push origin :old",
])
def test_remote_trust_changes_need_the_operator(proj, runtime, cmd):
    assert asked(proj, runtime, cmd), (runtime, cmd)


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("cmd", ["git config --get remote.origin.url", "git fetch origin",
                                 "git config --get-all tess.privateRemote"])
def test_remote_reads_stay_allowed(proj, runtime, cmd):
    assert bash(proj, runtime, cmd) is None, (runtime, cmd)


# ------------------------------------------------------------------ M-1: key directory

@pytest.fixture
def keyed(proj):
    kdir = proj / "home" / ".config" / "tess" / "brain"
    kdir.mkdir(parents=True)
    (kdir / "key").write_text("k" * 64)
    return proj


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("cmd", [
    "cat ~/.config/tess/brain/key",
    "head -c 64 $HOME/.config/tess/brain/key",
    "cp ${HOME}/.config/tess/brain/key /tmp/k",
    "less ~/.config/tess/brain/key",
    "python3 -c \"import os;print(open(os.path.expanduser('~/.config/tess/brain/key')).read())\"",
    "cd ~/.config && cat tess/brain/key",
    "grep -r . ~/.config",
    "ln -s ~/.config/tess k",
    "TESS_BRAIN_PROVENANCE_DIR=/tmp/x python3 scripts/brain/tessbrain.py status",
])
def test_key_directory_reads_are_denied_in_the_shell(keyed, runtime, cmd):
    assert bash(keyed, runtime, cmd) == "deny", (runtime, cmd)


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_key_directory_via_read_grep_edit_and_mcp_is_denied(keyed, runtime):
    key = str(keyed / "home" / ".config" / "tess" / "brain" / "key")
    cfg = str(keyed / "home" / ".config")
    assert run(keyed, runtime, "Read", {"file_path": key}) == "deny"
    assert run(keyed, runtime, "Grep", {"pattern": "x", "path": cfg}) == "deny"
    assert run(keyed, runtime, "Write", {"file_path": key, "content": "x"}) == "deny"
    assert run(keyed, runtime, "mcp__fs__read_file", {"path": key}) == "deny"


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_ordinary_reads_stay_allowed(keyed, runtime):
    assert bash(keyed, runtime, "cat src/app.py") is None
    assert bash(keyed, runtime, "ls ~") is None
    assert run(keyed, runtime, "Read", {"file_path": str(keyed / "src" / "app.py")}) is None
    assert run(keyed, runtime, "Grep", {"pattern": "x", "path": str(keyed / "src")}) is None


# ------------------------------------------------------------------ M-2: abbreviations

@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("cmd", [
    "git commit --no-veri -m x",
    "git commit --no-verif -m x",
    "git commit -m x --no-ver",
    "git merge --no-verify topic",
    "git rebase --no-verif main",
    "git am --no-v x.patch",
    "git cherry-pick --no-verify HEAD",
    "git revert --no-veri HEAD",
])
def test_no_verify_abbreviations_are_denied(proj, runtime, cmd):
    assert bash(proj, runtime, cmd) == "deny", (runtime, cmd)


@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("cmd", [
    "git push --forc origin HEAD",
    "git push --force-with origin HEAD",
    "git push --force-if origin HEAD",
    "git push --mirr origin",
    "git push --del origin old",
])
def test_force_mirror_delete_abbreviations_need_the_operator(proj, runtime, cmd):
    assert asked(proj, runtime, cmd), (runtime, cmd)


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not installed")
@pytest.mark.parametrize("cmd,want", [
    ("git commit --no-veri -m x", "forbidden"),
    ("git push --forc origin main", "prompt"),
    ("git log --output out.txt", "forbidden"),
    ("git update-ref refs/remotes/origin/x HEAD", "prompt"),
    ("git log --oneline", None),
    # v1.0.0 final (#224): git routes that can put other safety files in place
    ("git replace HEAD evil", "forbidden"),
    ("git replace --graft HEAD", "forbidden"),
    ("git sparse-checkout set --no-cone x", "forbidden"),
    ("git sparse-checkout add x", "forbidden"),
    ("git sparse-checkout init", "forbidden"),
    ("git sparse-checkout reapply", "forbidden"),
    ("git sparse-checkout disable", "forbidden"),
    ("git sparse-checkout list", None),
    ("git fetch --update-head-ok . +evil:main", "forbidden"),
    ("git fetch --update-he . evil:main", "forbidden"),
    ("git fetch -u . +evil:main", "forbidden"),
    ("git fetch origin", None),
    ("git bisect start evil main", "prompt"),
    ("git bisect reset evil", "prompt"),
    ("git bisect log", None),
    ("git rebase --onto evil main", "prompt"),
    ("git rebase main", None),
    ("git rebase --continue", None),
])
def test_codex_prefix_rules_cover_the_abbreviations(cmd, want):
    r = subprocess.run(["codex", "execpolicy", "check", "--rules", str(REPO / ".codex/rules/tess.rules"),
                        "--", *cmd.split()], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout).get("decision") == want, (cmd, r.stdout)


# ------------------------------------------------------------------ M-5: release tooling

def test_release_tooling_is_security_tier_and_code_owned():
    for rel in ("core/policy/policy.yaml", ".tess/core/policy/policy.yaml"):
        text = (REPO / rel).read_text()
        rule = text.split("id: tess-os-security-tier-doctrine", 1)[1].split("\n    - id:", 1)[0]
        assert "- scripts/release/**" in rule and "- .github/CODEOWNERS" in rule, rel
    owners = (REPO / ".github" / "CODEOWNERS").read_text()
    assert "/scripts/release/" in owners and "/.github/CODEOWNERS" in owners
    for rel in ("conductor/release-process.md", ".tess/core/conductor/release-process.md"):
        doc = (REPO / rel).read_text()
        assert 'bash "$SIGNER" v<new-semver> "$M"' in doc
        assert 'git show "$M:scripts/release/sign-release-tag.sh" > "$SIGNER"' in doc
        assert "shasum -a 256" in doc
        assert "\nscripts/release/sign-release-tag.sh v" not in doc  # never from the working tree


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_release_helper_is_a_protected_path(proj, runtime):
    assert bash(proj, runtime, "echo x > scripts/release/sign-release-tag.sh") == "deny"


# ------------------------------------------------------------------ L-b: log redaction

@pytest.mark.parametrize("runtime", RUNTIMES)
def test_decision_log_redacts_whole_pem_blocks_and_key_blobs(proj, runtime):
    import base64
    # Synthetic key material, built at run time so no scanner sees a key here.
    raw = base64.b64encode(b"tess-r2-synthetic-not-a-key+/" * 5).decode()
    body = [raw[:64], raw[64:128]]
    blob = base64.b64encode(b"forged-provenance-key-material-1234567890").decode()
    kind = "RSA " + "PRIVATE KEY"
    pem = f"-----BEGIN {kind}-----\n" + "\n".join(body) + f"\n-----END {kind}-----"
    bash(proj, runtime, f"git commit --no-verify -m 'k {blob}'\nprintf '%s' '{pem}'")
    log = (proj / "home" / "gate.log").read_text()
    assert log.strip(), "the deny was logged"
    for secret in body + [blob, f"BEGIN {kind}", f"END {kind}"]:
        assert secret[:24] not in log, secret


# ------------------------------------------------------------------ L-c: permission modes

@pytest.mark.parametrize("mode,want", [("default", "ask"), ("acceptEdits", "ask"), ("plan", "ask"),
                                       ("auto", "deny"), ("bypassPermissions", "deny"),
                                       ("dontAsk", "deny"), ("", "deny"), ("yolo", "deny")])
def test_ask_only_in_known_interactive_modes(proj, mode, want):
    assert bash(proj, "claude", "git remote add pub https://github.com/a/b.git", mode=mode) == want


# ------------------------------------------------------------------ L-d: vault hooks list with -z

SECRET = "ghp_" + "A1b2C3d4" * 5


@pytest.fixture
def vault_repo(tmp_path):
    root = tmp_path / "vr"
    _git(tmp_path, "init", "-b", "main", "-q", str(root))
    (root / "ok.txt").write_text("fine\n")
    _commit(root, "init")
    _engine()._vault_install_git_hooks(root)
    return root


def _run_git(root, *args):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@tess.test", "-c", "user.name=T",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True)


@pytest.mark.skipif(not HAS_GIT or shutil.which("bash") is None, reason="git and bash required")
def test_pre_commit_scans_a_name_with_a_newline(vault_repo):
    (vault_repo / "evil\nname.txt").write_text(f"token = {SECRET}\n")
    _git(vault_repo, "add", "-A")
    r = _run_git(vault_repo, "commit", "-q", "-m", "x")
    assert r.returncode != 0 and "GITHUB TOKEN" in r.stderr, r.stderr
    (vault_repo / "evil\nname.txt").unlink()
    _git(vault_repo, "add", "-A")


@pytest.mark.skipif(not HAS_GIT or shutil.which("bash") is None, reason="git and bash required")
def test_pre_push_scans_a_name_with_a_newline(vault_repo, tmp_path):
    bare = tmp_path / "vr.git"
    _git(tmp_path, "init", "-b", "main", "-q", "--bare", str(bare))
    (vault_repo / "evil\nname.txt").write_text(f"token = {SECRET}\n")
    _commit(vault_repo, "sneak")  # --no-verify: only the pre-push hook is under test
    r = _run_git(vault_repo, "push", "-q", str(bare), "HEAD:refs/heads/main")
    assert r.returncode != 0 and "GITHUB TOKEN" in r.stderr, r.stderr


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_vault_hooks_list_names_nul_separated_and_fail_closed():
    src = (REPO / ".tess/bin/tessctl").read_text()
    body = src.split("def _vault_install_git_hooks", 1)[1].split("\ndef ", 1)[0]
    assert body.count("--name-only -z") >= 2  # pre-commit and pre-push listings
    assert "read -r -d ''" in body
    assert "|| continue" not in body
    assert "UNREADABLE, so not scanned" in body
