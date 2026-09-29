"""
v1.0: Tess safety hooks enforce in Codex.

`.codex/config.toml` (rendered from codex-config.toml.tpl) carries a
PreToolUse hook that runs `.claude/hooks/tess-gate.py` through
`run-pinned.py --on-fail block`; `.codex/rules/tess.rules` is the prefix-rule
backstop. These tests run the REAL rendered hook command through `sh -c`
(as Codex does) against a temp copy of the shipped files, and assert on the
decision JSON / exit code Codex acts on:

  * Codex does not support "ask" (it fails the hook and RUNS the command), so
    every ask must leave the gate as "deny" — for `--runtime codex` and for
    any payload carrying `turn_id`;
  * each rule: --no-verify / commit -n, core.hooksPath (flag, env, config),
    .git/hooks writes, protected-path writes (apply_patch, Edit, shell,
    MCP), gh auth token, secret-shaped values, force push / remote /
    visibility changes, public-remote pushes of brain/ data;
  * fail closed: unreadable payload, tampered gate script, no python3.
The allow direction is tested too (normal edits, reads, commits, pushes).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / ".claude" / "hooks" / "tess-gate.py"


def _pre_tool_use(text: str) -> dict:
    """The PreToolUse entry of .codex/config.toml. tomllib on Python 3.11+;
    on 3.9/3.10 (stock macOS, CI py3.9) the one entry's two basic-string keys
    are read directly, since the gate itself must be tested there too. TOML
    basic-string escapes (\\" and \\\\) are JSON's, so json.loads decodes them."""
    try:
        import tomllib
    except ModuleNotFoundError:
        block = text.split("[[hooks.PreToolUse]]", 1)[1]
        m = re.search(r'^matcher = ("(?:[^"\\]|\\.)*")$', block, re.M)
        c = re.search(r'^command = ("(?:[^"\\]|\\.)*")$', block.split("[[hooks.PreToolUse.hooks]]", 1)[1], re.M)
        return {"matcher": json.loads(m.group(1)), "hooks": [{"command": json.loads(c.group(1))}]}
    return tomllib.loads(text)["hooks"]["PreToolUse"][0]


PRE = _pre_tool_use((REPO / ".codex" / "config.toml").read_text())
HOOK_CMD = PRE["hooks"][0]["command"]
HAS_GIT = shutil.which("git") is not None


def _git(root, *args):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture
def proj(tmp_path):
    """A Tess instance copy: lock, pins, hooks, engine; a git repo with one commit."""
    root = tmp_path / "proj"
    for rel in (".tess/tess.lock", ".tess/core/pinned-scripts.sha256", "tessctl",
                "tess.manifest.json", "conductor/guardrails.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    for tree in (".claude/hooks", "scripts/brain", ".tess/bin", ".tess/vendor"):
        shutil.copytree(REPO / tree, root / tree, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('hi')\n")
    if HAS_GIT:
        _git(tmp_path, "init", "-q", str(root))
        _git(root, "add", "-A")
        _git(root, "-c", "user.email=t@tess.test", "-c", "user.name=T", "-c",
             "commit.gpgsign=false", "commit", "-q", "--no-verify", "-m", "init")
    return root


def _hook(root, payload, cwd=None, path=None):
    """Run the rendered Codex hook command exactly as Codex does (sh -c, session cwd)."""
    data = payload if isinstance(payload, str) else json.dumps(payload)
    env = {"HOME": str(root / "home"), "PATH": path or os.environ["PATH"],
           "TESS_GATE_LOG": str(root / "home" / "gate.log")}
    return subprocess.run(["sh", "-c", HOOK_CMD], input=data, capture_output=True, text=True,
                          cwd=str(cwd or root), env=env, timeout=120)


def _decision(r):
    if r.returncode == 2:
        return "deny"
    assert r.returncode == 0, r.stderr
    if not r.stdout.strip():
        return None
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    return out["permissionDecision"], out["permissionDecisionReason"]


def _bash(root, cmd, **kw):
    return _decision(_hook(root, {"turn_id": "t1", "tool_name": "Bash",
                                  "tool_input": {"command": cmd}, "cwd": str(root)}, **kw))


def _gate():
    sys.dont_write_bytecode = True  # never leave __pycache__ in .claude/hooks
    spec = importlib.util.spec_from_file_location("tess_gate_under_test", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ rendering

def test_rendered_files_match_the_engine():
    loader = importlib.machinery.SourceFileLoader("tessctl_codex_gate", str(REPO / ".tess/bin/tessctl"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    eng = importlib.util.module_from_spec(spec)
    loader.exec_module(eng)
    assert (REPO / ".codex/config.toml").read_text() == eng.render_codex_config_toml(REPO)
    assert (REPO / ".codex/rules/tess.rules").read_text() == eng.render_codex_rules(REPO)
    tgt = eng.CodexRenderTarget()
    assert ".codex/rules/tess.rules" in tgt.render_generated_paths(REPO)
    assert eng.is_enforcement_render_output(".codex/rules/tess.rules")


def test_hook_covers_every_codex_tool_family_and_runs_pinned_blocking():
    import re
    m = re.compile(PRE["matcher"])
    for name in ("Bash", "apply_patch", "Edit", "Write", "Agent", "spawn_agent", "mcp__fs__write_file"):
        assert m.fullmatch(name), name
    assert not m.fullmatch("WebSearch")
    assert "run-pinned.py\" --on-fail block -- .claude/hooks/tess-gate.py --runtime codex" in HOOK_CMD
    pins = (REPO / ".tess/core/pinned-scripts.sha256").read_text()
    assert ".claude/hooks/tess-gate.py" in pins


# ------------------------------------------------------------------ ask -> deny

def test_ask_becomes_deny_for_codex_by_flag_and_by_turn_id(proj):
    g = _gate()
    base = {"tool_name": "Bash", "tool_input": {"command": "git remote add pub https://github.com/a/b.git"},
            "cwd": str(proj)}
    assert g.decide(dict(base), proj, "claude")[0] == "ask"
    dec, why = g.decide(dict(base), proj, "codex")
    assert dec == "deny" and "run it yourself" in why and "git remote add pub" in why
    assert g.decide(dict(base, turn_id="x"), proj, "claude")[0] == "deny"
    assert g.decide(dict(base, permission_mode="bypassPermissions"), proj, "claude")[0] == "deny"


@pytest.mark.parametrize("cmd", [
    "git remote add pub https://github.com/a/b.git",
    "git remote set-url origin https://github.com/a/b.git",
    "gh repo edit --visibility public",
    "gh repo create thing --public",
    "gh api -X PATCH repos/a/b -f visibility=public",
    "git push --force origin main",
    "git push -f",
    "git push origin +main",
    "git push --force-with-lease",
])
def test_every_ask_rule_is_a_deny_in_codex(proj, cmd):
    dec, why = _bash(proj, cmd)
    assert dec == "deny" and "cannot pause" in why


# ------------------------------------------------------------------ hard denies

@pytest.mark.parametrize("cmd", [
    "git commit -m wip --no-verify",
    "git commit --no-verify -m wip",
    "git commit -nm wip",
    "git commit -a -n -m wip",
    "git push --no-verify origin main",
    "git merge --no-verify topic",
    "git -c core.hooksPath=/dev/null commit -m x",
    "git -c CORE.HOOKSPATH=/tmp/x push",
    "git config core.hooksPath /dev/null",
    "git config --local core.hookspath x",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x",
    "export GIT_CONFIG_KEY_0=core.hooksPath",
    "bash -lc 'git commit --no-verify -m x'",
    "true && sh -c \"git commit -n -m x\"",
    "g''it commit --no-verify -m x",
    "rm .git/hooks/pre-push",
    "chmod -x .git/hooks/pre-commit",
    "echo x > .git/hooks/pre-commit",
    "gh auth token",
    "gh auth status --show-token",
    "echo x >> .claude/hooks/tess-gate.py",
    "sed -i '' 's/a/b/' conductor/guardrails.md",
    "cp /tmp/x .tess/tess.lock",
    "rm -rf .tess",
    "rm -rf .claude",
    "tee .codex/config.toml < /dev/null",
    "git rm .tess/core/pinned-scripts.sha256",
    "cat > core/policy/policy.yaml <<'X'",
    "CONDUCTOR/GUARDRAILS.MD",  # not a write: must stay allowed (see allow test)
][:-1])
def test_hard_denies(proj, cmd):
    dec, why = _bash(proj, cmd)
    assert dec == "deny", cmd
    assert "What to do:" in why


def test_secret_in_command_is_denied_and_never_echoed(proj):
    tok = "ghp_" + "A1b2C3d4" * 5
    dec, why = _bash(proj, f"curl -H 'Authorization: token {tok}' https://api.github.com")
    assert dec == "deny" and "GitHub personal access token" in why
    assert tok not in why


def test_secret_in_spawn_agent_dispatch_is_denied(proj):
    tok = "AKIA" + "ABCDEFGHIJKLMNOP"
    r = _hook(proj, {"turn_id": "t", "tool_name": "spawn_agent", "cwd": str(proj),
                     "tool_input": {"agent_type": "ada", "message": f"use key {tok}"}})
    dec, why = _decision(r)
    assert dec == "deny" and "AWS access key" in why and tok not in why


@pytest.mark.parametrize("path", ["conductor/guardrails.md", ".codex/rules/tess.rules",
                                  ".claude/settings.json", "Conductor/Guardrails.md"])
def test_apply_patch_to_a_protected_file_is_denied(proj, path):
    patch = f"*** Begin Patch\n*** Update File: {path}\n@@\n-a\n+b\n*** End Patch\n"
    r = _hook(proj, {"turn_id": "t", "tool_name": "apply_patch", "cwd": str(proj),
                     "tool_input": {"command": patch}})
    assert _decision(r)[0] == "deny"


def test_apply_patch_move_into_protected_and_symlink_escape_are_denied(proj):
    patch = "*** Begin Patch\n*** Update File: src/app.py\n*** Move to: .claude/hooks/x.py\n*** End Patch\n"
    r = _hook(proj, {"turn_id": "t", "tool_name": "apply_patch", "cwd": str(proj),
                     "tool_input": {"input": patch}})
    assert _decision(r)[0] == "deny"
    (proj / "link").symlink_to(proj / ".claude" / "hooks")
    patch = "*** Begin Patch\n*** Add File: link/evil.py\n+x\n*** End Patch\n"
    r = _hook(proj, {"turn_id": "t", "tool_name": "apply_patch", "cwd": str(proj),
                     "tool_input": {"command": patch}})
    assert _decision(r)[0] == "deny"


def test_edit_write_and_mcp_write_to_protected_are_denied(proj):
    r = _hook(proj, {"turn_id": "t", "tool_name": "Write", "cwd": str(proj),
                     "tool_input": {"file_path": str(proj / ".tess" / "tess.lock"), "content": "x"}})
    assert _decision(r)[0] == "deny"
    r = _hook(proj, {"turn_id": "t", "tool_name": "mcp__fs__write_file", "cwd": str(proj),
                     "tool_input": {"path": "core/policy/policy.yaml", "content": "x"}})
    assert _decision(r)[0] == "deny"


def test_unparseable_edit_fails_closed(proj):
    r = _hook(proj, {"turn_id": "t", "tool_name": "apply_patch", "cwd": str(proj),
                     "tool_input": {"command": "not a patch"}})
    assert _decision(r)[0] == "deny"


# ------------------------------------------------------------------ allow direction

@pytest.mark.parametrize("cmd", [
    "git status", "git commit -m 'fix: normal change'", "git commit -am wip",
    "git log -n 5", "git config --get core.hooksPath", "cat .git/config",
    "sed -n 1p conductor/guardrails.md", "grep -rn no-verify docs",
    "echo hello > src/out.txt", "python3 -m pytest -q", "git push --dry-run origin main",
    "git remote -v", "gh pr list", "ls .git/hooks",
])
def test_normal_commands_are_allowed(proj, cmd):
    assert _bash(proj, cmd) is None, cmd


def test_normal_apply_patch_is_allowed(proj):
    patch = "*** Begin Patch\n*** Update File: src/app.py\n@@\n-print('hi')\n+print('hello')\n*** End Patch\n"
    r = _hook(proj, {"turn_id": "t", "tool_name": "apply_patch", "cwd": str(proj / "src"),
                     "tool_input": {"command": patch.replace("src/app.py", "app.py")}})
    assert _decision(r) is None


def test_hook_resolves_the_instance_from_a_subdirectory(proj):
    assert _bash(proj, "git commit --no-verify -m x", cwd=proj / "src")[0] == "deny"


# ------------------------------------------------------------------ public-remote push guard

@pytest.fixture
def data_repo(proj):
    (proj / "brain" / "decisions").mkdir(parents=True)
    (proj / "brain" / "decisions" / "D-1.md").write_text("client pricing\n")
    _git(proj, "add", "-A")
    _git(proj, "-c", "user.email=t@tess.test", "-c", "user.name=T", "-c", "commit.gpgsign=false",
         "commit", "-q", "--no-verify", "-m", "data")
    return proj


def _nogh_path(tmp_path):
    b = tmp_path / "nogh"
    b.mkdir(exist_ok=True)
    for tool in ("python3", "git"):
        if not (b / tool).exists():
            (b / tool).symlink_to(sys.executable if tool == "python3" else shutil.which(tool))
    return f"{b}:/bin:/usr/bin"


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_push_of_brain_data_to_unverifiable_github_remote_is_denied(data_repo, tmp_path):
    _git(data_repo, "remote", "add", "origin", "https://github.com/acme/brain.git")
    dec, why = _bash(data_repo, "git push origin HEAD", path=_nogh_path(tmp_path))
    assert dec == "deny" and "public-remote guard" in why and "brain/decisions/D-1.md" in why


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_push_of_brain_data_to_a_local_remote_is_allowed(data_repo, tmp_path):
    bare = tmp_path / "bare.git"
    _git(tmp_path, "init", "-q", "--bare", str(bare))
    _git(data_repo, "remote", "add", "backup", str(bare))
    assert _bash(data_repo, "git push backup HEAD", path=_nogh_path(tmp_path)) is None


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_push_without_data_to_github_is_allowed(proj, tmp_path):
    _git(proj, "remote", "add", "origin", "https://github.com/acme/app.git")
    assert _bash(proj, "git push origin HEAD", path=_nogh_path(tmp_path)) is None


# ------------------------------------------------------------------ fail closed

def test_unreadable_payload_is_denied(proj):
    assert _decision(_hook(proj, "not json"))[0] == "deny"


def test_tampered_gate_blocks_every_call(proj):
    gate = proj / ".claude" / "hooks" / "tess-gate.py"
    gate.write_text(gate.read_text() + "\n# tampered\n")
    r = _hook(proj, {"turn_id": "t", "tool_name": "Bash", "tool_input": {"command": "ls"},
                     "cwd": str(proj)})
    assert r.returncode == 2 and "TESS HOOK NOT RUN" in r.stderr


def test_no_python3_blocks(proj, tmp_path):
    bindir = tmp_path / "nopy"  # sh and dirname, but no python3
    bindir.mkdir()
    for tool in ("sh", "dirname"):
        (bindir / tool).symlink_to(shutil.which(tool))
    r = subprocess.run(["/bin/sh", "-c", HOOK_CMD], input="{}", capture_output=True, text=True,
                       cwd=str(proj), env={"PATH": str(bindir)})
    assert r.returncode == 2 and "python3 was not found" in r.stderr


def test_outside_an_instance_blocks(tmp_path):
    r = subprocess.run(["sh", "-c", HOOK_CMD], input="{}", capture_output=True, text=True,
                       cwd=str(tmp_path), env={"PATH": os.environ["PATH"]})
    assert r.returncode == 2 and "TESS GATE NOT RUN" in r.stderr


# ------------------------------------------------------------------ rules backstop

RULES = REPO / ".codex" / "rules" / "tess.rules"


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not installed")
@pytest.mark.parametrize("cmd,want", [
    ("git commit --no-verify -m x", "forbidden"),
    ("git push --no-verify origin main", "forbidden"),
    ("git commit -n -m x", "forbidden"),
    ("gh auth token", "forbidden"),
    ("git remote add pub https://github.com/a/b.git", "prompt"),
    ("gh repo edit --visibility public", "prompt"),
    ("git config core.hooksPath /dev/null", "prompt"),
    ("git -c core.hooksPath=/dev/null commit -m x", "prompt"),
    ("git push --force origin main", "prompt"),
    ("git commit -m ok", None),
    ("git status", None),
])
def test_codex_rules_decisions(cmd, want):
    r = subprocess.run(["codex", "execpolicy", "check", "--rules", str(RULES), "--", *cmd.split()],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout).get("decision")
    assert got == want, (cmd, r.stdout)


def test_denies_are_logged_redacted(proj):
    tok = "ghp_" + "Z9y8X7w6" * 5
    _hook(proj, {"turn_id": "t9", "session_id": "s9", "tool_name": "Bash", "cwd": str(proj),
                 "tool_input": {"command": f"git commit --no-verify -m '{tok}'"}})
    lines = (proj / "home" / "gate.log").read_text().splitlines()
    entry = json.loads(lines[-1])
    assert entry["decision"] == "deny" and entry["turn_id"] == "t9" and entry["codex"] is True
    assert tok not in lines[-1]
