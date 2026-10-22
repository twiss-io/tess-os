"""v1.0.1 (2026-09-29 Codex review, HIGH): the hook launcher
.claude/hooks/run-pinned.py must not import planted modules at startup.

Before the fix every hook command ran `python3 .../run-pinned.py`, which puts
.claude/hooks/ first on sys.path, so a planted `.claude/hooks/hashlib.py` or
`json.py` executed before any pin was checked. Now every hook command starts
it as `python3 -I -B`, the launcher re-executes itself that way if a caller
forgets, and it refuses to run while extra Python files sit beside it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
LAUNCHER_REL = ".claude/hooks/run-pinned.py"
TARGET = ".claude/hooks/utc-local-context.sh"


def _claude_hook_commands(rel: str) -> list:
    data = json.loads((REPO / rel).read_text())
    return [h["command"] for groups in data["hooks"].values() for g in groups for h in g["hooks"]]


def _codex_hook_commands(rel: str) -> list:
    return re.findall(r'^command = "(.*)"$', (REPO / rel).read_text(), re.M)


@pytest.mark.parametrize("rel,reader", [
    (".claude/settings.json", _claude_hook_commands),
    (".tess/core/settings-core.json", _claude_hook_commands),
    (".codex/config.toml", _codex_hook_commands),
    (".tess/core/templates/agents-md/codex-config.toml.tpl", _codex_hook_commands),
])
def test_every_launcher_call_site_is_isolated(rel, reader):
    cmds = [c for c in reader(rel) if "run-pinned.py" in c]
    assert cmds, rel
    for cmd in cmds:
        calls = re.findall(r"python3( -I -B)? \\?\"\$(?:CLAUDE_PROJECT_DIR/\.claude/hooks/run-pinned\.py|l|d/\.claude/hooks/run-pinned\.py)", cmd)
        assert calls and all(c == " -I -B" for c in calls), f"{rel}: {cmd[:160]}"


def test_engine_entry_points_are_isolated():
    assert 'exec python3 -I -B "${TESSCTL_PY}"' in (REPO / "tessctl").read_text()
    engine = (REPO / ".tess/bin/tessctl").read_text()
    assert '"$PYTHON_BIN" "$TESSCTL"' not in engine
    assert engine.count('"$PYTHON_BIN" -I -B "$TESSCTL"') == 3


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for rel in (".claude/hooks", ".tess/tess.lock", ".tess/core/pinned-scripts.sha256"):
        src, dst = REPO / rel, tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, dst)
    return tmp_path


def _plant(project: Path, sentinels: Path) -> None:
    for mod in ("hashlib", "json"):
        (project / ".claude/hooks" / f"{mod}.py").write_text(
            f"open({str(sentinels / ('SENTINEL_' + mod))!r}, 'w').close()\n")


def _run(project: Path, argv: list, env_extra: dict | None = None):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update({"CLAUDE_PROJECT_DIR": str(project), **(env_extra or {})})
    return subprocess.run(argv, cwd=str(project), env=env, capture_output=True, text=True, input="{}")


def _shipped_command(target: str) -> str:
    return next(c for c in _claude_hook_commands(".claude/settings.json") if c.endswith("-- " + target))


def test_planted_modules_do_not_run_through_the_shipped_hook_command(project, tmp_path):
    _plant(project, tmp_path)
    r = _run(project, ["sh", "-c", _shipped_command(TARGET)])
    assert not list(tmp_path.glob("SENTINEL_*")), "a planted module ran"
    assert r.returncode == 0, r.stderr  # warn mode: the session keeps working
    assert "TESS HOOK NOT RUN" in r.stderr and "unexpected Python code" in r.stderr


def test_planted_modules_do_not_run_even_when_a_caller_omits_isolation(project, tmp_path):
    _plant(project, tmp_path)
    r = _run(project, ["python3", str(project / LAUNCHER_REL), "--on-fail", "warn", "--", TARGET])
    assert not list(tmp_path.glob("SENTINEL_*")), "a planted module ran"
    assert "unexpected Python code" in r.stderr


def test_planted_modules_block_a_blocking_hook(project, tmp_path):
    _plant(project, tmp_path)
    r = _run(project, ["python3", "-I", "-B", str(project / LAUNCHER_REL), "--on-fail", "block",
                       "--", ".claude/hooks/vault-dispatch-scan.py"])
    assert r.returncode == 2
    assert not list(tmp_path.glob("SENTINEL_*"))


def test_hook_still_runs_when_clean_even_with_a_hostile_pythonpath(project, tmp_path):
    evil = tmp_path / "evil"
    evil.mkdir()
    (evil / "hashlib.py").write_text(f"open({str(tmp_path / 'SENTINEL_pp')!r}, 'w').close()\n")
    r = _run(project, ["python3", str(project / LAUNCHER_REL), "--on-fail", "warn", "--", TARGET],
             {"PYTHONPATH": str(evil)})
    assert not (tmp_path / "SENTINEL_pp").exists(), "PYTHONPATH module ran in the launcher"
    assert r.returncode == 0 and "TESS HOOK NOT RUN" not in r.stderr + r.stdout, r.stderr
    r = _run(project, ["sh", "-c", _shipped_command(TARGET)])
    assert r.returncode == 0 and "TESS HOOK NOT RUN" not in r.stderr + r.stdout, r.stderr
