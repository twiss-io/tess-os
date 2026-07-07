"""
Goal #6 — `tessctl run <crew-plan>`: the mechanical CONDUCTOR LOOP.

Spec: docs/ULTIMATE_FRAMEWORK_PLAN.md's Phase-2 `tessctl run <plan>` target
line; conductor/orchestra-model.md §4 ("The Conductor Loop");
conductor/subagent-failure-protocol.md (failure states, cause classes, the
3-attempt cap, changed-brief requirement, escalation). Implementation: the
RUN region of .tess/bin/tessctl (directly below the MISSION LEDGER region).

Coverage (per the dispatch brief's explicit acceptance list):
  * A 2-stage plan runs end-to-end with FakeDriver in "good" mode: dispatch
    -> validate -> verify -> next, for both stages, including a mandatory
    verifier dispatch on stage 2's task.
  * A schema-missing return triggers degraded_output -> changed-brief retry
    -> cap-3 -> escalation record — asserting the ledger entries (3 retry
    attempt files, each independently passing `tessctl validate retry`) AND
    the halt (mission state flips to code-red; no 4th dispatch call made).
  * A verifier BLOCK halts the run with no further stages executed (proven
    via driver.calls never containing the next stage's task).
  * A gate left uncleared halts immediately with ZERO dispatch calls made
    ("never start early").
  * CLI wiring: `tessctl run --driver fake --fake-script ...` end-to-end via
    subprocess (argparse, dispatch table, exit codes).
  * `missions/**` (including the new returns/ and escalations/ subdirs)
    stays invisible to doctor/verify/lock --check after a full run, exactly
    like retries/ already does for Goal #5.
  * Every return-manifest/verdict artifact a successful run writes
    independently passes `tessctl validate <contract-type> <path>` (dogfood,
    via CLI subprocess — not just the in-process check `run` itself uses).
  * ClaudeCliDriver's constructed CLI invocation always carries an explicit
    `--allowed-tools` allowlist — a regression guard for a bug the live
    smoke run itself caught: a headless `claude -p` dispatch with no
    explicit tool allowlist silently DENIES a tool call (e.g. `Write`) with
    no prompt surfaced, burning all 3 retry attempts on `failure_state:
    empty` before this was diagnosed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT, ENGINE_SRC, MANIFEST_SRC

CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rroot(tmp_path):
    """A minimal synthetic Tess OS root: all six contract schemas `run`
    touches (brief is $ref'd from crew-plan; return-manifest/verdict/
    mission/retry are all read/written during a run), `tess.manifest.json`
    with the real `missions/**` never_touch entry, and the engine itself."""
    root = tmp_path / "os"
    contracts_dir = root / "core" / "contracts"
    contracts_dir.mkdir(parents=True)
    for fname in ("brief.schema.json", "crew-plan.schema.json", "verdict.schema.json",
                  "return-manifest.schema.json", "mission.schema.json", "retry.schema.json"):
        shutil.copy2(CONTRACTS_SRC / fname, contracts_dir / fname)
    (root / "tess.manifest.json").write_text(
        json.dumps({"schema": 1, "owned_globs": [], "never_touch": ["missions/**"]}),
        encoding="utf-8",
    )
    bin_dir = root / ".tess" / "bin"
    bin_dir.mkdir(parents=True)
    dst_engine = bin_dir / "tessctl"
    shutil.copy2(ENGINE_SRC, dst_engine)
    os.chmod(dst_engine, 0o755)
    return root


def _run_cli(root, *args, input_text=None):
    env = {**os.environ, "TESS_ROOT": str(root)}
    return subprocess.run(
        [sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
        cwd=str(root), env=env, capture_output=True, text=True, input=input_text,
    )


def _mission_dir(root, mission_id):
    return root / "missions" / mission_id


def _new_mission(engine, root, name="Run Test Mission"):
    r = _run_cli(root, "mission", "new", name)
    assert r.returncode == 0, r.stdout + r.stderr
    return next(p.name for p in (root / "missions").iterdir() if p.is_dir())


def _clear_gate(engine, root, mission_id, gate_name, evidence_path):
    """Direct engine-level gate clear — bypasses the CLI's git+gpg tool
    requirement on the top-level `gate` command (run's own tests don't need
    to exercise `gate clear` itself, only need a precondition mission with
    cleared gates)."""
    record = engine._read_mission_record(root, mission_id)
    for g in record["gates"]:
        if g["name"] == gate_name:
            g["cleared"] = True
            g["cleared_by"] = "test-harness"
            g["cleared_at"] = "2026-07-07T00:00:00Z"
            g["evidence"] = str(evidence_path)
    engine._write_mission_record(root, mission_id, record)


def _clear_all_five_gates(engine, root, mission_id, evidence_path):
    for gate_name in engine.MISSION_GATES:
        _clear_gate(engine, root, mission_id, gate_name, evidence_path)


def _brief(objective="Do the task."):
    return {
        "objective": objective,
        "output_contract": "Write the contracted return-manifest JSON.",
        "tools_sources_constraints": "none required for this test task",
        "not_responsible_for": "n/a",
        "milestones": [],
        "escalation_trigger": "If blocked, stop and report.",
    }


def _task(task_id, *, depends_on=None, verifier_required=False, verifier_agent="Reid"):
    return {
        "id": task_id, "agent": "ada", "role": "Owner", "depends_on": depends_on or [],
        "brief": _brief(f"Do {task_id}."),
        "verifier": {
            "agent": verifier_agent if verifier_required else None,
            "required": verifier_required,
            "primary_artifacts": [f"artifact-for-{task_id}"] if verifier_required else [],
        },
    }


def _crew_plan(mission_id, stages):
    return {
        "crew_plan": {
            "mission_id": mission_id, "outcome_owner": "test-orchestrator",
            "outcome_type": "build", "stages": stages,
            "synthesis": {"owner": "tess", "format": "memo", "inputs": []},
            "escalations": [],
        }
    }


def _write_plan(root, name, plan_dict):
    p = root / name
    p.write_text(json.dumps(plan_dict, indent=2), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. A 2-stage plan runs end-to-end: dispatch -> validate -> verify -> next.
# ---------------------------------------------------------------------------

def test_run_two_stage_plan_end_to_end_success(engine, rroot, monkeypatch):
    monkeypatch.chdir(rroot)
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)

    plan = _crew_plan(mission_id, [
        {
            "stage": 1, "gate_in": "intake-before-anything", "parallel": False,
            "tasks": [_task("research")],
        },
        {
            "stage": 2, "gate_in": "research-before-build", "parallel": False,
            "tasks": [_task("build", depends_on=["research"], verifier_required=True)],
        },
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    driver = engine.FakeDriver(default_mode="good")
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "complete", result
    assert result["stages_completed"] == 2
    assert [t["task_id"] for t in result["tasks"]] == ["research", "build"]
    assert all(t["status"] == "complete" for t in result["tasks"])

    # The verifier for "build" was actually dispatched.
    call_ids = [c["task_id"] for c in driver.calls]
    assert call_ids == ["research", "build", "build.verify"]

    # Both a return-manifest and a verdict were written, and BOTH
    # independently pass `tessctl validate` (dogfood, via the real CLI).
    research_return = _mission_dir(rroot, mission_id) / "returns" / "research.return.json"
    build_return = _mission_dir(rroot, mission_id) / "returns" / "build.return.json"
    build_verdict = _mission_dir(rroot, mission_id) / "returns" / "build.verify.verdict.json"
    assert research_return.exists() and build_return.exists() and build_verdict.exists()

    for contract_type, path in (
        ("return-manifest", research_return), ("return-manifest", build_return),
        ("verdict", build_verdict),
    ):
        v = _run_cli(rroot, "validate", contract_type, str(path))
        assert v.returncode == 0, f"{path} failed validate:\n{v.stdout}{v.stderr}"

    # Mission record is untouched (no escalation) — state stays "intake".
    mission = engine._read_mission_record(rroot, mission_id)
    assert mission["state"] == "intake"


# ---------------------------------------------------------------------------
# 2. schema-missing -> degraded_output -> changed-brief retry -> cap-3 ->
#    escalation record. Assert the ledger entries + the halt.
# ---------------------------------------------------------------------------

def test_run_schema_missing_return_retries_to_cap_then_escalates(engine, rroot, monkeypatch):
    monkeypatch.chdir(rroot)
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("flaky")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    driver = engine.FakeDriver(script={"flaky": {"mode": "schema-missing"}})
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "halted"
    assert "retry_cap_exhausted" in result["halt_reason"] or "attempt cap" in result["halt_reason"]
    assert result["escalation_path"]

    # Exactly 3 dispatch calls were made for "flaky" — never a 4th (the cap
    # is checked BEFORE dispatch, not just before logging).
    flaky_calls = [c for c in driver.calls if c["task_id"] == "flaky"]
    assert len(flaky_calls) == 3, driver.calls

    # 3 retry attempt files logged, each independently valid, each
    # classified degraded/context-gap (the schema-miss default), and each
    # attempt's brief differs from the one before it (the changed-brief
    # rule doing its job).
    retries_dir = _mission_dir(rroot, mission_id) / "retries"
    attempt_files = sorted(retries_dir.glob("flaky.attempt-*.md"))
    assert len(attempt_files) == 3, attempt_files

    prior_brief = None
    for i, p in enumerate(attempt_files, start=1):
        v = _run_cli(rroot, "validate", "retry", str(p))
        assert v.returncode == 0, f"{p} failed validate:\n{v.stdout}{v.stderr}"
        rec = yaml.safe_load(p.read_text(encoding="utf-8").split("---", 2)[1])
        assert rec["attempt"] == i
        assert rec["failure_state"] == "degraded"
        assert rec["cause_class"] == "context-gap"
        if prior_brief is not None:
            assert rec["brief_text"] != prior_brief, "consecutive attempts must have DIFFERENT briefs"
        prior_brief = rec["brief_text"]

    # Escalation record: reason, per-attempt analysis, and the mission
    # record's state flipped to code-red (subagent-failure-protocol.md:
    # "STOP; escalate to the operator with the full per-attempt analysis").
    esc_path = Path(result["escalation_path"])
    assert esc_path.exists()
    esc_fm = yaml.safe_load(esc_path.read_text(encoding="utf-8").split("---", 2)[1])
    assert esc_fm["reason"] == "retry_cap_exhausted"
    assert esc_fm["mission_id"] == mission_id
    assert esc_fm["task"] == "flaky"
    esc_body = esc_path.read_text(encoding="utf-8")
    assert "Per-attempt analysis" in esc_body
    assert "attempt 1" in esc_body and "attempt 2" in esc_body and "attempt 3" in esc_body

    mission = engine._read_mission_record(rroot, mission_id)
    assert mission["state"] == "code-red"


def test_run_missing_file_return_classified_transient_and_permits_same_brief(engine, rroot, monkeypatch):
    monkeypatch.chdir(rroot)
    """A driver that reports ok:True but writes NOTHING is an infra 'empty
    return' — classified transient (subagent-failure-protocol.md), which
    permits a same-brief retry rather than forcing a changed one. Prove the
    ledger records failure_state=empty/cause_class=transient and that an
    IDENTICAL brief is allowed across attempts (no forced brief mutation)."""
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("ghost")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    driver = engine.FakeDriver(script={"ghost": {"mode": "missing-file"}})
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "halted"
    ghost_calls = [c for c in driver.calls if c["task_id"] == "ghost"]
    assert len(ghost_calls) == 3

    retries_dir = _mission_dir(rroot, mission_id) / "retries"
    attempt_files = sorted(retries_dir.glob("ghost.attempt-*.md"))
    assert len(attempt_files) == 3
    briefs = []
    for p in attempt_files:
        rec = yaml.safe_load(p.read_text(encoding="utf-8").split("---", 2)[1])
        assert rec["failure_state"] == "empty"
        assert rec["cause_class"] == "transient"
        briefs.append(rec["brief_text"])
    assert len(set(briefs)) == 1, "transient cause should NOT force a brief change"


# ---------------------------------------------------------------------------
# 3. A verifier BLOCK halts the run — no further stages.
# ---------------------------------------------------------------------------

def test_run_verifier_block_halts_before_next_stage(engine, rroot, monkeypatch):
    monkeypatch.chdir(rroot)
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("t1", verifier_required=True)]},
        {"stage": 2, "gate_in": "research-before-build", "parallel": False,
         "tasks": [_task("t2", depends_on=["t1"])]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    driver = engine.FakeDriver(script={"t1": {"mode": "good"}, "t1.verify": {"mode": "blocking"}})
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "halted"
    assert result["stages_completed"] == 0
    assert "BLOCKED" in result["halt_reason"]
    assert result["escalation_path"]

    # Stage 2's task was NEVER dispatched.
    call_ids = [c["task_id"] for c in driver.calls]
    assert call_ids == ["t1", "t1.verify"]
    assert "t2" not in call_ids

    esc_path = Path(result["escalation_path"])
    esc_fm = yaml.safe_load(esc_path.read_text(encoding="utf-8").split("---", 2)[1])
    assert esc_fm["reason"] == "verifier_block"
    assert esc_fm["verdict"]["disposition"] == "BLOCK"

    mission = engine._read_mission_record(rroot, mission_id)
    assert mission["state"] == "code-red"

    # The BLOCKing verdict itself was schema-valid (a genuine BLOCK, not a
    # schema-miss masquerading as one) — dogfood it too.
    verdict_path = _mission_dir(rroot, mission_id) / "returns" / "t1.verify.verdict.json"
    assert verdict_path.exists()
    v = _run_cli(rroot, "validate", "verdict", str(verdict_path))
    assert v.returncode == 0, v.stdout + v.stderr


# ---------------------------------------------------------------------------
# 4. Gate not cleared -> immediate halt, zero dispatch calls ("never start
#    early").
# ---------------------------------------------------------------------------

def test_run_halts_when_gate_not_cleared_and_dispatches_nothing(engine, rroot, monkeypatch):
    monkeypatch.chdir(rroot)
    mission_id = _new_mission(engine, rroot)  # gates all pending by default

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("t1")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    driver = engine.FakeDriver(default_mode="good")
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "halted"
    assert "not cleared" in result["halt_reason"]
    assert result["escalation_path"] is None
    assert driver.calls == []

    # No mutation to the mission record at all.
    mission = engine._read_mission_record(rroot, mission_id)
    assert mission["state"] == "intake"


# ---------------------------------------------------------------------------
# 5. Refusals that stop the WHOLE run (RunError), not a per-task failure.
# ---------------------------------------------------------------------------

def test_run_refuses_invalid_crew_plan(engine, rroot):
    mission_id = _new_mission(engine, rroot)
    bad_plan_path = rroot / "bad.json"
    bad_plan_path.write_text(json.dumps({"crew_plan": {"mission_id": mission_id}}), encoding="utf-8")

    driver = engine.FakeDriver(default_mode="good")
    with pytest.raises(engine.RunError, match="failed validation"):
        engine._do_run(rroot, bad_plan_path, driver, by="tester")
    assert driver.calls == []


def test_run_refuses_when_mission_record_missing(engine, rroot):
    plan = _crew_plan("2026-07-07-does-not-exist", [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("t1")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)
    driver = engine.FakeDriver(default_mode="good")
    with pytest.raises(engine.RunError, match="mission new"):
        engine._do_run(rroot, plan_path, driver, by="tester")
    assert driver.calls == []


# ---------------------------------------------------------------------------
# 6. CLI wiring smoke — `tessctl run --driver fake --fake-script ...` via
#    subprocess (argparse, dispatch table, exit codes).
# ---------------------------------------------------------------------------

def test_run_cli_fake_driver_end_to_end(engine, rroot):
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("solo")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    script_path = rroot / "fake-script.json"
    script_path.write_text(json.dumps({"solo": {"mode": "good"}}), encoding="utf-8")

    r = _run_cli(rroot, "run", str(plan_path), "--driver", "fake", "--fake-script", str(script_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "status: complete" in r.stdout
    assert "1/1 stage(s) completed" in r.stdout

    rj = _run_cli(rroot, "run", str(plan_path), "--driver", "fake", "--fake-script", str(script_path), "--json")
    assert rj.returncode == 0
    obj = json.loads(rj.stdout)
    assert obj["status"] == "complete"


def test_run_cli_unknown_driver_rejected(rroot):
    plan_path = rroot / "plan.json"
    plan_path.write_text("{}", encoding="utf-8")
    r = _run_cli(rroot, "run", str(plan_path), "--driver", "bogus")
    assert r.returncode == 2  # argparse `choices=` usage error


# ---------------------------------------------------------------------------
# 7. missions/** (including returns/ and escalations/) stays invisible to
#    doctor/verify/lock --check after a full run — same discipline Goal #5
#    already proved for retries/.
# ---------------------------------------------------------------------------

_COPY_IGNORE = shutil.ignore_patterns(".git", "tests", ".pytest_cache", "__pycache__", ".github")


@pytest.fixture
def real_root(tmp_path):
    dst = tmp_path / "os"
    shutil.copytree(REPO_ROOT, dst, ignore=_COPY_IGNORE)
    return dst


def test_missions_returns_and_escalations_invisible_to_doctor_verify_lock_check(engine, real_root, monkeypatch):
    monkeypatch.chdir(real_root)
    mission_id = _new_mission(engine, real_root, "Run Region Regression Check")
    evidence = real_root / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, real_root, mission_id, evidence)

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("flaky")]},
    ])
    plan_path = _write_plan(real_root, "plan.json", plan)

    driver = engine.FakeDriver(script={"flaky": {"mode": "schema-missing"}})
    result = engine._do_run(real_root, plan_path, driver, by="tester")
    assert result["status"] == "halted"  # exercises returns/ AND escalations/ AND retries/

    d = _run_cli(real_root, "doctor")
    assert d.returncode == 0, d.stdout + d.stderr
    assert "missions/" not in d.stdout

    v = _run_cli(real_root, "verify")
    assert v.returncode == 0, v.stdout + v.stderr

    lc = _run_cli(real_root, "lock", "--check")
    assert lc.returncode == 0, lc.stdout + lc.stderr

    manifest = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))
    assert "missions/**" in manifest["never_touch"]


# ---------------------------------------------------------------------------
# 8. Driver-level failure (process crash / non-zero exit) is classified and
#    retried the same as a schema-miss.
# ---------------------------------------------------------------------------

def test_run_driver_error_mode_classified_and_retried(engine, rroot, monkeypatch):
    monkeypatch.chdir(rroot)
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("crashy")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    driver = engine.FakeDriver(script={"crashy": {"mode": "error", "error": "simulated crash"}})
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "halted"
    crashy_calls = [c for c in driver.calls if c["task_id"] == "crashy"]
    assert len(crashy_calls) == 3

    retries_dir = _mission_dir(rroot, mission_id) / "retries"
    attempt_files = sorted(retries_dir.glob("crashy.attempt-*.md"))
    assert len(attempt_files) == 3
    for p in attempt_files:
        rec = yaml.safe_load(p.read_text(encoding="utf-8").split("---", 2)[1])
        assert rec["failure_state"] == "error"
        assert rec["cause_class"] == "transient"


# ---------------------------------------------------------------------------
# 9. ClaudeCliDriver always passes an explicit --allowed-tools allowlist —
#    a regression guard for the exact bug the live smoke run caught: a
#    headless `claude -p` dispatch with no tool allowlist silently DENIES a
#    tool call (e.g. Write) with no prompt surfaced, burning the retry cap
#    on failure_state: empty before this was ever diagnosed as a permission
#    issue rather than a driver/prompt bug.
# ---------------------------------------------------------------------------

def test_claude_cli_driver_always_passes_allowed_tools(engine, tmp_path, monkeypatch):
    captured_cmds = []

    class _FakeCompletedProcess:
        returncode = 0
        stdout = json.dumps({
            "type": "result", "subtype": "success", "is_error": False,
            "result": "done", "total_cost_usd": 0.01,
        }) + "\n"
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        return _FakeCompletedProcess()

    monkeypatch.setattr(engine.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(engine.subprocess, "run", _fake_run)

    driver = engine.ClaudeCliDriver(cwd=tmp_path)
    brief = {
        "objective": "x", "output_contract": "x", "tools_sources_constraints": "x",
        "not_responsible_for": "x", "milestones": [], "escalation_trigger": "x",
        "_task_id": "t", "_mission_id": "m", "_contract_type": "return-manifest",
        "_return_manifest_path": "missions/m/returns/t.return.json", "_root": str(tmp_path),
    }
    result = driver.dispatch(brief, output_schema=None)

    assert result["ok"] is True
    assert len(captured_cmds) == 1
    cmd = captured_cmds[0]
    assert "--allowed-tools" in cmd
    idx = cmd.index("--allowed-tools")
    allowlist = cmd[idx + 1]
    for tool in ("Read", "Write", "Edit", "Bash"):
        assert tool in allowlist

    # Never the blanket bypass — this driver's default is an explicit
    # allowlist, not --dangerously-skip-permissions.
    assert "--dangerously-skip-permissions" not in cmd


def test_claude_cli_driver_allowed_tools_overridable(engine, tmp_path, monkeypatch):
    captured_cmds = []

    class _FakeCompletedProcess:
        returncode = 0
        stdout = json.dumps({
            "type": "result", "subtype": "success", "is_error": False,
            "result": "done", "total_cost_usd": 0.01,
        }) + "\n"
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        return _FakeCompletedProcess()

    monkeypatch.setattr(engine.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(engine.subprocess, "run", _fake_run)

    driver = engine.ClaudeCliDriver(cwd=tmp_path, allowed_tools=["Write"])
    brief = {
        "objective": "x", "output_contract": "x", "tools_sources_constraints": "x",
        "not_responsible_for": "x", "milestones": [], "escalation_trigger": "x",
        "_task_id": "t", "_mission_id": "m", "_contract_type": "return-manifest",
        "_return_manifest_path": "missions/m/returns/t.return.json", "_root": str(tmp_path),
    }
    driver.dispatch(brief, output_schema=None)

    cmd = captured_cmds[0]
    idx = cmd.index("--allowed-tools")
    assert cmd[idx + 1] == "Write"
