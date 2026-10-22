"""
v1.0 run-escalation review (Cyra, release/v1.0 @ 97207c9): every probe in the
review, as a test that fails on 97207c9 and passes after the fix.

F1 (critical)  `tessctl run --driver codex` gave a worker `codex -s
               workspace-write` over the whole project (the driver's cwd is
               the Tess root, so "is cwd a linked worktree" only asked whether
               the Tess checkout itself was one). Now: always `-s read-only`.
F2 (high)      `tessctl run` (any spelling) went around the agent-CLI policy
               and the peer-call depth limit: the gate allowed it everywhere,
               and tessctl dispatched from inside a peer call. Children got
               TESS_HEADLESS=1, which also switched off the brain hooks. Now:
               the gate treats it as an agent-CLI launch, tessctl refuses at
               TESS_CONSULT_DEPTH >= 1, and children get TESS_DISPATCHED=1.
F3 (high)      codex `-o` (written outside its read-only sandbox) followed a
               symlink planted at the return path while the child ran, and the
               gate allowed planting it. Now: the child writes into a private
               temp folder and tessctl installs the file without following
               any symlink; the same for the claude driver.
F4 (medium)    relative `ln -s` targets read from cwd, CDPATH not modelled,
               inline-code links allowed.
F5 (medium)    sqlite3 / duckdb were not writers.
F6 (medium)    a run-time part after a fixed folder outside the project was
               allowed even when it could hold "/" and climb back in.
2(b)           errors and git failures inside decide() must end in deny or
               ask, never allow.

Decisions are checked for Claude Code default mode, Claude Code acceptEdits
and Codex, as (claude default, claude acceptEdits, codex).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / ".claude" / "hooks" / "tess-gate.py"
TESSCTL = REPO / ".tess" / "bin" / "tessctl"
HAS_GIT = shutil.which("git") is not None
POSIX = os.name == "posix"


def _gate():
    sys.dont_write_bytecode = True  # never leave __pycache__ in .claude/hooks
    spec = importlib.util.spec_from_file_location("tess_gate_run_escalation", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _gate()


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    """A Tess instance copy (lock, pins, hooks) with a fake HOME."""
    tmp = tmp_path_factory.mktemp("runesc")
    root = tmp / "proj"
    for rel in (".tess/tess.lock", ".tess/core/pinned-scripts.sha256", "tessctl",
                "tess.manifest.json", "conductor/guardrails.md", "CLAUDE.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    for tree in (".claude/hooks", "scripts/brain", ".tess/bin", ".tess/vendor"):
        shutil.copytree(REPO / tree, root / tree, ignore=shutil.ignore_patterns("__pycache__"))
    (root / ".claude" / "settings.json").write_text("{}\n")
    (root / "missions" / "m1" / "returns").mkdir(parents=True)
    home = tmp / "home"
    (home / ".config").mkdir(parents=True)
    return root, home


@pytest.fixture(autouse=True)
def _env(proj, monkeypatch):
    monkeypatch.setenv("HOME", str(proj[1]))
    for k in ("XDG_CONFIG_HOME", "TESS_BRAIN_PROVENANCE_DIR", "GIT_DIR", "GIT_WORK_TREE",
              "TESS_CONSULT_DEPTH", "CDPATH", "TESS_HEADLESS", "TESS_DISPATCHED"):
        monkeypatch.delenv(k, raising=False)
    # The test runner's own ancestry is not the gate's (the suite may run
    # from inside an agent session).
    monkeypatch.setattr(G, "_ancestry", lambda limit=40: ["python3", "zsh", "login"], raising=False)


def _decide(proj, cmd, runtime="claude", mode="default"):
    root = proj[0]
    data = {"tool_name": "Bash", "cwd": str(root), "tool_input": {"command": cmd}}
    if runtime == "codex":
        data["turn_id"] = "t"
    else:
        data["permission_mode"] = mode
    return G.decide(data, root, runtime)


def _all(proj, cmd):
    """(claude default, claude acceptEdits, codex) decisions."""
    return tuple(_decide(proj, cmd, rt, mode)[0] or "allow"
                 for rt, mode in (("claude", "default"), ("claude", "acceptEdits"), ("codex", None)))


ALLOW = ("allow", "allow", "allow")
ASK = ("ask", "ask", "deny")  # Codex cannot pause to ask: an ask is a deny there
DENY = ("deny", "deny", "deny")


# ====================================================================== F1 / F2: the gate

RUN_DISPATCH = [
    # Cyra's probes, verbatim
    "./tessctl run --driver codex plan.json",
    "./tessctl run --driver claude plan.json",
    "python3 -I .tess/bin/tessctl run --driver codex plan.json",
    # the default driver is claude
    "./tessctl run plan.json",
    ".tess/bin/tessctl run --driver codex plan.json",
    "python3 .tess/bin/tessctl run plan.json",
    "python3 -I -B .tess/bin/tessctl run plan.json --json",
    "bash -c './tessctl run --driver=codex plan.json'",
    "env FOO=1 ./tessctl run --dri codex plan.json",  # argparse takes a unique prefix
    "timeout 600 ./tessctl run plan.json",
    "nohup ./tessctl run plan.json &",
    "./tessctl run --driver fake plan.json --driver codex",  # the last --driver wins
    "./tessctl run --timeout 30 plan.json",
]


@pytest.mark.parametrize("cmd", RUN_DISPATCH)
def test_tessctl_run_is_an_agent_cli_launch(proj, cmd):
    assert _all(proj, cmd) == ASK, cmd
    assert "dispatches" in _decide(proj, cmd)[1]


RUN_ALLOWED = [
    "./tessctl run --driver fake plan.json",
    "./tessctl run plan.json --driver=fake",
    "python3 -I .tess/bin/tessctl run --driver fake --fake-script s.json plan.json",
    "./tessctl run --help",
    "./tessctl run -h",
    "./tessctl status",
    "./tessctl verify",
    "./tessctl mission new 'x'",
    "./tessctl gate clear intake-before-anything --mission m1 --evidence README.md",
    "./tessctl help run",
]


@pytest.mark.parametrize("cmd", RUN_ALLOWED)
def test_tessctl_forms_that_dispatch_no_agent_stay_allowed(proj, cmd):
    assert _all(proj, cmd) == ALLOW, cmd


@pytest.mark.parametrize("depth", ["1", "2", "abc"])
@pytest.mark.parametrize("cmd", RUN_DISPATCH[:6])
def test_tessctl_run_inside_a_peer_call_is_refused(proj, monkeypatch, cmd, depth):
    monkeypatch.setenv("TESS_CONSULT_DEPTH", depth)
    assert _all(proj, cmd) == DENY, cmd
    assert "peer call" in _decide(proj, cmd)[1]


def test_tessctl_run_with_its_own_depth_or_from_a_nested_runtime_is_refused(proj, monkeypatch):
    assert _all(proj, "TESS_CONSULT_DEPTH=0 ./tessctl run --driver codex plan.json") == DENY
    assert _all(proj, "export TESS_CONSULT_DEPTH=0; ./tessctl run plan.json") == DENY
    monkeypatch.setattr(G, "_ancestry", lambda limit=40: ["python3", "sh", "codex", "zsh", "claude", "zsh"])
    G._STATE["nested"] = None
    assert _all(proj, "./tessctl run plan.json") == DENY
    # the fake driver starts no agent, even there
    assert _all(proj, "./tessctl run --driver fake plan.json") == ALLOW


def test_fake_driver_inside_a_peer_call_is_still_allowed(proj, monkeypatch):
    monkeypatch.setenv("TESS_CONSULT_DEPTH", "1")
    assert _all(proj, "./tessctl run --driver fake plan.json") == ALLOW


def test_the_gate_runs_tessctl_run_as_the_hook_process(proj):
    root = proj[0]
    env = {k: v for k, v in os.environ.items() if k not in ("TESS_CONSULT_DEPTH", "CDPATH")}
    env.update(CLAUDE_PROJECT_DIR=str(root), HOME=str(proj[1]))

    def run(cmd, extra=None):
        payload = {"tool_name": "Bash", "cwd": str(root), "tool_input": {"command": cmd}, "turn_id": "t"}
        r = subprocess.run([sys.executable, str(root / ".claude/hooks/tess-gate.py"), "--runtime", "codex"],
                           input=json.dumps(payload), capture_output=True, text=True,
                           env={**env, **(extra or {})}, timeout=120)
        out = r.stdout.strip()
        return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else "allow"

    assert run("./tessctl run --driver codex plan.json") == "deny"
    assert run("./tessctl run --driver fake plan.json") == "allow"


# ====================================================================== F4: parser differences

def test_relative_symlink_target_resolves_from_the_links_folder(proj):
    # Cyra's probe: the link points at the project's CLAUDE.md
    assert _all(proj, "ln -s ../../../CLAUDE.md missions/m1/returns/t1.return.json") == DENY
    assert _all(proj, "ln -sf ../../../.claude/settings.json missions/m1/returns/t1.verdict.json") == DENY
    assert _all(proj, "ln -s -f ../../../CLAUDE.md -t missions/m1/returns") == DENY
    # controls
    assert _all(proj, "ln -sf $PWD/CLAUDE.md missions/m1/returns/t1.return.json") == DENY
    assert _all(proj, "ln -s ../../README.md missions/m1/readme-link") == ALLOW
    assert _all(proj, "ln -s /var/tmp/x missions/m1/tmp-link") == ALLOW


@pytest.mark.parametrize("cmd", [
    """python3 -c 'import os; os.symlink("../../../CLAUDE.md", "missions/m1/returns/t1.return.json")'""",
    """python3 -c 'from pathlib import Path; Path("missions/m1/x").symlink_to("../../CLAUDE.md")'""",
    """python3 -c 'import os; os.link("a", "b")'""",
    """python3 -c 'from pathlib import Path; Path("b").hardlink_to("a")'""",
    """node -e 'require("fs").symlinkSync("../../CLAUDE.md", "missions/m1/x")'""",
    """perl -e 'symlink("../../CLAUDE.md", "missions/m1/x")'""",
])
def test_inline_interpreter_links_ask(proj, cmd):
    assert _all(proj, cmd) == ASK, cmd


def test_inline_interpreter_without_links_stays_allowed(proj):
    assert _all(proj, "python3 -c 'print(1)'") == ALLOW
    assert _all(proj, "node -e 'console.log(1)'") == ALLOW


@pytest.mark.parametrize("cmd", [
    # Cyra's probes
    "CDPATH=.claude cd hooks; : > tess-gate.py",
    "export CDPATH=.claude; cd hooks && : > tess-gate.py",
    # a plain shell variable is enough for cd
    "CDPATH=.claude; cd hooks && : > tess-gate.py",
    "CDPATH=.claude pushd hooks && : > tess-gate.py",
])
def test_cdpath_makes_a_relative_cd_unknown(proj, cmd):
    # A relative write after a cd Tess cannot resolve is refused (the gate's
    # existing rule for a run-time `cd`).
    assert _all(proj, cmd) == DENY, cmd


def test_inherited_cdpath_makes_a_relative_cd_unknown(proj, monkeypatch):
    monkeypatch.setenv("CDPATH", ".claude")
    assert _all(proj, "cd hooks && : > tess-gate.py") == DENY
    # ./ and ../ and absolute targets never use CDPATH
    assert _all(proj, "cd ./missions && : > m1/x.txt") == ALLOW
    assert _all(proj, "cd /var/tmp && : > x.txt") == ALLOW


def test_cd_without_cdpath_is_unchanged(proj):
    assert _all(proj, "cd missions && : > m1/x.txt") == ALLOW
    assert _all(proj, "cd .claude/hooks && : > tess-gate.py") == DENY
    assert _all(proj, "CDPATH= cd missions && : > m1/x.txt") == ALLOW


# ====================================================================== F5: sqlite3 / duckdb

SQL_DENIED = [
    # Cyra's probes
    "sqlite3 x.db '.output CLAUDE.md' \"select 'PWNED'\"",
    "sqlite3 x.db '.once .claude/settings.json' 'select 1'",
    "sqlite3 x.db \"VACUUM INTO 'CLAUDE.md'\"",
    "sqlite3 CLAUDE.md 'create table t(x)'",
    "sqlite3 x.db \"ATTACH 'conductor/guardrails.md' AS g; create table g.t(x)\"",
    # the other writing forms
    "sqlite3 x.db '.backup CLAUDE.md'",
    "sqlite3 x.db '.backup main CLAUDE.md'",
    "sqlite3 x.db '.save CLAUDE.md'",
    "sqlite3 x.db '.clone CLAUDE.md'",
    "sqlite3 x.db '.open CLAUDE.md'",
    "sqlite3 x.db '.log CLAUDE.md'",
    "sqlite3 x.db '.out CLAUDE.md' 'select 1'",  # the shell takes abbreviations
    "sqlite3 -cmd '.output CLAUDE.md' x.db 'select 1'",
    "sqlite3 x.db \"attach database 'file:CLAUDE.md?mode=rwc' as g\"",
    "sqlite3 file:CLAUDE.md 'create table t(x)'",
    "sqlite3 x.db \"select writefile('CLAUDE.md', 'x')\"",
    "sqlite3 x.db '.shell rm CLAUDE.md'",
    "sqlite3 x.db '.output |tee CLAUDE.md' 'select 1'",
    "sqlite3 x.db <<'EOF'\n.output CLAUDE.md\nselect 1;\nEOF",
    "sqlite3 x.db <<< \"VACUUM INTO 'CLAUDE.md'\"",
    "echo \"VACUUM INTO 'CLAUDE.md'\" | sqlite3 x.db",
    "duckdb x.db \"COPY (select 1) TO 'CLAUDE.md'\"",
    "duckdb -c \"COPY (select 1) TO 'CLAUDE.md'\"",
    "duckdb x.db \"EXPORT DATABASE '.claude/hooks'\"",
]


@pytest.mark.parametrize("cmd", SQL_DENIED)
def test_sql_shell_writes_to_protected_paths_are_refused(proj, cmd):
    assert _all(proj, cmd) == DENY, cmd


SQL_ASKED = [
    "sqlite3 x.db < script.sql",
    "sqlite3 x.db '.read script.sql'",
    "sqlite3 -init setup.sql x.db 'select 1'",
    "cat script.sql | sqlite3 x.db",
    "sqlite3 x.db \"$SQL\"",
    "sqlite3 x.db \"VACUUM INTO '$OUT'\"",
    "sqlite3 x.db \"select load_extension('./evil')\"",
    "sqlite3 x.db '.cd .claude' '.output settings.json' 'select 1'",
    "HOME=/var/tmp/h sqlite3 x.db 'select 1'",
]


@pytest.mark.parametrize("cmd", SQL_ASKED)
def test_sql_from_input_tess_cannot_read_asks(proj, cmd):
    assert _all(proj, cmd) == ASK, cmd


SQL_ALLOWED = [
    "sqlite3 x.db 'select 1'",
    "sqlite3 -readonly x.db 'select count(*) from t'",
    "sqlite3 -json x.db 'select * from t'",
    "sqlite3 x.db '.tables'",
    "sqlite3 x.db '.schema'",
    "sqlite3 x.db '.output out.txt' 'select 1'",
    "sqlite3 x.db \"VACUUM INTO 'backup.db'\"",
    "sqlite3 x.db \"ATTACH 'other.db' AS o\"",
    "sqlite3 :memory: 'select 1'",
    "echo 'select 1' | sqlite3 x.db",
    "duckdb -c 'select 42'",
    "duckdb x.db \"COPY (select 1) TO 'out.csv'\"",
]


@pytest.mark.parametrize("cmd", SQL_ALLOWED)
def test_ordinary_sql_shell_use_stays_allowed(proj, cmd):
    assert _all(proj, cmd) == ALLOW, cmd


def test_sqliterc_runs_first_and_is_read(proj):
    rc = proj[1] / ".sqliterc"
    rc.write_text(".output CLAUDE.md\n")
    try:
        assert _all(proj, "sqlite3 x.db 'select 1'") == DENY
    finally:
        rc.unlink()
    assert _all(proj, "sqlite3 x.db 'select 1'") == ALLOW


# ====================================================================== F6: run-time paths

F6_ASKED = [
    # Cyra's probes
    'rm -rf "/var/tmp/build-$ID"',
    'read ID; rm -rf "/var/tmp/build-$ID"',
    'ID=$(cat id.txt); rm -rf "/var/tmp/build-$ID"',
    'rm -rf "/var/tmp/b-$1"',
    # the same through other writers
    'find "/var/tmp/b-$ID" -delete',
    'cp x "/var/tmp/out-$NAME"',
    ': > "/var/tmp/log-$(cat name.txt)"',
    'rm -rf "/var/tmp/b-$$/x/$ID"',
]


@pytest.mark.parametrize("cmd", F6_ASKED)
def test_run_time_part_that_could_climb_back_asks(proj, cmd):
    assert _all(proj, cmd) == ASK, cmd


F6_ALLOWED = [
    'rm -rf "$TMPDIR/x"',
    'rm -rf "/var/tmp/build-$$"',
    'mkdir -p "/var/tmp/run-$(date +%s)"',
    'mkdir -p "/var/tmp/run-$(date +%Y-%m-%dT%H%M%S)"',
    'rm -f "/var/tmp/out-$RANDOM.txt"',
    'rm -rf "/var/tmp/b-${#X}"',
    'rm -rf "/var/tmp/b-$((1 + 2))"',
    'rm -rf /var/tmp/x',
    'ID=abc; rm -rf "/var/tmp/build-$ID"',
    'rm -rf build',
]


@pytest.mark.parametrize("cmd", F6_ALLOWED)
def test_run_time_part_that_cannot_hold_a_slash_stays_allowed(proj, monkeypatch, cmd):
    monkeypatch.setenv("TMPDIR", "/var/tmp/")
    assert _all(proj, cmd) == ALLOW, cmd


def test_known_dotdot_after_a_run_time_part_asks(proj):
    assert _all(proj, 'rm -rf "/var/tmp/b-$$/../../x"') == ASK


# ====================================================================== 2(b): decide() fails closed

FAULT_CORPUS = [
    "ls -la", "echo hi > notes.txt", ": > CLAUDE.md", "git status", "git reset --hard HEAD~1",
    "git checkout other -- .", "codex exec -s read-only x", "./tessctl run plan.json",
    "sqlite3 x.db 'select 1'", "rm -rf \"/var/tmp/b-$ID\"", "ln -s a b", "cd x && : > y",
]
FAULT_HELPERS = ["_git_ro", "protected_hit", "_word_values", "_check_agent_cli", "_check_program",
                 "check_command", "_security_tier_paths", "_tessctl_call", "_check_sql_cli",
                 "_ln_links", "_next_cwd", "_slash_free_runtime", "_evaluate"]


@pytest.mark.parametrize("helper", FAULT_HELPERS)
def test_an_error_in_any_helper_ends_in_deny(proj, monkeypatch, helper):
    called = []

    def boom(*a, **k):
        called.append(1)
        raise RuntimeError("forced")

    monkeypatch.setattr(G, helper, boom)
    for cmd in FAULT_CORPUS:
        called.clear()
        got = _all(proj, cmd)  # never raises out of decide()
        if called:
            assert got == DENY, (helper, cmd, got)
    # the helper is reached by at least one command in the corpus
    hits = 0
    for cmd in FAULT_CORPUS:
        called.clear()
        _all(proj, cmd)
        hits += bool(called)
    assert hits, helper


def test_an_unreadable_tess_lock_fails_closed(proj, monkeypatch):
    real = Path.read_text

    def unreadable(self, *a, **k):
        if self.name == "tess.lock":
            raise PermissionError(13, "Permission denied")
        return real(self, *a, **k)

    G._LOCK_CACHE.clear()
    monkeypatch.setattr(Path, "read_text", unreadable)
    assert _all(proj, "echo x > notes.txt") == DENY
    assert _all(proj, ": > conductor/guardrails.md") == DENY
    G._LOCK_CACHE.clear()


@pytest.fixture()
def gitproj(proj, tmp_path):
    """A git repository copy of the project: main has two commits, `other`
    the first; one stash changes CLAUDE.md."""
    root = tmp_path / "g"
    shutil.copytree(proj[0], root, symlinks=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}

    def git(*args):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)

    git("init", "-q", "-b", "main")
    git("config", "commit.gpgsign", "false")
    git("config", "core.hooksPath", os.devnull)
    git("add", "-A")
    git("commit", "-q", "--no-gpg-sign", "-m", "one")
    git("branch", "other")
    with open(root / "CLAUDE.md", "a") as fh:
        fh.write("two\n")
    git("commit", "-q", "--no-gpg-sign", "-am", "two")
    with open(root / "CLAUDE.md", "a") as fh:
        fh.write("stash\n")
    git("stash", "-q")
    return root, proj[1]


GIT_TREE_WRITES = [
    "git reset --hard HEAD~1", "git reset --hard other", "git reset other", "git stash pop",
    "git stash apply", "git update-ref refs/heads/main other", "git checkout other -- .",
    "git restore --source=other .", "git switch other", "git merge other", "git rebase other",
    "git read-tree other", "git push origin main",
]


@pytest.mark.skipif(not HAS_GIT, reason="git not installed")
@pytest.mark.parametrize("cmd", GIT_TREE_WRITES)
def test_git_timing_out_never_turns_a_tree_write_into_an_allow(gitproj, monkeypatch, cmd):
    real = G.subprocess.run

    def hung(argv, *a, **k):
        if argv and argv[0] == "git":
            raise subprocess.TimeoutExpired(argv, 1)
        return real(argv, *a, **k)

    monkeypatch.setattr(G.subprocess, "run", hung)
    got = _all(gitproj, cmd)
    assert "allow" not in got, (cmd, got)


# ====================================================================== tessctl: drivers, depth, install

def _engine():
    sys.dont_write_bytecode = True
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("tessctl_run_escalation", str(TESSCTL))
    spec = importlib.util.spec_from_loader("tessctl_run_escalation", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def eng():
    return _engine()


FAKE_AGENT = textwrap.dedent(r'''
    #!/usr/bin/env python3
    # A stand-in for `codex` / `claude`: records argv, cwd and env, does what
    # FAKE_AGENT_MODE says to the project while "running", then writes its
    # artifact where it was told to.
    import json, os, re, shutil, sys
    prog = os.path.basename(sys.argv[0])
    argv = sys.argv[1:]
    with open(os.environ["FAKE_AGENT_LOG"], "a") as fh:
        fh.write(json.dumps({"prog": prog, "argv": argv, "cwd": os.getcwd(),
                             "env": {k: os.environ.get(k) for k in
                                     ("TESS_DISPATCHED", "TESS_HEADLESS", "TESS_CONSULT_DEPTH")}}) + "\n")
    mode = os.environ.get("FAKE_AGENT_MODE", "good")
    root = os.environ["FAKE_AGENT_ROOT"]
    ret = os.path.join(root, os.environ["FAKE_AGENT_RET"])
    payload = os.environ.get("FAKE_AGENT_PAYLOAD", '{"from": "child"}')
    if mode == "swap-link":      # plant a symlink at the contracted return path mid-run
        os.makedirs(os.path.dirname(ret), exist_ok=True)
        if os.path.lexists(ret):
            os.unlink(ret)
        os.symlink(os.environ["FAKE_AGENT_VICTIM"], ret)
    elif mode == "swap-dir":     # swap the returns folder for a symlink to another folder
        d = os.path.dirname(ret)
        shutil.rmtree(d, ignore_errors=True)
        os.symlink(os.environ["FAKE_AGENT_VICTIM_DIR"], d)
    if prog == "codex":
        out = argv[argv.index("-o") + 1]
        if mode == "o-symlink":
            os.symlink(os.environ["FAKE_AGENT_VICTIM"], out)
        else:
            with open(out, "w") as fh:
                fh.write(payload)
        print(json.dumps({"type": "turn.completed"}))
    else:
        prompt = argv[argv.index("-p") + 1]
        if "--add-dir" in argv:
            add = argv[argv.index("--add-dir") + 1]
            out = re.search(r"`(" + re.escape(add) + r"[^`]*)`", prompt).group(1)
        else:  # the old prompt: a repo-relative path
            out = os.path.join(root, re.search(r"repo-relative path\s+`([^`]+)`", prompt).group(1))
        with open(out, "w") as fh:
            fh.write(payload)
        print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "ok"}))
''').lstrip()


@pytest.fixture()
def fake_agents(tmp_path, monkeypatch):
    """`codex` and `claude` stand-ins first on PATH, a project root, and the
    log of what each was started with."""
    if not POSIX:
        pytest.skip("POSIX symlinks and executables")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("codex", "claude"):
        p = bindir / name
        p.write_text(FAKE_AGENT)
        p.chmod(0o755)
    root = tmp_path / "project"
    (root / "missions" / "m1" / "returns").mkdir(parents=True)
    (root / "CLAUDE.md").write_text("ORIGINAL\n")
    log = tmp_path / "agent.log"
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_AGENT_LOG", str(log))
    monkeypatch.setenv("FAKE_AGENT_ROOT", str(root))
    monkeypatch.setenv("FAKE_AGENT_RET", "missions/m1/returns/t1.return.json")
    monkeypatch.setenv("FAKE_AGENT_VICTIM", str(root / "CLAUDE.md"))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", None)

    def calls():
        return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []

    return root, calls


def _brief(root, contract="return-manifest", ret="missions/m1/returns/t1.return.json"):
    return {"objective": "x", "output_contract": "x", "tools_sources_constraints": "x",
            "not_responsible_for": "x", "milestones": [], "escalation_trigger": "x",
            "_task_id": "t1", "_mission_id": "m1", "_contract_type": contract,
            "_return_manifest_path": ret, "_root": str(root)}


def _within(path, root):
    rp, rr = os.path.realpath(str(path)), os.path.realpath(str(root))
    return rp == rr or rp.startswith(rr + os.sep)


@pytest.mark.skipif(not HAS_GIT, reason="git not installed")
def test_codex_worker_in_a_linked_worktree_checkout_runs_read_only(eng, fake_agents, tmp_path, monkeypatch):
    """F1, Cyra's probe: the Tess checkout is itself a linked worktree."""
    _root, calls = fake_agents
    main = tmp_path / "main"
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", "-b", "main", str(main)], check=True, env=env)
    subprocess.run(["git", "-C", str(main), "config", "core.hooksPath", os.devnull], check=True, env=env)
    subprocess.run(["git", "-C", str(main), "commit", "-q", "--no-gpg-sign", "--allow-empty", "-m", "i"],
                   check=True, env=env)
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", "-b", "task", str(wt)], check=True, env=env)
    (wt / "missions" / "m1" / "returns").mkdir(parents=True)
    monkeypatch.setenv("FAKE_AGENT_ROOT", str(wt))
    raw = eng.CodexExecDriver(cwd=wt).dispatch(_brief(wt), output_schema={"type": "object"})
    assert raw["ok"], raw
    (call,) = calls()
    argv = call["argv"]
    assert argv[argv.index("-s") + 1] == "read-only"
    assert "workspace-write" not in argv and "danger-full-access" not in argv
    assert not _within(argv[argv.index("-o") + 1], wt)  # -o is outside the project
    assert os.path.realpath(call["cwd"]) == os.path.realpath(str(wt))
    assert call["env"] == {"TESS_DISPATCHED": "1", "TESS_HEADLESS": None, "TESS_CONSULT_DEPTH": "1"}
    # the artifact is installed at the contracted path, a regular file
    ret = wt / "missions/m1/returns/t1.return.json"
    assert not ret.is_symlink() and json.loads(ret.read_text()) == {"from": "child"}


@pytest.mark.parametrize("prog", ["codex", "claude"])
def test_a_symlink_planted_at_the_return_path_mid_run_is_replaced_not_followed(eng, fake_agents,
                                                                               monkeypatch, prog):
    """F3, Cyra's probe: `ln -s ../../../CLAUDE.md missions/m1/returns/t1.return.json`
    planted while the child runs; codex -o (or claude's write) followed it."""
    root, calls = fake_agents
    monkeypatch.setenv("FAKE_AGENT_MODE", "swap-link")
    driver = eng.CodexExecDriver(cwd=root) if prog == "codex" else eng.ClaudeCliDriver(cwd=root)
    try:
        driver.dispatch(_brief(root))
    except eng.RunError:
        pass  # refusing is also fine; overwriting the victim is not
    assert (root / "CLAUDE.md").read_text() == "ORIGINAL\n"
    ret = root / "missions/m1/returns/t1.return.json"
    assert not ret.is_symlink() and json.loads(ret.read_text()) == {"from": "child"}
    assert calls()[0]["prog"] == prog


@pytest.mark.parametrize("prog", ["codex", "claude"])
def test_a_returns_folder_swapped_for_a_symlink_is_refused(eng, fake_agents, monkeypatch, tmp_path, prog):
    root, _calls = fake_agents
    victim_dir = root / ".claude" / "hooks"
    victim_dir.mkdir(parents=True)
    monkeypatch.setenv("FAKE_AGENT_MODE", "swap-dir")
    monkeypatch.setenv("FAKE_AGENT_VICTIM_DIR", str(victim_dir))
    driver = eng.CodexExecDriver(cwd=root) if prog == "codex" else eng.ClaudeCliDriver(cwd=root)
    with pytest.raises(eng.RunError, match="symlink"):
        driver.dispatch(_brief(root))
    assert list(victim_dir.iterdir()) == []


def test_a_codex_output_file_that_is_a_symlink_is_refused(eng, fake_agents, monkeypatch, tmp_path):
    root, _calls = fake_agents
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET\n")
    monkeypatch.setenv("FAKE_AGENT_MODE", "o-symlink")
    monkeypatch.setenv("FAKE_AGENT_VICTIM", str(secret))
    with pytest.raises(eng.RunError, match="symlink"):
        eng.CodexExecDriver(cwd=root).dispatch(_brief(root))
    assert not (root / "missions/m1/returns/t1.return.json").exists()
    assert secret.read_text() == "SECRET\n"


def test_the_private_folder_is_removed_and_never_inside_the_project(eng, fake_agents):
    root, calls = fake_agents
    eng.CodexExecDriver(cwd=root).dispatch(_brief(root), output_schema={"type": "object"})
    argv = calls()[0]["argv"]
    out = argv[argv.index("-o") + 1]
    schema = argv[argv.index("--output-schema") + 1]
    assert os.path.dirname(out) == os.path.dirname(schema)
    assert not os.path.exists(os.path.dirname(out))  # cleaned up
    assert not _within(out, root)


def test_a_temp_folder_inside_the_project_is_refused(eng, fake_agents, monkeypatch):
    root, calls = fake_agents
    inside = root / "tmp"
    inside.mkdir()
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(inside))
    with pytest.raises(eng.RunError, match="inside the project"):
        eng.CodexExecDriver(cwd=root).dispatch(_brief(root))
    assert calls() == []


@pytest.mark.parametrize("depth", ["1", "3", "abc"])
@pytest.mark.parametrize("name", ["codex", "claude"])
def test_tessctl_run_refuses_to_dispatch_inside_a_peer_call(eng, fake_agents, monkeypatch, depth, name):
    """F2: tessctl's own check, for a call the gate did not see."""
    root, calls = fake_agents
    monkeypatch.setenv("TESS_CONSULT_DEPTH", depth)
    driver = eng.CodexExecDriver(cwd=root) if name == "codex" else eng.ClaudeCliDriver(cwd=root)
    with pytest.raises(eng.RunError, match="peer call"):
        driver.dispatch(_brief(root))

    class Args:
        driver = name
        timeout = None
        fake_script = None

    with pytest.raises(eng.RunError, match="peer call"):
        eng._run_build_driver(Args(), root)
    Args.driver = "fake"
    assert isinstance(eng._run_build_driver(Args(), root), eng.FakeDriver)
    assert calls() == []


def test_tessctl_run_process_refuses_inside_a_peer_call(fake_agents, tmp_path):
    root, calls = fake_agents
    env = {**os.environ, "TESS_CONSULT_DEPTH": "1", "TESS_ROOT": str(REPO)}
    r = subprocess.run([sys.executable, "-I", "-B", str(TESSCTL), "run", "--driver", "codex",
                        str(tmp_path / "plan.json")], cwd=str(REPO), capture_output=True, text=True,
                       env=env, timeout=120, stdin=subprocess.DEVNULL)
    assert r.returncode != 0
    assert "peer call" in (r.stderr + r.stdout)
    assert calls() == []


def test_dispatched_children_keep_brain_hooks_and_quiet_the_dispatch_guard(eng, monkeypatch):
    monkeypatch.delenv("TESS_CONSULT_DEPTH", raising=False)
    monkeypatch.setenv("TESS_HEADLESS", "1")
    env = eng._run_child_env()
    assert env["TESS_DISPATCHED"] == "1" and env["TESS_CONSULT_DEPTH"] == "1"
    assert "TESS_HEADLESS" not in env
    # the brain hooks are not silenced by TESS_DISPATCHED
    sys.path.insert(0, str(REPO / "scripts" / "brain"))
    try:
        from brainlib import config as brain_config
    finally:
        sys.path.pop(0)
    monkeypatch.delenv("TESS_HEADLESS", raising=False)
    monkeypatch.delenv("TESS_BRAIN_QUIET", raising=False)
    monkeypatch.setenv("TESS_DISPATCHED", "1")
    assert brain_config.quiet_env() is False
    # the dispatch guard stays quiet for a dispatched child
    if POSIX and shutil.which("bash"):
        hook = REPO / ".claude" / "hooks" / "dispatch-guard.sh"
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "npm install"}})
        base = {k: v for k, v in os.environ.items()
                if k not in ("TESS_HEADLESS", "TESS_NO_SUBAGENTS", "TESS_DISPATCHED")}
        base.update(CLAUDE_PROJECT_DIR=str(REPO), TESS_LOCK_DIR=str(Path(os.environ["HOME"]) / "locks"))
        loud = subprocess.run(["bash", str(hook)], input=payload, capture_output=True, text=True,
                              env=base, timeout=60)
        quiet = subprocess.run(["bash", str(hook)], input=payload, capture_output=True, text=True,
                               env={**base, "TESS_DISPATCHED": "1"}, timeout=60)
        assert quiet.stdout.strip() == ""
        assert loud.stdout.strip() != ""


def test_safe_write_and_unlink_never_follow_links(eng, tmp_path):
    if not POSIX:
        pytest.skip("POSIX symlinks")
    root = tmp_path / "r"
    (root / "missions" / "m1" / "returns").mkdir(parents=True)
    victim = root / "CLAUDE.md"
    victim.write_text("ORIGINAL\n")
    ret = root / "missions/m1/returns/t1.return.json"
    ret.symlink_to("../../../CLAUDE.md")
    eng._run_safe_write(root, "missions/m1/returns/t1.return.json", b"{}")
    assert victim.read_text() == "ORIGINAL\n" and not ret.is_symlink() and ret.read_text() == "{}"
    ret.unlink()
    ret.symlink_to("../../../CLAUDE.md")
    assert eng._run_safe_unlink(root, "missions/m1/returns/t1.return.json") is True
    assert victim.exists() and not os.path.lexists(ret)
    # escapes are refused before the filesystem is touched
    for bad in ("../x", "missions/../CLAUDE.md", "/etc/passwd", "missions", "kb/x.json"):
        with pytest.raises(eng.RunError, match="escapes"):
            eng._run_safe_write(root, bad, b"x")
    # the stale-artifact clear removes a planted link instead of refusing the run
    ret.symlink_to("../../../CLAUDE.md")
    eng._run_clear_stale_artifact(root, "missions/m1/returns/t1.return.json")
    assert not os.path.lexists(ret) and victim.read_text() == "ORIGINAL\n"


def test_install_refuses_non_regular_and_oversized_files(eng, tmp_path, monkeypatch):
    if not POSIX:
        pytest.skip("POSIX fifos")
    root = tmp_path / "r"
    (root / "missions").mkdir(parents=True)
    fifo = tmp_path / "p"
    os.mkfifo(str(fifo))
    with pytest.raises(eng.RunError, match="non-regular"):
        eng._run_install_artifact(root, fifo, "missions/m1/returns/t.json")
    assert eng._run_install_artifact(root, tmp_path / "missing", "missions/m1/returns/t.json") is False
    big = tmp_path / "big"
    big.write_bytes(b"x" * 11)
    monkeypatch.setattr(eng, "RUN_ARTIFACT_MAX_BYTES", 10)
    with pytest.raises(eng.RunError, match="larger"):
        eng._run_install_artifact(root, big, "missions/m1/returns/t.json")
