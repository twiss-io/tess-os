"""v1.0.1 (GPT-6 independent review, round 2): isolated engine launches and
native-import rejection.

R3 HIGH: the Claude/Codex gate's push check started `.tess/bin/tessctl`
without `-I`, so Python put `.tess/bin/` first on sys.path and a planted
`.tess/bin/argparse.py` ran inside the hook. Every launch of repo Python code
now uses `-I -B`.

R4 HIGH: `run-pinned.py --closure` hashed only `*.py`. A native extension
(`brainlib/__init__.so`), a sourceless `.pyc`, a `.pth` or a symlink in the
closure was neither rejected nor hashed, and Python prefers an extension
module over the verified source. The launcher now refuses every importable
artifact that is not a pinned `.py`, and runs the target from the bytes it
verified.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_codex_gate import HAS_GIT, _git, _hook, proj  # noqa: F401 — fixture

REPO = Path(__file__).resolve().parent.parent
LAUNCHER = ".claude/hooks/run-pinned.py"


# --- R3: the gate's push check never imports planted engine siblings ---------------------------

def _plant_engine_sibling(root: Path, sentinel: Path) -> None:
    for mod in ("argparse", "yaml"):
        (root / ".tess" / "bin" / f"{mod}.py").write_text(
            f"open({str(sentinel)!r}, 'a').write({mod!r} + '\\n')\n", encoding="utf-8")


def _claude_gate_command() -> str:
    data = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    for entry in data["hooks"]["PreToolUse"]:
        for hook in entry["hooks"]:
            if "tess-gate.py" in hook["command"]:
                return hook["command"]
    raise AssertionError("no tess-gate.py hook in .claude/settings.json")


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
@pytest.mark.parametrize("runtime", ["codex", "claude"])
def test_push_check_never_runs_a_planted_engine_sibling(proj, tmp_path, runtime):
    sentinel = tmp_path / "SENTINEL"
    _plant_engine_sibling(proj, sentinel)
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    _git(proj, "remote", "add", "origin", str(remote))
    cmd = "git push origin HEAD:main"
    if runtime == "codex":
        r = _hook(proj, {"turn_id": "t1", "tool_name": "Bash", "cwd": str(proj),
                         "tool_input": {"command": cmd}})
    else:
        payload = {"session_id": "s", "hook_event_name": "PreToolUse", "cwd": str(proj),
                   "permission_mode": "default", "tool_name": "Bash",
                   "tool_input": {"command": cmd}}
        r = subprocess.run(["sh", "-c", _claude_gate_command()], input=json.dumps(payload),
                           capture_output=True, text=True, cwd=str(proj), timeout=120,
                           env={**os.environ, "CLAUDE_PROJECT_DIR": str(proj),
                                "TESS_GATE_LOG": os.devnull})
    assert r.returncode in (0, 2), r.stderr
    assert "TESS HOOK NOT RUN" not in r.stderr, r.stderr   # the gate itself ran
    assert not sentinel.exists(), sentinel.read_text()


def test_gate_launches_the_engine_isolated():
    gate = (REPO / ".claude/hooks/tess-gate.py").read_text(encoding="utf-8")
    assert '[sys.executable, "-I", "-B", str(tessctl), "doctor", "--publish-remote"' in gate
    assert re.search(r"\[sys\.executable, str\(tessctl\)", gate) is None


# Every place the repo launches Python on repo code, and the isolated form it must use.
_LAUNCHES = [
    (".tess/bin/tessctl", '[sys.executable, "-I", "-B", "-c",'),
    (".tess/bin/tessctl", '[sys.executable, "-I", "-B", str(engine_path), "doctor"]'),
    (".tess/bin/tessctl", 'sys.executable, "-I", "-B", str(emit_cli), "emit",'),
    ("create-tess/src/keystone.js", "execFileSync('python3', ['-I', '-B', py, ...argsArr]"),
    ("create-tess/src/brain.js", "execFileSync('python3', ['-I', '-B', script, ...args]"),
    ("create-tess/src/python.js", "spawnSync(cmd, ['-I', '-c',"),
    ("scripts/tess", '[sys.executable, "-I", "-B", str(tool), "status", "--json"]'),
    ("tools/receipt-emit/receipt_emit.py", '[sys.executable, "-I", "-B", str(RECEIPT_VERIFY_CLI)'),
    (".github/workflows/ci.yml", "run: python3 -I -B .tess/bin/tessctl doctor"),
    (".github/workflows/ci.yml", "run: python3 -I -B .tess/bin/tessctl verify"),
    (".github/workflows/release.yml", "run: python3 -I -B .tess/bin/tessctl doctor"),
    (".github/workflows/release.yml", "run: python3 -I -B .tess/bin/tessctl verify"),
]


@pytest.mark.parametrize("rel,needle", _LAUNCHES)
def test_repo_python_launches_are_isolated(rel, needle):
    assert needle in (REPO / rel).read_text(encoding="utf-8"), rel


def test_no_unisolated_tessctl_launch_remains():
    pat = re.compile(r"(sys\.executable|'python3'|\bpython3?)\s*[,\]]?\s*\[?\s*"
                     r"(str\()?[\w.\"'/]*tessctl\b")
    offenders = []
    for rel in (".claude/hooks/tess-gate.py", ".tess/bin/tessctl", "create-tess/src/keystone.js",
                ".github/workflows/ci.yml", ".github/workflows/release.yml", "tessctl"):
        for n, line in enumerate((REPO / rel).read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line) and "-I" not in line and not line.lstrip().startswith(("#", "//")):
                offenders.append(f"{rel}:{n}: {line.strip()}")
    assert not offenders, offenders


# --- R4: run-pinned.py --closure rejects everything importable that is not a pinned .py --------

@pytest.fixture
def pinned(tmp_path):
    root = tmp_path / "inst"
    for rel in (".claude/hooks", ".tess/tess.lock", ".tess/core/pinned-scripts.sha256"):
        src, dst = REPO / rel, root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, dst)
    shutil.copytree(REPO / "scripts/brain", root / "scripts/brain",
                    ignore=shutil.ignore_patterns("__pycache__"))
    return root


def _launch(root: Path, *target):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env["CLAUDE_PROJECT_DIR"] = str(root)
    return subprocess.run([sys.executable, "-I", "-B", str(root / LAUNCHER), "--on-fail", "block",
                           "--closure", "scripts/brain", "--", *target],
                          cwd=str(root), env=env, capture_output=True, text=True, timeout=120)


def test_clean_closure_runs_the_verified_target(pinned):
    r = _launch(pinned, "scripts/brain/tessbrain.py", "--help")
    assert r.returncode == 0, r.stderr
    assert "usage: tessbrain.py" in r.stdout


@pytest.mark.parametrize("planted", [
    "scripts/brain/brainlib/__init__.so",
    "scripts/brain/brainlib/caps.cpython-313-darwin.so",
    "scripts/brain/brainlib/caps.abi3.so",
    "scripts/brain/brainlib/__init__.pyd",
    "scripts/brain/brainlib/__init__.dylib",
    "scripts/brain/brainlib/evil.pyc",
    "scripts/brain/json.pyc",
    "scripts/brain/brainlib/evil.pth",
    "scripts/brain/brainlib/Evil.PY",
    "scripts/brain/brainlib/__pycache__/nested/x.pyc",
])
def test_planted_importable_artifact_is_refused_before_import(pinned, planted):
    path = pinned / planted
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")        # never imported: refusal happens before Python runs
    r = _launch(pinned, "scripts/brain/tessbrain.py", "--help")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "TESS HOOK NOT RUN" in r.stderr
    assert "usage: tessbrain.py" not in r.stdout


@pytest.mark.skipif(not hasattr(os, "symlink") or sys.platform.startswith("win"),
                    reason="needs symlinks")
@pytest.mark.parametrize("link,to", [
    ("scripts/brain/brainlib/linked.txt", "scripts/brain/BOOT.md"),
    ("scripts/brain/extra", "scripts/brain/modes"),
])
def test_symlink_in_the_closure_is_refused(pinned, link, to):
    os.symlink(str(pinned / to), str(pinned / link))
    r = _launch(pinned, "scripts/brain/tessbrain.py", "--help")
    assert r.returncode == 2 and "symlink" in r.stderr, r.stderr


def test_unpinned_py_is_still_refused_and_data_files_are_fine(pinned):
    (pinned / "scripts/brain/templates/notes.md").write_text("x\n")
    assert _launch(pinned, "scripts/brain/tessbrain.py", "--help").returncode == 0
    (pinned / "scripts/brain/brainlib/json.py").write_text("raise SystemExit(9)\n")
    r = _launch(pinned, "scripts/brain/tessbrain.py", "--help")
    assert r.returncode == 2 and "not pinned" in r.stderr, r.stderr


def test_plain_pycache_is_tolerated_because_it_is_never_read(pinned):
    cache = pinned / "scripts/brain/brainlib/__pycache__"
    cache.mkdir()
    (cache / "caps.cpython-313.pyc").write_bytes(b"not bytecode")
    r = _launch(pinned, "scripts/brain/tessbrain.py", "--help")
    assert r.returncode == 0, r.stderr


def test_target_runs_from_the_captured_verified_bytes(pinned, tmp_path):
    """The interpreter executes the bytes the launcher hashed: a copy fed to a
    fixed bootstrap, never a second read of the working-tree file."""
    src = (REPO / LAUNCHER).read_text(encoding="utf-8")
    assert '"-c", _BOOTSTRAP' in src and "_check_capture" in src
    r = _launch(pinned, "scripts/brain/tessbrain.py", "--help")
    assert r.returncode == 0 and "usage: tessbrain.py" in r.stdout, r.stderr
