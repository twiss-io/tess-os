"""
v1.0 final review, round 2 (writer G1b): tess-gate command handlers and the
core.hooksPath tripwire. Every payload below comes from the two final reviews
(scratchpad/final-review/r6-codex-review.md, r6-cyra-review.md) and failed at
8f78d69; the controls keep ordinary find, cp, sed, git push/tag and apply_patch
work allowed.

  * GPT-6 #7   find on out-of-project control roots (~/.claude, ~/.codex)
  * GPT-6 #8   find -L / -follow link-following traversal
  * GPT-6 #13  boolean find expressions (false positive)
  * GPT-6 #12  cp sources are reads (false positive)
  * GPT-6 #14  git push --follow-tags pushes only reachable annotated tags
  * Cyra H3    indented apply_patch headers; unknown `*** ` lines
  * Cyra H4    shell apply_patch / applypatch with a heredoc, here-string or pipe
  * Cyra M1    a push of a branch or tag the same command creates (false positive)
  * Cyra M2    sed w/W commands and s///w flags; any separator before .git/
  * Cyra L2    the anchor words in prose (false positive)
  * Cyra H1    core.hooksPath tripwire in run-pinned.py, hooks-status and doctor
  * Cyra "not covered": Codex exec payloads (workdir, cmd, typed input)
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / ".claude" / "hooks" / "tess-gate.py"
HAS_GIT = shutil.which("git") is not None
PUB = "https://github.com/acme/pub.git"


def _gate():
    sys.dont_write_bytecode = True  # never leave __pycache__ in .claude/hooks
    spec = importlib.util.spec_from_file_location("tess_gate_r6_cmds", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _gate()


def _git(root, *args, env=None):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _commit(root, msg="c"):
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@tess.test", "-c", "user.name=T", "-c", "commit.gpgsign=false",
         "commit", "-q", "--no-verify", "-m", msg)


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """A Tess instance copy in a git repo; HOME is a temp dir holding the
    user-level control files (~/.claude, ~/.codex, ~/.gitconfig)."""
    root = tmp_path / "proj"
    for rel in (".tess/tess.lock", ".tess/core/pinned-scripts.sha256", "tessctl",
                "tess.manifest.json", "conductor/guardrails.md", "CLAUDE.md", ".claude/settings.json",
                "scripts/tess"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    for tree in (".claude/hooks", "scripts/brain", ".tess/bin", ".tess/vendor"):
        shutil.copytree(REPO / tree, root / tree, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('hi')\n")
    (root / "README.md").write_text("readme\n")
    (root / "docs").mkdir()
    (root / "a.tmp").write_text("x\n")
    (root / "b.log").write_text("x\n")
    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text("{}\n")
    (home / ".claude" / "projects" / "s.jsonl").write_text("{}\n")
    (home / ".codex").mkdir()
    (home / ".codex" / "config.toml").write_text("")
    (home / ".gitconfig").write_text("[user]\n\tname = T\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("TESS_BRAIN_PROVENANCE_DIR", raising=False)
    for k in [k for k in os.environ if k.startswith("GIT_CONFIG")]:
        monkeypatch.delenv(k, raising=False)
    G._CONTROL_CACHE.clear()
    if HAS_GIT:
        _git(tmp_path, "init", "-b", "main", "-q", str(root))
        _commit(root, "init")
    return root


def _eval(root, cmd, codex=False, tool="Bash", tin=None):
    data = {"tool_name": tool, "cwd": str(root), "tool_input": tin if tin is not None else {"command": cmd},
            "permission_mode": "default"}
    if codex:
        data["turn_id"] = "t1"
    return G.evaluate(data, root)


def _level(root, cmd, **kw):
    return ["allow", "ask", "deny"][_eval(root, cmd, **kw).level]


def _decide(root, cmd, runtime, tool="Bash", tin=None):
    data = {"tool_name": tool, "cwd": str(root), "tool_input": tin if tin is not None else {"command": cmd},
            "permission_mode": "default"}
    if runtime == "codex":
        data["turn_id"] = "t1"
    return G.decide(data, root, runtime)[0] or "allow"


# ------------------------------------------------------------------ GPT-6 #7: find on control roots

@pytest.mark.parametrize("cmd", [
    "find ~/.claude -maxdepth 1 -name settings.json -delete",
    "find ~/.codex -maxdepth 1 -name config.toml -delete",
    "find ~/.claude -name 'settings*.json' -exec rm {} +",
    "find ~ -maxdepth 2 -path '*/.codex/*' -delete",
])
def test_find_on_external_control_roots_is_denied(proj, cmd):
    v = _eval(proj, cmd)
    assert v.level == G.DENY, (cmd, v.reasons)
    assert "protected Tess path" in "; ".join(v.reasons)


@pytest.mark.parametrize("cmd", [
    "find ~/.claude/projects -name '*.jsonl' -delete",
    "find ~/.claude -maxdepth 1 -name '*.log' -delete",
    "find ~/.claude -name settings.json",
])
def test_find_on_external_roots_control_allowed(proj, cmd):
    assert _level(proj, cmd) == "allow", cmd


# ------------------------------------------------------------------ GPT-6 #8: find -L / -follow

@pytest.mark.parametrize("cmd", ["find -L build -type f -delete", "find build -follow -type f -delete",
                                 "find -L build -exec rm {} +"])
def test_find_following_links_does_not_pass(proj, cmd):
    (proj / "build").mkdir()
    (proj / "build" / "controls").symlink_to("../.claude")
    assert _level(proj, cmd) == "ask", cmd
    assert _decide(proj, cmd, "codex") == "deny"


def test_find_following_links_controls(proj):
    (proj / "build").mkdir()
    (proj / "build" / "x.o").write_text("o\n")
    assert _level(proj, "find -L build -name '*.o'") == "allow"
    assert _level(proj, "find build -name '*.o' -delete") == "allow"
    assert _level(proj, "find -H build -name '*.o' -delete") == "allow"


# ------------------------------------------------------------------ GPT-6 #13: boolean find

@pytest.mark.parametrize("cmd", [
    "find . -maxdepth 1 -type f \\( -name '*.tmp' -o -name '*.log' \\) -delete",
    "find . -maxdepth 1 \\( -name '*.tmp' -or -name '*.log' \\) -type f -delete",
    "find . -type f \\( -name '*.tmp' -o -name '*.log' \\) -mtime +7 -exec rm -f {} +",
    "find . -name '*.pyc' -delete",
    "find . -type d -name __pycache__ -exec rm -rf {} +",
])
def test_boolean_find_cleanup_is_allowed(proj, cmd):
    v = _eval(proj, cmd)
    assert v.level == G.ALLOW, (cmd, v.reasons)


@pytest.mark.parametrize("cmd", [
    "find . -maxdepth 1 -type f \\( -name '*.tmp' -o -name '*.md' \\) -delete",
    "find . ! -name '*.tmp' -delete",
    "find . -name '*.tmp' -o -delete",
    "find . -not -type d -delete",
    "find . -maxdepth 1 -iname 'claude.MD' -delete",
    "find . -path './.claude/*' -exec rm {} \\;",
    "find . -frobnicate x -delete",  # unreadable: every file counts, as before
    "find . \\( -name '*.tmp' -delete",
])
def test_boolean_find_still_denies_protected_matches(proj, cmd):
    v = _eval(proj, cmd)
    assert v.level == G.DENY, (cmd, v.reasons)


# ------------------------------------------------------------------ GPT-6 #12: cp sources are reads

@pytest.mark.parametrize("cmd", [
    "cp ~/.gitconfig /tmp/gitconfig.backup",
    "cp ~/.codex/config.toml /tmp/codex-config.bak",
    "cp ~/.claude/settings.json /tmp/claude-settings.bak",
    "cp CLAUDE.md /tmp/claude-md.bak",
    "cp -p .claude/settings.json docs/settings-copy.json",
])
def test_copy_from_a_protected_file_is_allowed(proj, cmd):
    v = _eval(proj, cmd)
    assert v.level == G.ALLOW, (cmd, v.reasons)


@pytest.mark.parametrize("cmd", [
    "cp /tmp/x ~/.gitconfig",
    "cp /tmp/x CLAUDE.md",
    "cp /tmp/a /tmp/b .claude/hooks/",
    "cp -t .claude /tmp/settings.json",
    "cp --target-directory=.claude/hooks /tmp/x.py",
    "cp -l CLAUDE.md /tmp/hardlink",
    "cp -s ~/.gitconfig /tmp/link",
    "cp ~/.config/tess/signing.key /tmp/k",
])
def test_copy_destinations_links_and_key_reads_stay_denied(proj, cmd):
    v = _eval(proj, cmd)
    assert v.level == G.DENY, (cmd, v.reasons)


# ------------------------------------------------------------------ push fixtures

@pytest.fixture
def side_data(proj, tmp_path, monkeypatch):
    """brain/ data only on branch `data` (lightweight tag private-notes on it);
    main (HEAD) is clean; origin is public (no gh on PATH)."""
    _git(proj, "checkout", "-q", "-b", "data")
    (proj / "brain").mkdir()
    (proj / "brain" / "private.md").write_text("private\n")
    _commit(proj, "data")
    _git(proj, "tag", "private-notes")
    _git(proj, "checkout", "-q", "main")
    _git(proj, "remote", "add", "origin", PUB)
    nogh = tmp_path / "nogh"
    nogh.mkdir()
    for tool in ("python3", "git"):
        (nogh / tool).symlink_to(sys.executable if tool == "python3" else shutil.which(tool))
    monkeypatch.setenv("PATH", f"{nogh}:/bin:/usr/bin")
    return proj


# ------------------------------------------------------------------ GPT-6 #14: --follow-tags

@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_follow_tags_clean_push_is_allowed(side_data):
    v = _eval(side_data, "git push --follow-tags origin main")
    assert v.level == G.ALLOW, v.reasons
    _git(side_data, "-c", "user.email=t@tess.test", "-c", "user.name=T", "tag", "-a", "-m", "x",
         "data-release", "data")  # annotated, but not in main's history
    v = _eval(side_data, "git push --follow-tags origin main")
    assert v.level == G.ALLOW, v.reasons


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_follow_tags_neighbours_still_denied(side_data):
    for cmd in ("git push --tags origin main", "git push origin main private-notes",
                "git push --follow-tags origin data"):
        v = _eval(side_data, cmd)
        assert v.level == G.DENY and "brain/private.md" in "; ".join(v.reasons), (cmd, v.reasons)


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_follow_tags_picks_reachable_annotated_tags_only(side_data):
    top = str(side_data)
    tag = ["-c", "user.email=t@tess.test", "-c", "user.name=T", "tag"]
    _git(side_data, *tag, "-a", "-m", "release", "v1.0", "main")
    _git(side_data, *tag, "light-main", "main")
    _git(side_data, *tag, "-a", "-m", "side", "v-side", "data")
    names = lambda refs: sorted(r for r, _s in refs)  # noqa: E731
    assert names(G._push_refs(top, [], "origin", ["main"], ["--follow-tags"])) == ["main", "refs/tags/v1.0"]
    assert names(G._push_refs(top, [], "origin", ["main"], [])) == ["main"]
    _git(side_data, "config", "push.followTags", "true")
    assert names(G._push_refs(top, [], "origin", ["main"], [])) == ["main", "refs/tags/v1.0"]
    assert names(G._push_refs(top, [], "origin", ["main"], ["--no-follow-tags"])) == ["main"]
    assert names(G._push_refs(top, [], "origin", ["main"], ["--no-follow-tags", "--follow-tags"])) == \
        ["main", "refs/tags/v1.0"]


# ------------------------------------------------------------------ Cyra M1: push what the command creates

@pytest.mark.skipif(not HAS_GIT, reason="git required")
@pytest.mark.parametrize("cmd", [
    'git checkout -b feature/signup && git add -A && git commit -m "Add signup" && git push -u origin feature/signup',
    'git switch -c fix/typo && git commit -am "typo" && git push -u origin fix/typo',
    "git tag v2.0.0 && git push origin v2.0.0",
    "git tag -a v2.0.1 -m 'release' && git push origin tag v2.0.1",
    "git branch topic && git push origin topic:topic",
])
def test_push_of_a_ref_the_command_creates_is_left_to_the_pre_push_hook(side_data, cmd):
    for runtime in ("claude", "codex"):
        assert _decide(side_data, cmd, runtime) == "allow", (runtime, cmd)


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_push_of_a_missing_ref_says_so_and_neighbours_stay_denied(side_data):
    v = _eval(side_data, "git push origin no-such-branch")
    assert v.level == G.DENY
    assert "does not exist yet" in "; ".join(v.reasons) and "RuntimeError" not in "; ".join(v.reasons)
    v = _eval(side_data, "git checkout -b feature/x && git push origin feature/x data")
    assert v.level == G.DENY and "brain/private.md" in "; ".join(v.reasons), v.reasons


# ------------------------------------------------------------------ Cyra H3: indented apply_patch headers

def _patch(root, text, runtime="codex"):
    return _decide(root, None, runtime, tool="apply_patch", tin={"command": text})


@pytest.mark.parametrize("text", [
    "*** Begin Patch\n  *** Delete File: .tess/tess.lock\n*** Add File: docs/a.md\n+x\n*** End Patch",
    "*** Begin Patch\n *** Update File: CLAUDE.md\n@@\n-a\n+b\n*** Add File: docs/a.md\n+x\n*** End Patch",
    "*** Begin Patch\n*** Add File: docs/a.md\n+x\n\t*** Add File: .claude/settings.json\n+{}\n*** End Patch",
    "*** Begin Patch\n*** Update File: src/app.py\n *** Move to: .claude/settings.json\n@@\n-a\n+b\n*** End Patch",
    "*** Begin Patch\n*** Add File: docs/a.md\n+x\n*** Frobnicate File: CLAUDE.md\n*** End Patch",
    "*** Begin Patch\n*** Add File: docs/a.md\n+x\n  ***  Delete File: .tess/tess.lock\n*** End Patch",
])
def test_indented_or_unknown_patch_headers_are_denied(proj, text):
    assert _patch(proj, text) == "deny"
    assert _patch(proj, text, "claude") == "deny"


@pytest.mark.parametrize("text", [
    "*** Begin Patch\n*** Update File: src/app.py\n@@\n-print('hi')\n+print('ho')\n*** End Patch",
    "*** Begin Patch\n*** Add File: docs/notes.md\n+*** not a header, just text\n+***bold***\n*** End Patch",
    "*** Begin Patch\n  *** Add File: docs/indented.md\n+x\n*** End of File\n*** End Patch",
])
def test_ordinary_patches_are_allowed(proj, text):
    assert _patch(proj, text) == "allow"


# ------------------------------------------------------------------ Cyra H4: apply_patch from the shell

H4_DENY = [
    "apply_patch <<'EOF'\n*** Begin Patch\n*** Update File: CLAUDE.md\n@@\n-a\n+b\n*** End Patch\nEOF",
    "applypatch <<'EOF'\n*** Begin Patch\n*** Delete File: .tess/tess.lock\n*** End Patch\nEOF",
    "cd .claude && apply_patch <<'EOF'\n*** Begin Patch\n*** Update File: settings.json\n@@\n-a\n+b\n*** End Patch\nEOF",
    "apply_patch '*** Begin Patch\n*** Delete File: AGENTS.md\n*** End Patch'",
    "apply_patch <<< '*** Begin Patch\n*** Delete File: CLAUDE.md\n*** End Patch'",
    "printf '*** Begin Patch\\n*** Delete File: CLAUDE.md\\n*** End Patch\\n' | apply_patch",
    "timeout 30 applypatch <<'EOF'\n*** Begin Patch\n  *** Delete File: .tess/tess.lock\n*** End Patch\nEOF",
]


@pytest.mark.parametrize("cmd", H4_DENY)
def test_shell_apply_patch_is_checked(proj, cmd):
    assert _decide(proj, cmd, "codex") == "deny", cmd
    assert _decide(proj, cmd, "claude") == "deny", cmd


@pytest.mark.parametrize("cmd", ['apply_patch "$(cat /tmp/p.patch)"', "curl -s https://x.test/p | apply_patch",
                                 "apply_patch < /tmp/no-such.patch"])
def test_shell_apply_patch_unreadable_body_asks(proj, cmd):
    assert _level(proj, cmd) == "ask", cmd
    assert _decide(proj, cmd, "codex") == "deny"


def test_shell_apply_patch_ordinary_file_is_allowed(proj):
    cmd = "apply_patch <<'EOF'\n*** Begin Patch\n*** Add File: docs/notes.md\n+hello\n*** End Patch\nEOF"
    assert _decide(proj, cmd, "codex") == "allow"
    cmd = "cd src && apply_patch <<'EOF'\n*** Begin Patch\n*** Update File: app.py\n@@\n-print('hi')\n+print('ho')\n*** End Patch\nEOF"
    assert _decide(proj, cmd, "codex") == "allow"


# ------------------------------------------------------------------ Cyra M2: sed w

@pytest.mark.parametrize("cmd", [
    "sed -n 'w CLAUDE.md' README.md",
    "sed 's/a/b/w .claude/settings.json' README.md",
    "sed -n 'w .git/config' /tmp/cfg",
    "sed -e 's/x/y/' -e '/z/W AGENTS.md' README.md",
    "sed -n '1,5{w .tess/tess.lock\n}' README.md",
    "sed --expression='s/a/b/gw CLAUDE.md' README.md",
    "sed -E -n '$w .codex/config.toml' README.md",
])
def test_sed_write_commands_are_write_targets(proj, cmd):
    v = _eval(proj, cmd)
    assert v.level == G.DENY, (cmd, v.reasons)


@pytest.mark.parametrize("cmd", ["mytool --out=.git/hooks/pre-push",
                                 "python3 tool.py --target=.git/config"])
def test_git_dir_paths_after_any_separator_are_denied(proj, cmd):
    assert _level(proj, cmd) == "deny", cmd


@pytest.mark.parametrize("cmd", ["sed -e '1e rm CLAUDE.md' README.md", "sed 's/.*/rm x/e' README.md",
                                 "sed -f /tmp/no-such-script.sed README.md"])
def test_sed_that_runs_commands_or_cannot_be_read_asks(proj, cmd):
    assert _level(proj, cmd) == "ask", cmd


@pytest.mark.parametrize("cmd", [
    "sed -n '/x/p' README.md",
    "sed 's/foo/bar/g' README.md > /tmp/out",
    "sed -i '' 's/foo/bar/' src/app.py",
    "sed -i.bak -e 's/wow/wee/' src/app.py",
    "sed -n 'w /tmp/copy.txt' README.md",
    "sed '/^#/d;s/west/east/w /tmp/changed.txt' README.md",
    "sed -n '$=' README.md",
    "sed --sandbox 's/a/b/' README.md",
    "echo 'see .git/hooks/pre-push for details'",
])
def test_ordinary_sed_is_allowed(proj, cmd):
    v = _eval(proj, cmd)
    assert v.level == G.ALLOW, (cmd, v.reasons)


# ------------------------------------------------------------------ Cyra L2: anchor words in prose

@pytest.mark.parametrize("cmd", [
    'echo "run tessctl anchor accept yourself" > docs/howto.md',
    "printf 'Run ./tessctl anchor accept in your terminal\\n' >> docs/howto.md",
    'git commit -m "docs: explain tessctl anchor accept"',
])
def test_anchor_words_in_prose_are_allowed(proj, cmd):
    v = _eval(proj, cmd)
    assert v.level == G.ALLOW, (cmd, v.reasons)


@pytest.mark.parametrize("cmd", [
    "./tessctl anchor accept",
    "python3 tessctl anchor init",
    "python3 -c \"import os; os.system('tessctl anchor accept')\"",
    "bash -c './tessctl anchor accept'",
    "eval './tessctl anchor accept'",
])
def test_anchor_writes_stay_denied(proj, cmd):
    assert _level(proj, cmd) == "deny", cmd


# ------------------------------------------------------------------ Codex exec payloads

def test_codex_exec_command_cmd_key_is_read(proj):
    assert _decide(proj, None, "codex", tin={"cmd": "rm -f CLAUDE.md"}) == "deny"
    assert _decide(proj, None, "codex", tin={"cmd": "rm -f settings.json", "workdir": ".claude"}) == "deny"
    assert _decide(proj, None, "codex", tin={"cmd": "ls", "workdir": "src"}) == "allow"


@pytest.mark.parametrize("cmd", ["bash", "sh -i", "zsh -l", "python3", "node", "timeout 600 bash",
                                 "cd src && bash"])
def test_codex_commands_waiting_for_typed_input_are_denied(proj, cmd):
    assert _decide(proj, cmd, "codex") == "deny", cmd


@pytest.mark.parametrize("cmd", ["bash -c 'echo hi'", "bash scripts/build.sh", "python3 src/app.py",
                                 "echo 'echo hi' | bash", "python3 -m pytest -q", "./tessctl status",
                                 "node -e 'console.log(1)'"])
def test_codex_ordinary_commands_are_allowed(proj, cmd):
    assert _decide(proj, cmd, "codex") == "allow", cmd


def test_claude_bare_shell_is_unchanged(proj):
    assert _decide(proj, "bash", "claude") == "allow"


# ------------------------------------------------------------------ Cyra H1: core.hooksPath tripwire

def _launcher():
    spec = importlib.util.spec_from_file_location("run_pinned_r6", str(REPO / ".claude/hooks/run-pinned.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


L = _launcher()


def _run_gate(root, env=None):
    payload = json.dumps({"tool_name": "Bash", "cwd": str(root), "tool_input": {"command": "ls"},
                          "permission_mode": "default"})
    return subprocess.run([sys.executable, "-I", "-B", str(root / ".claude/hooks/run-pinned.py"),
                           "--on-fail", "block", "--", ".claude/hooks/tess-gate.py", "--runtime", "claude"],
                          input=payload, capture_output=True, text=True, cwd=str(root),
                          env=dict(env or os.environ, CLAUDE_PROJECT_DIR=str(root)), timeout=120)


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_hookspath_unset_or_tess_own_folder_passes(proj):
    assert L.hookspath_problem(proj) is None
    assert _run_gate(proj).returncode == 0
    _git(proj, "config", "core.hooksPath", ".git/hooks")
    assert L.hookspath_problem(proj) is None
    _git(proj, "config", "core.hooksPath", str(proj / ".git" / "hooks"))
    assert L.hookspath_problem(proj) is None


@pytest.mark.skipif(not HAS_GIT, reason="git required")
@pytest.mark.parametrize("scope", ["local", "global", "env"])
def test_hookspath_elsewhere_stops_every_hook(proj, scope, monkeypatch):
    env = None
    if scope == "local":
        _git(proj, "config", "core.hooksPath", "/dev/null")
    elif scope == "global":
        with open(Path(os.environ["HOME"]) / ".gitconfig", "a") as fh:
            fh.write("[core]\n\thooksPath = /tmp/elsewhere\n")
    else:
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/dev/null")
        env = dict(os.environ)
    why = L.hookspath_problem(proj)
    assert why and "core.hooksPath" in why
    if scope == "global":
        assert "git config --global --unset core.hooksPath" in why
    if scope == "local":
        assert "git config --unset core.hooksPath" in why
    r = _run_gate(proj, env)
    assert r.returncode == 2 and "core.hooksPath" in r.stderr, r.stderr


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_hooks_status_and_doctor_report_hookspath(proj, engine):
    _git(proj, "config", "core.hooksPath", "/dev/null")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CODEX_", "CLAUDE_CODE_"))}
    r = subprocess.run([sys.executable, "-I", "-B", str(proj / "scripts" / "tess"), "hooks-status",
                        "--runtime", "claude"], capture_output=True, text=True, cwd=str(proj),
                       env=dict(env, CLAUDE_CODE_SESSION_ID="s1"), timeout=60)
    assert r.returncode == 1 and "OFF" in r.stdout and "core.hooksPath" in r.stdout, r.stdout
    lines = engine._hookspath_findings(proj)
    assert lines and "core.hooksPath" in lines[0]
    _git(proj, "config", "--unset", "core.hooksPath")
    assert engine._hookspath_findings(proj) == []
