"""CLI-level contract coverage for the portable crew-plan reference.

The validator writes a trace record for every invocation.  These tests copy
only the real CLI and contract schemas into a temporary root so the trace is
isolated from the checkout and removed with pytest's temporary directory.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_PLAN = REPO_ROOT / "examples" / "portable-crew-plan" / "plan.json"


def _scratch_root(tmp_path: Path) -> Path:
    """Build the smallest root that exercises the shipped CLI and schemas."""
    root = tmp_path / "tess-root"
    (root / ".tess" / "bin").mkdir(parents=True)
    (root / "core").mkdir()
    shutil.copy2(REPO_ROOT / "tess.manifest.json", root / "tess.manifest.json")
    shutil.copy2(REPO_ROOT / ".tess" / "bin" / "tessctl", root / ".tess" / "bin" / "tessctl")
    shutil.copytree(REPO_ROOT / "core" / "contracts", root / "core" / "contracts")
    return root


def _example_plan() -> dict:
    return json.loads(EXAMPLE_PLAN.read_text(encoding="utf-8"))


def _validate(root: Path, plan: dict) -> tuple[subprocess.CompletedProcess[str], list[Path]]:
    """Run the real CLI on a scratch-local input and return its trace writes."""
    plan_path = root / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    env = {**os.environ, "TESS_ROOT": str(root)}
    result = subprocess.run(
        [
            sys.executable,
            str(root / ".tess" / "bin" / "tessctl"),
            "validate",
            "crew-plan",
            str(plan_path),
            "--json",
        ],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, sorted((root / ".tess" / "trace" / "runs").glob("*.jsonl"))


def _result_json(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)


def _assert_trace(root: Path, traces: list[Path], expected_outcome: str) -> None:
    assert len(traces) == 1
    trace = traces[0]
    assert trace.is_relative_to(root / ".tess" / "trace" / "runs")
    event = json.loads(trace.read_text(encoding="utf-8"))
    assert event["phase"] == "validate"
    assert event["action"] == "validate"
    assert event["outcome"] == expected_outcome
    assert event["subject"]["contract_type"] == "crew-plan"


def _source_trace_snapshot() -> dict[Path, bytes]:
    """Capture any pre-existing checkout traces without assuming none exist."""
    trace_dir = REPO_ROOT / ".tess" / "trace"
    return {
        path.relative_to(trace_dir): path.read_bytes()
        for path in trace_dir.rglob("*")
        if path.is_file()
    } if trace_dir.exists() else {}


def test_portable_crew_plan_passes_real_cli_in_disposable_root(tmp_path):
    root = _scratch_root(tmp_path)
    source_traces_before = _source_trace_snapshot()
    result, traces = _validate(root, _example_plan())

    assert result.returncode == 0, result.stderr
    assert _result_json(result)["valid"] is True
    _assert_trace(root, traces, "pass")
    assert _source_trace_snapshot() == source_traces_before


def test_portable_crew_plan_rejects_unsafe_task_id(tmp_path):
    root = _scratch_root(tmp_path)
    plan = _example_plan()
    plan["crew_plan"]["stages"][0]["tasks"][0]["id"] = "task/escape"

    result, traces = _validate(root, plan)

    assert result.returncode == 1
    assert _result_json(result)["valid"] is False
    assert "does not match pattern" in result.stdout
    _assert_trace(root, traces, "block")


def test_portable_crew_plan_rejects_parallel_stage_dependency(tmp_path):
    root = _scratch_root(tmp_path)
    plan = _example_plan()
    stage = plan["crew_plan"]["stages"][0]
    stage["parallel"] = True
    second_task = copy.deepcopy(stage["tasks"][0])
    second_task["id"] = "evidence-map"
    stage["tasks"].append(second_task)
    stage["tasks"][0]["depends_on"] = ["evidence-map"]

    result, traces = _validate(root, plan)

    assert result.returncode == 1
    assert _result_json(result)["valid"] is False
    assert "parallel:true" in result.stdout
    _assert_trace(root, traces, "block")


def test_portable_crew_plan_rejects_unknown_synthesis_input(tmp_path):
    root = _scratch_root(tmp_path)
    plan = _example_plan()
    plan["crew_plan"]["synthesis"]["inputs"] = ["missing-task"]

    result, traces = _validate(root, plan)

    assert result.returncode == 1
    assert _result_json(result)["valid"] is False
    assert "does not match any task id" in result.stdout
    _assert_trace(root, traces, "block")


def test_portable_crew_plan_rejects_externally_visible_task_without_verifier(tmp_path):
    root = _scratch_root(tmp_path)
    plan = _example_plan()
    plan["crew_plan"]["stages"][0]["tasks"][0]["externally_visible"] = True

    result, traces = _validate(root, plan)

    assert result.returncode == 1
    assert _result_json(result)["valid"] is False
    assert "expected constant True" in result.stdout
    assert "not one of" in result.stdout
    assert "array length 0 < minItems 1" in result.stdout
    _assert_trace(root, traces, "block")
