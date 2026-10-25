"""1.0.0: Cyra's security review of f8fb9c6, the gate items (a, c, d).

a. Glob semantics assumed the shells' default options. Claude Code runs an
   agent's commands with the operator's own shell options, which Tess cannot
   see. Where a glob may reach a protected path, a control file or the key
   folder, it is now read under the worst case:
     * a glob step matches dot names (zsh GLOB_DOTS, bash dotglob), and `**`
       / `***` walk into dot folders;
     * an unquoted `^`, `~` or `#` is a wildcard (zsh EXTENDED_GLOB), read as
       a plain glob that matches every name either reading names;
     * zsh's `<N-M>` number range asks (it is two redirections in bash);
     * `(...)` patterns already asked (unchanged, pinned here).
   A wildcard that can end on a control name only through a dot match is
   decided from the listing, so everyday writes into ordinary folders keep
   working.
c. The gate's task-start handler (`tess-gate.py --task-start`) reset the
   three-agents-per-task budget when an agent ran it from its shell. It now
   goes through the brain hook handler's rule (B-2): refused when a word names
   the gate and a later word is the flag, asked when a program is handed text
   naming the handler.
d. U1's "nothing earlier in the command changes files" did not count process
   substitution. `<(...)`, `>(...)` and zsh `=(...)` now count, wherever they
   stand, for U1 and for the U2 key-folder check.

Decisions: (claude default, claude acceptEdits, codex). The attack rows are
allowed by f8fb9c6's gate and refused (or asked) here; the everyday rows are
allowed by both.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_v1_n1_n3 import ALLOW, ASK, DENY, G, GATE, REPO, SLASHFREE

MODES = (("claude", "default"), ("claude", "acceptEdits"), ("codex", None))


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """A Tess instance copy (lock, pins, hooks, brain) with ordinary project
    folders, plus a fake home with user-level control files."""
    tmp = tmp_path_factory.mktemp("cyraf8")
    root, home = tmp / "proj", tmp / "home"
    for rel in (".tess/tess.lock", ".tess/core/pinned-scripts.sha256", "tessctl",
                "tess.manifest.json", "conductor/guardrails.md", "CLAUDE.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    for tree in (".claude/hooks", "scripts/brain", ".tess/bin", ".tess/vendor"):
        shutil.copytree(REPO / tree, root / tree, ignore=shutil.ignore_patterns("__pycache__"))
    (root / ".claude" / "settings.json").write_text("{}\n")
    for d in ("src/a/__pycache__", "web/dist", "web/node_modules/.bin", "many/aa"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "src" / "a.py").write_text("print(1)\n")
    (root / "src" / ".env.example").write_text("X=1\n")
    (root / "src" / "notes~").write_text("old\n")
    (root / ".git" / "hooks").mkdir(parents=True)
    (root / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\nexit 0\n")
    (home / ".config").mkdir(parents=True)
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("{}\n")
    (home / "Documents").mkdir()
    return root, home


@pytest.fixture(autouse=True)
def _env(world, monkeypatch):
    monkeypatch.setenv("HOME", str(world[1]))
    for k in ("XDG_CONFIG_HOME", "TESS_BRAIN_PROVENANCE_DIR", "GIT_DIR", "GIT_WORK_TREE",
              "TESS_CONSULT_DEPTH", "CDPATH", "TESS_HEADLESS", "TESS_DISPATCHED", *SLASHFREE):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(G, "_ancestry", lambda limit=40: ["python3", "zsh", "login"], raising=False)
    monkeypatch.setattr(G, "_os_home", lambda: str(world[1]), raising=False)
    getattr(G, "_CONTROL_CACHE", {}).clear()


def _all(world, cmd, cwd=""):
    root = world[0]
    out = []
    for rt, mode in MODES:
        data = {"tool_name": "Bash", "cwd": str(root / cwd), "tool_input": {"command": cmd}}
        if rt == "codex":
            data["turn_id"] = "t"
        else:
            data["permission_mode"] = mode
        d = G.decide(data, root, rt)
        assert "safety check errored" not in (d[1] or ""), (cmd, d[1])
        out.append(d[0] or "allow")
    return tuple(out)


# ============================================================== a. dot names
# A glob step that reaches a protected or control path only by matching a dot
# name: f8fb9c6 allowed every one of these.
A_DOT_REFUSED = [
    "rm -rf */hooks",
    "rm -f */hooks/tess-gate.py",
    "rm -f */hooks/run-pinned.py",
    "cp src/a.py */hooks/tess-gate.py",
    "mv */hooks /tmp/away",
    "rm -rf **/hooks",
    "rm -f **/tess-gate.py",
    "rm -f **/run-pinned.py",
    "chmod 000 **/*.sh",
    "rm -rf ?claude",
    "rm -rf [.]claude/hooks",
    "rm -rf *tess/core",
    "rm -rf *tess/bin",
    "rm -f ./*/*/pinned-scripts.sha256",
    # Reid's f8 review (M1): `**` spellings that reach .claude/ or .git/hooks
    "rm -f **/settings.json",
    "rm -f */settings.json",
    "chmod -R 777 **/hooks",
    "rm -f **/hooks/pre-commit",
    "rm -f */hooks/pre-commit",
]


@pytest.mark.parametrize("cmd", A_DOT_REFUSED)
def test_a_a_glob_that_matches_a_dot_name_reaches_protected_files(world, cmd):
    assert _all(world, cmd) == DENY


def test_a_a_recursive_glob_after_a_change_still_counts_dot_folders(world):
    assert _all(world, "touch x.txt && rm -rf **/hooks") in (ASK, DENY)


# Home: a glob step that can end on a user-level control folder only by a dot match.
def test_a_a_home_glob_is_decided_from_the_listing(world):
    home = world[1]
    assert _all(world, f"rm -rf {home}/*") in (ASK, DENY)          # ~/.claude is in the listing
    assert _all(world, f"cp src/a.py {home}/*/settings.json") in (ASK, DENY)
    assert _all(world, f"rm -rf {home}/Doc*") == ALLOW              # no control name listed


def test_a_a_recursive_reader_of_a_glob_over_the_home_reaches_the_key_folder(world):
    assert _all(world, "grep -r x ~/*") == DENY       # ~/.config is above the key folder
    assert _all(world, "grep -r x ~/.c*") == DENY
    assert _all(world, "ls ~/*") == ALLOW             # not recursive: only names


# =================================================== a. extended glob (zsh EXTENDED_GLOB)
A_EXT_REFUSED = [
    "rm -rf ^src",                 # negation: everything but src, CLAUDE.md included
    "rm -rf conductor/^x",
    "rm -f conductor/guard^x",
    "rm -rf *~src",                # exclusion: `*` minus src
    "rm -f *~",
    "rm -f CLAUDE.md~x",
    "rm -f CLAUDE.md#",            # repetition: `d#` is zero or more `d`
    "rm -f CLAUDE.m#d",
    "rm -rf .claude/hook#s",
    "rm -rf .^x/hooks",
    "X='^src'; rm -rf $X",         # an unquoted value is a pattern (GLOB_SUBST, the worst case)
]


@pytest.mark.parametrize("cmd", A_EXT_REFUSED)
def test_a_extended_glob_characters_are_wildcards(world, cmd):
    assert _all(world, cmd) == DENY


A_ASKS = [
    "rm -f CLAUDE<->.md",          # zsh number range; bash reads two redirections
    "rm -f <->",
    "rm -f (CLAUDE|x).md",         # alternatives (already asked before; pinned)
    "rm -f @(CLAUDE).md",          # ksh-style / bash extglob
    "rm -rf !(src)",
    "rm -rf src/*(D)",             # zsh glob qualifier
]


@pytest.mark.parametrize("cmd", A_ASKS)
def test_a_patterns_tess_does_not_read_ask(world, cmd):
    assert _all(world, cmd) in (ASK, DENY)


# Quoted characters stay literal; ordinary writes keep working.
A_EVERYDAY = [
    "rm -rf node_modules",
    "rm -rf web/node_modules",
    "rm -rf src/*",
    "rm -rf web/dist/*",
    "rm -f src/*~",
    "rm -f 'a~b' \"^src\" 'CLAUDE.md#'",
    "rm -rf **/__pycache__",
    "rm -rf **/node_modules",
    "rm -f **/*.pyc",
    "ls *",
    "ls -a src/*",
    "grep -rn print src/*",
    "git log --oneline HEAD~3",
    "git diff HEAD^ -- src",
    "touch notes#1.txt",
    "find . -name '*.pyc' -delete",
]


@pytest.mark.parametrize("cmd", A_EVERYDAY)
def test_a_everyday_commands_are_unchanged(world, cmd):
    assert _all(world, cmd) == ALLOW


def test_a_ext_glob_reading_matches_every_name_either_reading_names():
    """The plain glob _ext_glob builds matches the extended reading (zsh) and
    the plain reading (the characters as text)."""
    import fnmatch

    def m(pat, name):
        return fnmatch.fnmatchcase(name, G._shell_glob(G._ext_glob(G._ext_mark(pat))))

    cases = [("^src", ["CLAUDE.md", "^src", "src"]), ("*~src", ["CLAUDE.md", "a~src"]),
             ("CLAUDE.md#", ["CLAUDE.m", "CLAUDE.md", "CLAUDE.mdd", "CLAUDE.md#"]),
             ("CLAUDE.m#d", ["CLAUDE.d", "CLAUDE.md", "CLAUDE.m#d"]),
             ("a~b", ["a", "a~b"]), ("[^a]x", ["bx"]), ("x[#]", ["x#"]), ("guard^x", ["guardrails.md"])]
    for pat, names in cases:
        for n in names:
            assert m(pat, n), (pat, n)
    # `L~R` with a `/` in R: the plain reading is deeper; `L*/**` covers both
    assert G._ext_glob(G._ext_mark("a~b/c")) == "a*/**"
    # quoted characters (not marked) stay literal
    assert G._ext_glob("^src") == "^src"


def test_a_dot_names_never_match_dot_and_dotdot():
    assert not G._seg_match(".", "*") and not G._seg_match("..", "*")
    assert G._seg_match(".claude", "*") and G._seg_match(".claude", "?claude")
    assert G._parts_match([".claude", "hooks"], ["**", "hooks"]) == "full"


# ====================================================== c. the task-start handler
C_DENIED = [
    "echo '{\"session_id\": \"s1\"}' | python3 .claude/hooks/tess-gate.py --runtime claude --task-start",
    "python3 .claude/hooks/tess-gate.py --task-start < p.json",
    "python3 -I -B .claude/hooks/tess-gate.py --runtime claude --task-start",
    "echo '{}' | python3 -I -B .claude/hooks/run-pinned.py --on-fail warn -- "
    ".claude/hooks/tess-gate.py --runtime claude --task-start",
    "bash -c 'python3 .claude/hooks/tess-gate.py --task-start'",
    "cd .claude/hooks && python3 tess-gate.py --task-start",
    "myinterp .claude/hooks/tess-gate.py --task-start",
    "find . -maxdepth 0 -exec python3 .claude/hooks/tess-gate.py --task-start \\;",
]


@pytest.mark.parametrize("cmd", C_DENIED)
def test_c_an_agent_shell_never_runs_the_task_start_handler(world, cmd):
    assert _all(world, cmd) == DENY


C_UNSHOWN = [
    "python3 -c 'import runpy, sys; sys.argv = [\"g\", \"--task-start\"]; "
    "runpy.run_path(\".claude/hooks/tess-gate.py\")'",
    "python3 -c 'import importlib.util as u; s = u.spec_from_file_location(\"g\", "
    "\".claude/hooks/tess-gate.py\"); g = u.module_from_spec(s); s.loader.exec_module(g); "
    "g.task_start({\"session_id\": \"s1\"})'",
    "python3 -c 'getattr(g, \"task_\" + \"start\")'",
    "S=--task-start; python3 .claude/hooks/tess-gate.py \"$S\"",
    "echo --task-start | xargs python3 .claude/hooks/tess-gate.py",
]


@pytest.mark.parametrize("cmd", C_UNSHOWN)
def test_c_text_naming_the_task_start_handler_asks(world, cmd):
    assert _all(world, cmd) in (ASK, DENY)


C_NEIGHBOURS = [
    "grep -n task_start .claude/hooks/tess-gate.py",
    "grep -n -- --task-start .claude/settings.json",
    "cat .claude/hooks/tess-gate.py | head -3",
    "python3 -m pytest -q tests/test_v1_0_0_peer_consult_budget.py",
]


@pytest.mark.parametrize("cmd", C_NEIGHBOURS)
def test_c_neighbours_are_unchanged(world, cmd):
    assert _all(world, cmd) == ALLOW


# a769130 review (Reid M5): the hook is run as its own process with its input
# on a pipe, as Claude Code runs it, and the budget folder is redirected to a
# temporary home inside that process (the gate finds the home from the OS user
# record, not $HOME, so HOME alone would reach the real ~/.config/tess).
_HOOK_RUNNER = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location("tess_gate_hook_under_test", sys.argv[1])
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
gate._os_home = lambda: sys.argv[2]
sys.exit(gate.main(["--runtime", "claude", "--task-start"]))
"""


def _run_task_start_hook(tmp_path, home, payload):
    runner = tmp_path / "hook_runner.py"
    runner.write_text(_HOOK_RUNNER)
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CODEX_THREAD_ID")}
    env["HOME"] = str(home)
    return subprocess.run([sys.executable, "-I", "-B", str(runner), str(GATE), str(home)],
                          input=json.dumps(payload), capture_output=True, text=True, env=env,
                          cwd=str(tmp_path))


def _spent_budget(home, session):
    import hashlib
    d = home / ".config" / "tess" / "agent-budget"
    d.mkdir(parents=True, mode=0o700)
    f = d / (hashlib.sha256(session.encode()).hexdigest()[:32] + ".json")
    f.write_text(json.dumps({"task": "session", "used": 3}) + "\n")
    f.chmod(0o600)
    return f


_PROMPT = {"hook_event_name": "UserPromptSubmit", "prompt": "next task", "session_id": "s-f8",
           "cwd": "/x", "transcript_path": "/x/t.jsonl"}


def test_c_the_runtime_hook_itself_still_marks_a_task(world, tmp_path):
    """The UserPromptSubmit hook (run by Claude Code, not through the gate)
    prints nothing, never blocks, and starts a fresh budget for a payload
    shaped as Claude Code sends it."""
    home = tmp_path / "h"
    counter = _spent_budget(home, "s-f8")
    r = _run_task_start_hook(tmp_path, home, _PROMPT)
    assert r.returncode == 0 and r.stdout == "" and "no new task marked" not in r.stderr, r.stderr
    doc = json.loads(counter.read_text())
    assert doc["used"] == 0 and doc["task"].startswith("prompt:")


def test_c_a_payload_the_hook_refuses_keeps_the_spent_budget(world, tmp_path):
    home = tmp_path / "h"
    counter = _spent_budget(home, "s-f8")
    r = _run_task_start_hook(tmp_path, home, {"session_id": "s-f8"})
    assert r.returncode == 0 and r.stdout == "" and "no new task marked" in r.stderr
    assert json.loads(counter.read_text())["used"] == 3


def test_c_the_marked_task_really_resets_what_the_gate_counts(world, tmp_path, monkeypatch):
    """After the real hook marks a task, the gate allows agents again."""
    home = tmp_path / "h"
    _spent_budget(home, "s-f8")
    monkeypatch.setattr(G, "_os_home", lambda: str(home), raising=False)
    data = {"tool_name": "Bash", "cwd": str(world[0]), "session_id": "s-f8", "permission_mode": "default",
            "tool_input": {"command": "codex exec -s read-only 'review src'"}}
    assert G.decide(data, world[0], "claude")[0] == "ask"           # the budget is spent
    _run_task_start_hook(tmp_path, home, _PROMPT)
    assert (G.decide(data, world[0], "claude")[0] or "allow") == "allow"


# ================================================ d. process substitution and U1
D_ASKS = [
    "cat <(touch x) && rm -rf **/dist",
    "rm -rf **/dist <(true)",
    "rm -rf **/dist >(cat)",
    "diff <(ls) <(ls src) ; rm -rf **/__pycache__",
    "rm -f **/*.pyc =(true)",
]


@pytest.mark.parametrize("cmd", D_ASKS)
def test_d_process_substitution_counts_as_a_change_before_the_glob(world, cmd):
    assert _all(world, cmd) in (ASK, DENY)


def test_d_a_link_made_by_process_substitution_is_never_allowed(world):
    assert _all(world, "rm -rf ***/hooks <(ln -s .claude zz)") in (ASK, DENY)
    assert _all(world, "cat <(ln -s .claude zz) && rm -rf **/zz/hooks") in (ASK, DENY)


def test_d_u1_quiet_reads_process_substitution():
    ctx = G._Ctx("rm -rf **/dist <(true)")
    assert not G._u1_quiet(ctx)
    assert G._u1_quiet(G._Ctx("rm -rf **/dist"))


def test_d_without_process_substitution_u1_still_allows(world):
    assert _all(world, "rm -rf **/dist") == ALLOW
    assert _all(world, "rm -rf **/__pycache__ && ls") == ALLOW


# ============================== f. (Reid f8 review, L1) the budget counter's lock wait
def test_f_a_held_budget_lock_ends_in_the_gates_own_ask_quickly(world, tmp_path, monkeypatch):
    """Another call holding the counter's lock: the wait is bounded (on
    f8fb9c6 it blocked until the launcher's 100 s deadline) and ends in the
    gate's own ask, which Codex turns into a refusal."""
    import fcntl
    import time
    home = tmp_path / "bh"
    home.mkdir()
    monkeypatch.setattr(G, "_os_home", lambda: str(home), raising=False)
    monkeypatch.setattr(G, "AGENT_BUDGET_LOCK_WAIT", 0.5, raising=False)
    path = G._budget_file("sess-f-lock")
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    holder = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        v = G.Verdict()
        t0 = time.monotonic()
        G._budget_charge({"session_id": "sess-f-lock"}, False, 1, v)
        took = time.monotonic() - t0
        assert v.level == G.ASK and took < 5, (v.reasons, took)
        assert any("agent budget" in r for r in v.reasons)
        # inside the gate's time budget: an expired deadline stops the wait at once
        G._STATE["deadline"] = time.monotonic() - 1
        try:
            with pytest.raises(G._GateTimeout):
                G._budget_open(path)
        finally:
            G._STATE["deadline"] = None
    finally:
        os.close(holder)
    # with the lock free, counting works as before
    v = G.Verdict()
    G._budget_charge({"session_id": "sess-f-lock"}, False, 1, v)
    assert v.level == G.ALLOW


def test_f_the_lock_wait_is_far_below_the_gate_and_launcher_deadlines():
    assert 0 < G.AGENT_BUDGET_LOCK_WAIT < G.GATE_BUDGET
