"""Tests for the top-level pipeline entry points (`run_intent_router`,
`continue_with_clarification`) and the CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import _paths  # noqa: F401 -- sys.path bootstrap, see _paths.py docstring

from intent_router import read_decisions
from intent_router.pipeline import continue_with_clarification, run_intent_router

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COMPONENT_ROOT = REPO_ROOT / "intent-router"
EXAMPLE_TABLE = COMPONENT_ROOT / "routing_table.example.yaml"


def test_run_intent_router_logs_by_default(tmp_path):
    log_path = tmp_path / "log.jsonl"
    decision = run_intent_router(
        "we need to build a new feature and finish the roadmap",
        EXAMPLE_TABLE,
        log_path=log_path,
    )
    assert decision.route_id == "product-mode"
    records = list(read_decisions(log_path))
    assert len(records) == 1


def test_run_intent_router_can_skip_logging(tmp_path):
    log_path = tmp_path / "log.jsonl"
    run_intent_router(
        "we need to build a new feature and finish the roadmap",
        EXAMPLE_TABLE,
        log_path=False,
    )
    assert not log_path.exists()


def test_continue_with_clarification_end_to_end(tmp_path):
    log_path = tmp_path / "log.jsonl"
    first = run_intent_router("hello", EXAMPLE_TABLE, log_path=log_path)
    assert first.ambiguous is True

    second = continue_with_clarification(
        first,
        "It's about whether we should expand into a brand new country market.",
        EXAMPLE_TABLE,
        log_path=log_path,
    )
    assert second.ambiguous is False
    records = list(read_decisions(log_path))
    assert len(records) == 2


def test_cli_route_prints_narration(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "intent_router.cli",
            "route",
            "we need to build a new feature and finish the roadmap",
            "--table",
            str(EXAMPLE_TABLE),
            "--no-log",
        ],
        cwd=str(COMPONENT_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "/product-mode" in result.stdout


def test_cli_route_json_output_is_parseable(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "intent_router.cli",
            "route",
            "we need to build a new feature and finish the roadmap",
            "--table",
            str(EXAMPLE_TABLE),
            "--json",
            "--no-log",
        ],
        cwd=str(COMPONENT_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    record = json.loads(result.stdout)
    assert record["route_id"] == "product-mode"


def test_cli_no_log_flag_writes_nothing(tmp_path):
    import os

    # Run from a scratch cwd so a bug that ignores --no-log would write to
    # a directory we control, not the repo's own intent-router/decisions/.
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(COMPONENT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "intent_router.cli",
            "route",
            "we need to build a new feature and finish the roadmap",
            "--table",
            str(EXAMPLE_TABLE),
            "--no-log",
        ],
        cwd=str(scratch),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert not (COMPONENT_ROOT / "decisions" / "log.jsonl").exists()
