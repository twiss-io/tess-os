"""End-to-end CLI tests for `run.py --dry-run` — both as a direct function
call (fast) and as a real subprocess invocation (slower, but proves the
literal acceptance-criteria command actually works as a CLI, not just as
importable Python).
"""
from __future__ import annotations

import subprocess
import sys

import run  # proving-ground/run.py — importable because conftest.py put
             # PROVING_GROUND_ROOT on sys.path first.
from pg_lib.paths import PROVING_GROUND_ROOT


def test_dry_run_via_main_returns_zero(capsys):
    exit_code = run.main(["--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DRY RUN: OK" in captured.out
    assert "$0 spent" in captured.out


def test_dry_run_never_spends_because_it_never_shells_out_to_claude(monkeypatch):
    """Belt-and-suspenders: patch subprocess.run to explode if --dry-run
    ever tries to invoke a subprocess at all."""

    def _explode(*args, **kwargs):
        raise AssertionError("run.py --dry-run must never invoke a subprocess")

    monkeypatch.setattr(subprocess, "run", _explode)
    exit_code = run.main(["--dry-run"])
    assert exit_code == 0


def test_dry_run_as_a_real_subprocess_cli_invocation():
    proc = subprocess.run(
        [sys.executable, str(PROVING_GROUND_ROOT / "run.py"), "--dry-run"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DRY RUN: OK" in proc.stdout


def test_dry_run_with_bad_task_filter_still_only_validates_not_runs():
    """--dry-run ignores --tasks/--models filters entirely — it always
    validates the WHOLE suite, since a filtered dry-run would give a false
    "all clear" while a task outside the filter is actually broken."""
    exit_code = run.main(["--dry-run", "--tasks", "01-bug-average-empty-list"])
    assert exit_code == 0
