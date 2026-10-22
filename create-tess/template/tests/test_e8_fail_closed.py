"""E8: every way a gate hook invocation can end produces an explicit decision.

Claude Code and Codex both treat a PreToolUse hook that prints nothing and exits with
anything other than 0 or 2, that dies on a signal, or that runs past the host's hook
timeout as "no decision", and the tool call goes ahead. These tests hold the fix
(kb: 2026-10-22 Quinn E8 report, section 6):

  T2  the E8 precondition fails as an isolation error, never as "the gate allowed it";
  T3  launcher, block mode: a child that exits 1, is killed, segfaults or hangs past the
      deadline ends in exit 2, nothing on stdout, a "TESS GATE: blocked" line on stderr;
      and the same through the real hook commands of both runtimes;
  T4  launcher, warn mode: the same children's return codes pass through unchanged;
  T5  the gate, both runtimes: SIGTERM, SIGINT or SIGHUP while it waits on stdin ends in
      rc 0 and one deny;
  T6  the gate: an edit or MCP payload whose loop outruns the budget ends in the budget's
      decision (Codex deny, Claude ask) within GATE_BUDGET + 5 s;
  T7  GATE_BUDGET < BLOCK_DEADLINE < every host timeout of a block-mode hook;
  plus static guards: every loop in the gate checks the budget unless it is bounded,
  and the iterative _strings() keeps the old document order.
T1 is tests/test_e8_suite_os_home_consistency.py; T8 is the xdist step in .github/workflows/ci.yml.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import random
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_codex_gate import HOOK_CMD, proj  # noqa: F401 -- fixture

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / ".claude" / "hooks" / "tess-gate.py"
LAUNCHER = REPO / ".claude" / "hooks" / "run-pinned.py"
POSIX = os.name == "posix"


def _gate_mod():
    sys.dont_write_bytecode = True  # never leave __pycache__ in .claude/hooks
    spec = importlib.util.spec_from_file_location("tess_gate_e8", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _claude_gate_cmd() -> str:
    data = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    for entry in data["hooks"]["PreToolUse"]:
        for hook in entry["hooks"]:
            if "tess-gate.py" in hook["command"]:
                return hook["command"]
    raise AssertionError("no tess-gate.py PreToolUse hook in .claude/settings.json")


# ------------------------------------------------------------------ T2

def test_t2_home_mismatch_is_an_isolation_error_not_an_allow(tmp_path):
    from test_v1_gate_git_routes import _assert_same_os_home
    elsewhere = str(tmp_path / "another-home" / ".config" / "tess" / "projects" / "x" / "anchor.json")
    with pytest.raises(AssertionError, match="test isolation error"):
        _assert_same_os_home(tmp_path, elsewhere)


# ------------------------------------------------------------------ T3 / T4: the launcher

_CHILDREN = {
    "exit1": "import sys; sys.exit(1)",
    "sigkill": "import os, signal; os.kill(os.getpid(), signal.SIGKILL)",
    "sigsegv": "import os, signal; os.kill(os.getpid(), signal.SIGSEGV)",
    "hang": "import time; time.sleep(60)",
    "decides": "print('{}')",
    "blocks": "import sys; sys.exit(2)",
    "slow": "import time; time.sleep(1.5); print('{}')",
}

# Runs one child through the launcher's own _guarded/_spawn, with BLOCK_DEADLINE patched.
_LAUNCH = r"""
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("run_pinned_e8", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
mode, deadline, child, after = sys.argv[2], float(sys.argv[3]), sys.argv[4], float(sys.argv[5])
m.BLOCK_DEADLINE, m._STARTED = deadline, time.monotonic()
rc = m._guarded(mode == "block", "child.py",
                lambda: m._spawn([sys.executable, "-I", "-B", "-c", child], mode, "child.py"))
time.sleep(after)  # a deadline that passes after the child decided must not change the result
sys.exit(rc)
"""


def _launch(mode: str, kind: str, deadline: float = 30.0, after: float = 0.0):
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, "-I", "-B", "-c", _LAUNCH, str(LAUNCHER), mode, str(deadline),
                        _CHILDREN[kind], str(after)], capture_output=True, text=True, timeout=120)
    return r, time.monotonic() - t0


@pytest.mark.skipif(not POSIX, reason="POSIX signals")
@pytest.mark.parametrize("kind", ["exit1", "sigkill", "sigsegv"])
def test_t3_block_mode_child_that_dies_is_a_block(kind):
    r, _ = _launch("block", kind)
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert r.stdout == ""
    assert r.stderr.startswith("TESS GATE: blocked"), r.stderr


@pytest.mark.skipif(not POSIX, reason="POSIX signals")
def test_t3_block_mode_child_past_the_deadline_is_a_block():
    r, took = _launch("block", "hang", deadline=2.0)
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert r.stdout == ""
    assert r.stderr.startswith("TESS GATE: blocked"), r.stderr
    assert "did not decide within" in r.stderr
    assert took < 2.0 + 10, took


@pytest.mark.parametrize("kind,rc", [("decides", 0), ("blocks", 2)])
def test_t3_block_mode_decisions_pass_through_and_survive_the_deadline(kind, rc):
    r, _ = _launch("block", kind, deadline=1.5, after=2.5)
    assert r.returncode == rc, (r.returncode, r.stderr)
    assert "TESS GATE: blocked" not in r.stderr


@pytest.mark.skipif(not POSIX, reason="POSIX signals")
@pytest.mark.parametrize("kind,rc", [("exit1", 1), ("sigkill", -signal.SIGKILL % 256),
                                     ("sigsegv", -signal.SIGSEGV % 256), ("decides", 0), ("blocks", 2)])
def test_t4_warn_mode_passes_the_return_code_through(kind, rc):
    r, _ = _launch("warn", kind)
    assert r.returncode == rc, (r.returncode, r.stderr)
    assert "TESS GATE: blocked" not in r.stderr


@pytest.mark.skipif(not POSIX, reason="POSIX signals")
def test_t4_warn_mode_has_no_deadline():
    r, took = _launch("warn", "slow", deadline=0.2, after=0.0)
    assert r.returncode == 0 and r.stdout.strip() == "{}", (r.returncode, r.stdout, r.stderr)


# ------------------------------------------------------------------ the real hooks, both runtimes

def _start_hook(runtime: str, root: Path) -> subprocess.Popen:
    if runtime == "codex":
        cmd = HOOK_CMD
        env = {"HOME": str(root / "home"), "PATH": os.environ["PATH"], "TESS_GATE_LOG": os.devnull}
    else:
        cmd = _claude_gate_cmd()
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "TESS_GATE_LOG": os.devnull}
    return subprocess.Popen(["sh", "-c", cmd], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, cwd=str(root), env=env,
                            preexec_fn=_default_stop_signals)


def _default_stop_signals():
    # A suite started with nohup or in a background job inherits SIGHUP/SIGINT as ignored, and
    # an ignored signal never reaches the gate: T5 would then pass without testing anything.
    for name in ("SIGTERM", "SIGHUP", "SIGINT"):
        signal.signal(getattr(signal, name), signal.SIG_DFL)


def _processes() -> dict:
    out = subprocess.run(["ps", "-A", "-ww", "-o", "pid=,ppid=,stat=,command="], capture_output=True,
                         text=True, check=True).stdout
    procs = {}
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4 and parts[0].isdigit() and parts[1].isdigit():
            procs[int(parts[0])] = (int(parts[1]), parts[2], parts[3])
    return procs


def _gate_waiting_on_stdin(top: int, timeout: float = 60.0) -> int:
    """The PID of the gate interpreter started under `top` (one of OUR processes), once it
    has loaded and sits waiting for its input: sleeping for several samples in a row."""
    end, quiet = time.monotonic() + timeout, 0
    while time.monotonic() < end:
        procs = _processes()
        mine, todo = set(), [top]
        while todo:
            p = todo.pop()
            mine.add(p)
            todo += [c for c, (pp, _s, _c) in procs.items() if pp == p and c not in mine]
        gate = [p for p in mine if p in procs and "verified-source.py" in procs[p][2]
                and "tess-gate.py" in procs[p][2]]
        if gate and procs[gate[0]][1].startswith("S"):
            quiet += 1
            if quiet >= 8:
                return gate[0]
        else:
            quiet = 0
        time.sleep(0.1)
    raise AssertionError("the gate process never reached its stdin read")


@pytest.mark.skipif(not POSIX, reason="POSIX signals")
@pytest.mark.parametrize("runtime", ["codex", "claude"])
@pytest.mark.parametrize("sig", ["SIGTERM", "SIGINT", "SIGHUP"])
def test_t5_stop_signal_while_reading_stdin_is_a_deny(proj, runtime, sig):
    p = _start_hook(runtime, proj)
    try:
        gate = _gate_waiting_on_stdin(p.pid)
        os.kill(gate, getattr(signal, sig))  # the gate process this test started
        out, err = p.communicate(timeout=60)
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
    assert p.returncode == 0, (p.returncode, err)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1, out
    hso = json.loads(lines[0])["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny", hso


@pytest.mark.skipif(not POSIX, reason="POSIX signals")
@pytest.mark.parametrize("runtime", ["codex", "claude"])
def test_t3_real_hook_gate_killed_is_a_block(proj, runtime):
    p = _start_hook(runtime, proj)
    try:
        gate = _gate_waiting_on_stdin(p.pid)
        os.kill(gate, signal.SIGKILL)  # the gate process this test started
        out, err = p.communicate(timeout=60)
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
    assert p.returncode == 2, (p.returncode, err)
    assert out == ""
    assert "TESS GATE: blocked" in err, err


# ------------------------------------------------------------------ T6: the budget covers every loop

# Runs the gate's own entry point with GATE_BUDGET patched, so CI stays fast.
_GATE_MAIN = r"""
import importlib.util, sys
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("tess_gate_e8_main", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.GATE_BUDGET = float(sys.argv[2])
sys.exit(m._backstop(["--runtime", sys.argv[3]]))
"""
_BUDGET = 1.0
_MANY = 60000  # far more paths than one budget can check (each one is a path resolution)


def _gate_main(root: Path, runtime: str, payload: dict):
    env = {"HOME": str(root / "home"), "PATH": os.environ["PATH"], "TESS_GATE_LOG": os.devnull,
           "CLAUDE_PROJECT_DIR": str(root)}
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, "-I", "-B", "-c", _GATE_MAIN, str(GATE), str(_BUDGET), runtime],
                       input=json.dumps(payload), capture_output=True, text=True, cwd=str(root), env=env,
                       timeout=300)
    took = time.monotonic() - t0
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"], took


def _patch(n: int) -> str:
    return "*** Begin Patch\n" + "".join(f"*** Add File: src/e8/f{i}.txt\n+x\n" for i in range(n)) \
        + "*** End Patch\n"


@pytest.mark.parametrize("runtime,payload,want", [
    ("codex", {"turn_id": "t", "tool_name": "apply_patch", "tool_input": {"command": _patch(_MANY)}}, "deny"),
    ("claude", {"permission_mode": "default", "tool_name": "Write",
                "tool_input": {"file_path": "src/e8/notes.txt", "content": _patch(_MANY)}}, "ask"),
    ("codex", {"turn_id": "t", "tool_name": "mcp__fs__stat",
               "tool_input": {"paths": [f"src/e8/f{i}.txt" for i in range(_MANY)]}}, "deny"),
    ("claude", {"permission_mode": "default", "tool_name": "mcp__fs__stat",
                "tool_input": {"paths": [f"src/e8/f{i}.txt" for i in range(_MANY)]}}, "ask"),
], ids=["codex-edit", "claude-edit", "codex-mcp", "claude-mcp"])
def test_t6_large_payload_ends_in_the_budget_decision(proj, runtime, payload, want):
    payload = {"session_id": "s", "hook_event_name": "PreToolUse", "cwd": str(proj), **payload}
    out, took = _gate_main(proj, runtime, payload)
    assert out["permissionDecision"] == want, out
    assert "could not finish checking" in out["permissionDecisionReason"], out
    assert took < _BUDGET + 5, took


# ------------------------------------------------------------------ T7: the wall-clock contract

def _const(path: Path, name: str) -> float:
    m = re.search(rf"^{name} = ([0-9.]+)$", path.read_text(encoding="utf-8"), re.M)
    assert m, f"{name} not found in {path}"
    return float(m.group(1))


def _block_mode_host_timeouts() -> list:
    out = []
    data = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    for entries in data["hooks"].values():
        for entry in entries:
            for hook in entry["hooks"]:
                if "--on-fail block" in hook["command"]:
                    # Claude Code's default command-hook timeout is 600 s; the gate sets 120.
                    out.append(("claude", hook["command"][-60:], float(hook.get("timeout", 600))))
    text = (REPO / ".codex" / "config.toml").read_text(encoding="utf-8")
    for block in text.split("[[hooks.")[1:]:
        cmd = re.search(r"^command = (.*)$", block, re.M)
        if cmd and "--on-fail block" in cmd.group(1):
            m = re.search(r"^timeout = ([0-9.]+)$", block, re.M)
            assert m, "a Codex block-mode hook with no explicit timeout"
            out.append(("codex", "config.toml", float(m.group(1))))
    return out


def test_t7_budget_below_deadline_below_every_host_timeout():
    budget, deadline = _const(GATE, "GATE_BUDGET"), _const(LAUNCHER, "BLOCK_DEADLINE")
    hosts = _block_mode_host_timeouts()
    assert any(rt == "codex" for rt, _c, _t in hosts) and any(rt == "claude" for rt, _c, _t in hosts)
    assert budget < deadline, (budget, deadline)
    for rt, where, t in hosts:
        assert deadline < t, (rt, where, deadline, t)


# ------------------------------------------------------------------ static guards

# Loops that need no budget check: a fixed table or a small constant range, or (archive
# listing) a loop inside a broad `except Exception` with its own item limit.
_BOUNDED = {
    "for pattern, desc in mod._PATTERNS:",
    "for pattern, _desc in _scanner(root)._PATTERNS:",
    "for home in _homes():",
    'for name in ("config.toml", "hooks.json", "rules"):',
    'for var, val in (("HOME", home), ("XDG_CONFIG_HOME", xdg)):',
    "for d in _key_dirs():",
    'for kind in ("full", "prefix", "beyond"):',
    'for commenters in ("", "#"):',
    'for k in ("--rebase", "-r"):',
    "for a in ([t, _g.escape(t)] if _g.has_magic(t) else [t]):",
    "for _ in range(8):",
    "for entry in _CONTROL_SUFFIXES:",
    "for o in _OUTPUT_OPTS.get(name, ()):",
    "for _ in range(2):",
    "for info in z.infolist():",
    "for m in tf:",
    'for suffix in (".exe", ".cmd", ".bat", ".ps1"):',
    'for k in ("CLAUDE_CODE_SIMPLE", "CLAUDE_CODE_SAFE_MODE"):',
    'for name in ("CDPATH", "cdpath"):',
    'for k in ("workdir", "cwd", "directory", "working_directory"):',
    'for k in ("file_path", "path", "notebook_path"):',
    "for name in _STOP_SIGNALS:",
}


def _calls_tick(stmts) -> bool:
    todo = list(stmts)
    while todo:
        n = todo.pop()
        if isinstance(n, (ast.FunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_tick":
            return True
        todo.extend(ast.iter_child_nodes(n))
    return False


def test_every_unbounded_gate_loop_checks_the_budget():
    src = GATE.read_text(encoding="utf-8")
    lines = src.splitlines()
    missing = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, (ast.For, ast.While)) and not _calls_tick(n.body):
            head = lines[n.lineno - 1].strip()
            if head not in _BOUNDED:
                missing.append(f"{n.lineno}: {head}")
    assert not missing, "loops with no _tick() (E8: add one, or list the loop as bounded):\n" + \
        "\n".join(missing)


def _strings_old(obj) -> list:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for val in obj.values() for s in _strings_old(val)]
    if isinstance(obj, list):
        return [s for val in obj for s in _strings_old(val)]
    return []


def test_iterative_strings_keeps_document_order():
    gate = _gate_mod()
    rnd = random.Random(8)

    def build(depth):
        k = rnd.random()
        if depth > 5 or k < 0.3:
            return rnd.choice([f"s{rnd.randint(0, 99)}", 1, None, True, 2.5])
        if k < 0.65:
            return [build(depth + 1) for _ in range(rnd.randint(0, 4))]
        return {f"k{i}": build(depth + 1) for i in range(rnd.randint(0, 4))}

    for _ in range(300):
        obj = build(0)
        assert gate._strings(obj) == _strings_old(obj)
    deep = "x"
    for _ in range(500):
        deep = [deep, {"a": "y"}]
    assert gate._strings(deep) == _strings_old(deep)


def test_block_mode_claude_hooks_also_ask_the_host_to_block_on_failure():
    """Defence in depth for what the launcher cannot cover (the launcher itself killed, a host
    timeout): Claude Code >= 2.1.295 blocks the call when such a hook fails. Older versions
    ignore the key and still run the hook (checked on 2.1.290 and 2.1.294, E8 report)."""
    for name in (".claude/settings.json", ".tess/core/settings-core.json"):
        data = json.loads((REPO / name).read_text(encoding="utf-8"))
        hooks = [h for entries in data["hooks"].values() for e in entries for h in e["hooks"]
                 if "--on-fail block" in h["command"]]
        assert len(hooks) >= 2, name
        for h in hooks:
            assert h.get("onFailure") == "block", (name, h["command"][-60:])
