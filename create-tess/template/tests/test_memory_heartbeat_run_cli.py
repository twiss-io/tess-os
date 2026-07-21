"""End-to-end CLI test for scripts/heartbeat/run.py.

Runs the real script as a subprocess against this checkout with an explicit
`--dry-run` flag, which forces dry-run regardless of activation state or
environment — this is always safe (no card writes, no `claude -p` spawn, no
notification send, no git commit/push) per run.py's own module docstring.
`TESS_MEMORY_STATE_DIR` is redirected to a throwaway tmp dir so even the
runner's own lockfile/state.json never touches a real operator's state dir.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_PY = REPO_ROOT / "scripts" / "heartbeat" / "run.py"


def _run(tmp_path, *extra_args, extra_env=None):
    env = {**os.environ, "TESS_MEMORY_STATE_DIR": str(tmp_path / "state")}
    # Explicitly unset activation so this test is unaffected by whatever the
    # calling shell's environment happens to have set.
    env.pop("TESS_MEMORY_HEARTBEAT_ACTIVATED", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(RUN_PY), "--dry-run", *extra_args],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=60,
    )


def test_dry_run_exits_zero_and_reports_dry_run_true(tmp_path):
    result = _run(tmp_path, "--daily", "--quiet")
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["dry_run"] is True
    assert summary["activated"] is False


def test_dry_run_with_activation_env_still_forces_dry_run_via_explicit_flag(tmp_path):
    """Even with the activation env var set to true, passing --dry-run on
    the CLI must still force dry_run=True (the explicit flag always wins) —
    this is the exact invocation shape that is safe to run against ANY
    checkout, including one with a real git remote."""
    result = _run(tmp_path, "--daily", "--quiet", extra_env={"TESS_MEMORY_HEARTBEAT_ACTIVATED": "1"})
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["activated"] is True
    assert summary["dry_run"] is True  # --dry-run flag still wins
    assert summary["daily_recompile"]["synthesis"]["_dry_run_note"]


def test_not_activated_forces_dry_run_even_without_the_flag(tmp_path):
    """Omitting --dry-run entirely must still behave as dry-run when
    heartbeat.config.json's activated=false and no env override is set —
    the second, independent off-switch this port adds."""
    env = {**os.environ, "TESS_MEMORY_STATE_DIR": str(tmp_path / "state")}
    env.pop("TESS_MEMORY_HEARTBEAT_ACTIVATED", None)
    result = subprocess.run(
        [sys.executable, str(RUN_PY), "--daily", "--quiet"],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["activated"] is False
    assert summary["dry_run"] is True
