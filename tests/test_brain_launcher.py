"""scripts/tess: the per-runtime launcher (spec 5.1, 6.2 "Launcher start prompt").

It passes the brain-onboard start prompt only while onboarding is pending or
in progress; once complete, skipped or deferred it launches the CLI plain;
in the source repo it never onboards. Checked with --print-cmd, so no
runtime CLI is ever started by the suite.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import _brain_oobe_helpers as h

LAUNCHER = h.REPO_ROOT / "scripts" / "tess"


def instance(tmp: Path, source_repo: bool = False) -> Path:
    root = h.mini_instance(tmp, source_repo=source_repo)
    shutil.copy2(str(LAUNCHER), str(root / "scripts" / "tess"))
    return root


def launch(root: Path, *args: str, path: str = None) -> subprocess.CompletedProcess:
    env = h.env()
    if path is not None:
        env["PATH"] = path
    return subprocess.run([sys.executable, "-I", str(root / "scripts" / "tess")] + list(args),
                          capture_output=True, text=True, env=env, timeout=30)


EXPECT_PENDING = {
    "claude": "claude /brain-onboard",
    "codex": "codex '$brain-onboard'",
    "gemini": "gemini -i 'Use the brain-onboard skill.'",
}


@pytest.mark.parametrize("runtime", sorted(EXPECT_PENDING))
def test_pending_passes_the_start_prompt(tmp_path, runtime):
    done = launch(instance(tmp_path), runtime, "--print-cmd")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == EXPECT_PENDING[runtime]


def test_in_progress_still_passes_the_start_prompt(tmp_path):
    root = instance(tmp_path)
    assert h.onboard(root, "answer", "mode", "--value", "personal", "--quote", "Just me.").returncode == 0
    assert launch(root, "claude", "--print-cmd").stdout.strip() == "claude /brain-onboard"


@pytest.mark.parametrize("runtime", sorted(EXPECT_PENDING))
def test_complete_launches_plain(tmp_path, runtime):
    root = instance(tmp_path)
    assert h.onboard_fixture(root, "personal").returncode == 0
    assert launch(root, runtime, "--print-cmd").stdout.strip() == runtime


def test_deferred_launches_plain(tmp_path):
    root = instance(tmp_path)
    assert h.onboard(root, "defer", "--days", "7").returncode == 0
    assert launch(root, "codex", "--print-cmd").stdout.strip() == "codex"


def test_source_repo_never_onboards(tmp_path):
    done = launch(instance(tmp_path, source_repo=True), "claude", "--print-cmd")
    assert done.returncode == 0 and done.stdout.strip() == "claude"
    assert "npm create tess@latest" in done.stderr


def test_extra_args_go_before_the_start_prompt(tmp_path):
    done = launch(instance(tmp_path), "gemini", "--print-cmd", "--", "--model", "m1")
    assert done.stdout.strip() == "gemini --model m1 -i 'Use the brain-onboard skill.'"


def test_unknown_runtime_is_usage_error(tmp_path):
    done = launch(instance(tmp_path), "notacli")
    assert done.returncode == 2 and "claude|codex|gemini" in done.stderr


def test_missing_cli_exits_127(tmp_path):
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    done = launch(instance(tmp_path), "claude", path=str(empty))
    assert done.returncode == 127 and "not on PATH" in done.stderr


def test_broken_brain_json_still_launches(tmp_path):
    root = instance(tmp_path)
    (root / "brain").mkdir()
    (root / "brain" / "brain.json").write_text("{not json")
    done = launch(root, "claude", "--print-cmd")
    assert done.returncode == 0 and done.stdout.strip() == "claude"
    assert "status unavailable" in done.stderr
