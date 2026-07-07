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
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT, ENGINE_SRC, MANIFEST_SRC, sign_verdict_for_test

CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rroot(tmp_path):
    """A minimal synthetic Tess OS root: all seven contract schemas `run`
    touches (brief is $ref'd from crew-plan; return-manifest/verdict/
    mission/retry are all read/written during a run; policy.schema.json is
    needed for the HIGH-1(b) verdict-signature check's `_gate_load_policy`
    call, even for plans with no verifier — the check only fires per-task),
    `tess.manifest.json` with the real `missions/**` never_touch entry, and
    the engine itself."""
    root = tmp_path / "os"
    contracts_dir = root / "core" / "contracts"
    contracts_dir.mkdir(parents=True)
    for fname in ("brief.schema.json", "crew-plan.schema.json", "verdict.schema.json",
                  "return-manifest.schema.json", "mission.schema.json", "retry.schema.json",
                  "policy.schema.json"):
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


# ---------------------------------------------------------------------------
# HIGH-1(b) test scaffolding — a real core/policy/policy.yaml registering
# real GPG verifier identities (mirrors tests/test_gate_spine.py's own
# `_policy_with_verifier_keys` onboarding convention), so a verdict signed
# with `sign_verdict_for_test` can actually verify inside `tessctl run`'s
# own signature check (`_run_check_verdict_signature` /
# `_gate_verify_verdict_signature`).
# ---------------------------------------------------------------------------

def _write_policy_with_keys(root, keys, *, only=None):
    """Writes core/policy/policy.yaml registering the given verifier GPG
    identities' real fingerprint + bundled public-key file. `only`
    restricts registration to a subset of names (default: register all of
    `keys`) — used by tests that need a policy which recognizes SOME
    verifiers but not others."""
    keys_dir = root / ".tess" / "keys" / "verifiers"
    keys_dir.mkdir(parents=True, exist_ok=True)
    verifier_keys = {}
    for name in (only if only is not None else list(keys.keys())):
        key = keys[name]
        asc_path = keys_dir / f"{name.lower()}.asc"
        asc_path.write_text(key.pubkey_armored, encoding="utf-8")
        verifier_keys[name] = {
            "fingerprint": key.fpr,
            "public_key_file": f".tess/keys/verifiers/{name.lower()}.asc",
        }
    policy_dir = root / "core" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "policy.yaml").write_text(
        yaml.safe_dump({
            "policy": {"version": 1, "rules": [], "hard_floor_rules": [], "verifier_keys": verifier_keys},
        }),
        encoding="utf-8",
    )


def _signed_verdict(engine, key, *, verifier="Reid", disposition="APPROVE",
                     findings=None, primary_artifacts=None):
    """Builds a schema-valid verdict dict and signs it with `key` (a
    SimpleNamespace from the `verifier_gpg_keys` fixture), using the
    engine's own `verdict_canonical_bytes()` so the signature verifies
    exactly like a real `tessctl verdict sign` output would."""
    if findings is None:
        findings = [{
            "severity": "CRITICAL", "location": "fake:1", "finding": "Scripted BLOCK finding",
            "risk": "Test-scripted risk", "fix": "n/a — scripted for test coverage",
        }] if disposition == "BLOCK" else []
    tally = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev = str(f.get("severity", "")).lower()
        if sev in tally:
            tally[sev] += 1
    verdict = {
        "verifier": verifier,
        "output_domain": "test dispatch",
        "primary_artifacts_read": primary_artifacts or ["artifact.txt"],
        "findings": findings,
        "severity_counts": tally,
        "summary_line": (
            f"Reviewed. Found {tally['critical']} CRITICAL, {tally['high']} HIGH, "
            f"{tally['medium']} MEDIUM, {tally['low']} LOW."
        ),
        "disposition": disposition,
    }
    verdict["signature"] = sign_verdict_for_test(engine, verdict, key)
    return verdict


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


def _frontmatter_text(raw_text):
    """Extract the YAML front-matter block from a `---\\n<fm>---\\n\\n<body>`
    file — LINE-ANCHORED (`^---$` at the start of a line), not a naive
    substring split. A naive `text.split('---', 2)[1]` breaks the moment the
    front-matter's own content contains the substring '---' anywhere — e.g.
    a PGP-armored `-----BEGIN PGP SIGNATURE-----` block embedded in an
    escalation record's `verdict.signature.signature_armored`, exactly what
    HIGH-1(b)'s signed-verdict test fixtures legitimately produce."""
    parts = re.split(r"(?m)^---[ \t]*$", raw_text, maxsplit=2)
    return parts[1]


# ---------------------------------------------------------------------------
# 1. A 2-stage plan runs end-to-end: dispatch -> validate -> verify -> next.
# ---------------------------------------------------------------------------

def test_run_two_stage_plan_end_to_end_success(engine, rroot, verifier_gpg_keys, monkeypatch):
    monkeypatch.chdir(rroot)
    _write_policy_with_keys(rroot, verifier_gpg_keys)
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

    # HIGH-1(b): a mandatory verifier's verdict must be SIGNED by a
    # registered key to satisfy `run` now — FakeDriver's own "good" mode
    # verdict has no signature, so this test (a genuine passing-path
    # regression guard, not just a HIGH-1 proof test) provides one via the
    # scripted "instance" override.
    signed_verdict = _signed_verdict(engine, verifier_gpg_keys["Reid"], disposition="APPROVE")
    driver = engine.FakeDriver(script={"build.verify": {"mode": "good", "instance": signed_verdict}})
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
        rec = yaml.safe_load(_frontmatter_text(p.read_text(encoding="utf-8")))
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
    esc_fm = yaml.safe_load(_frontmatter_text(esc_path.read_text(encoding="utf-8")))
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
        rec = yaml.safe_load(_frontmatter_text(p.read_text(encoding="utf-8")))
        assert rec["failure_state"] == "empty"
        assert rec["cause_class"] == "transient"
        briefs.append(rec["brief_text"])
    assert len(set(briefs)) == 1, "transient cause should NOT force a brief change"


# ---------------------------------------------------------------------------
# 3. A verifier BLOCK halts the run — no further stages.
# ---------------------------------------------------------------------------

def test_run_verifier_block_halts_before_next_stage(engine, rroot, verifier_gpg_keys, monkeypatch):
    monkeypatch.chdir(rroot)
    _write_policy_with_keys(rroot, verifier_gpg_keys)
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

    # HIGH-1(b): the BLOCK verdict must ALSO be signed to be trusted — a
    # forged/unsigned BLOCK is no more trustworthy than a forged APPROVE;
    # the signature check applies to every verdict regardless of
    # disposition.
    blocking_verdict = _signed_verdict(engine, verifier_gpg_keys["Reid"], disposition="BLOCK")
    driver = engine.FakeDriver(script={
        "t1": {"mode": "good"}, "t1.verify": {"mode": "blocking", "instance": blocking_verdict},
    })
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
    esc_fm = yaml.safe_load(_frontmatter_text(esc_path.read_text(encoding="utf-8")))
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
        rec = yaml.safe_load(_frontmatter_text(p.read_text(encoding="utf-8")))
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
    for tool in ("Read", "Write", "Edit", "Grep", "Glob"):
        assert tool in allowlist

    # MEDIUM-1 FIX (Fable adversarial review): Bash is NOT part of the
    # default allowlist — arbitrary shell execution is never granted
    # silently by default, only via an explicit `allowed_tools=[...]` opt-in
    # (see test_claude_cli_driver_allowed_tools_overridable below).
    assert "Bash" not in allowlist

    # Never the blanket bypass — this driver's default is an explicit
    # allowlist, not --dangerously-skip-permissions.
    assert "--dangerously-skip-permissions" not in cmd


def test_claude_cli_driver_default_allowed_tools_excludes_bash(engine):
    """MEDIUM-1 FIX proof (module-level constant, independent of any
    subprocess plumbing): Bash must not be in the default least-privilege
    allowlist. WITHOUT the fix, `CLAUDE_CLI_DEFAULT_ALLOWED_TOOLS` includes
    'Bash' and this assertion fails."""
    assert "Bash" not in engine.CLAUDE_CLI_DEFAULT_ALLOWED_TOOLS
    for tool in ("Read", "Write", "Edit", "Grep", "Glob"):
        assert tool in engine.CLAUDE_CLI_DEFAULT_ALLOWED_TOOLS


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


# ---------------------------------------------------------------------------
# 10. HIGH-1(a) — pre-planted verdict must not survive a stale-artifact
#     check (the core hole; Fable's exact reproduction).
# ---------------------------------------------------------------------------

def test_run_pre_planted_verdict_does_not_survive_stale_check(engine, rroot, verifier_gpg_keys, monkeypatch):
    """HIGH-1(a) FIX proof — the core hole Fable reproduced: pre-plant a
    schema-valid, SIGNED, disposition:APPROVE verdict at the EXACT
    contracted path a verifier dispatch is about to write to, then let that
    dispatch write NOTHING. WITHOUT the fix (no unlink-before-dispatch in
    `_run_dispatch_with_retry`), `_run_check_artifact` reads the
    pre-planted file straight off disk — schema, lint, and signature all
    pass, since it's a genuinely valid, signed verdict — and `run` reports
    `status: complete`, exactly Fable's reproduction. WITH the fix, the
    pre-plant is removed before the verifier's own dispatch attempt, that
    attempt writes nothing, and `run` correctly halts on retry-cap
    exhaustion instead."""
    monkeypatch.chdir(rroot)
    _write_policy_with_keys(rroot, verifier_gpg_keys)
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("build", verifier_required=True, verifier_agent="Reid")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    verdict_path_rel = engine._run_artifact_path(mission_id, "build.verify", "verdict")
    verdict_path = rroot / verdict_path_rel
    verdict_path.parent.mkdir(parents=True, exist_ok=True)
    pre_planted = _signed_verdict(engine, verifier_gpg_keys["Reid"], disposition="APPROVE")
    verdict_path.write_text(json.dumps(pre_planted), encoding="utf-8")
    assert verdict_path.exists()

    # "build" dispatches normally; its verifier ("build.verify") writes
    # NOTHING — if the pre-plant survives, `run` would still see the valid
    # signed APPROVE sitting there and pass.
    driver = engine.FakeDriver(script={
        "build": {"mode": "good"},
        "build.verify": {"mode": "missing-file"},
    })
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "halted", (
        "HIGH-1(a) regression: pre-planted verdict survived into the check -- " + json.dumps(result)
    )
    assert result["escalation_path"]
    # The pre-planted file itself must be GONE, not merely ignored.
    assert not verdict_path.exists()


# ---------------------------------------------------------------------------
# 11. HIGH-1(b) — the signed-verdict trust model must apply INSIDE `run`,
#     not just `tessctl gate`: unsigned, wrong-key, and no-registered-key
#     verdicts must all fail to satisfy a mandatory verifier.
# ---------------------------------------------------------------------------

def test_run_unsigned_verdict_rejected_by_signature_check(engine, rroot, verifier_gpg_keys, monkeypatch):
    """HIGH-1(b) FIX proof: a schema-valid, disposition:APPROVE verdict
    with NO `signature` block must not satisfy a mandatory verifier —
    `run` must apply the SAME signed-verdict trust model `tessctl gate`
    already does. WITHOUT the fix, `_run_check_artifact` only
    schema/lint-validates a verdict and this exact scenario reports
    `status: complete`."""
    monkeypatch.chdir(rroot)
    _write_policy_with_keys(rroot, verifier_gpg_keys)
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("build", verifier_required=True, verifier_agent="Reid")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    # FakeDriver's own "good" mode verdict has no `signature` field at all.
    driver = engine.FakeDriver(script={"build": {"mode": "good"}, "build.verify": {"mode": "good"}})
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "halted", (
        "HIGH-1(b) regression: an unsigned verdict satisfied the mandatory verifier -- "
        + json.dumps(result)
    )
    assert result["escalation_path"]


def test_run_verdict_signed_by_wrong_key_rejected(engine, rroot, verifier_gpg_keys, monkeypatch):
    """HIGH-1(b) FIX proof: a verdict that claims `verifier: Reid` but is
    signed with a DIFFERENT, still-registered verifier's key (Quinn's)
    must not satisfy the mandatory verifier — a real, valid GPG signature
    alone is not enough; it must be made by the CLAIMED verifier's own
    registered key (C3 exact match, per `_gate_verify_verdict_signature`)."""
    monkeypatch.chdir(rroot)
    _write_policy_with_keys(rroot, verifier_gpg_keys)
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("build", verifier_required=True, verifier_agent="Reid")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    # `verifier` field says "Reid", but the signature is genuinely Quinn's.
    wrong_key_verdict = _signed_verdict(
        engine, verifier_gpg_keys["Quinn"], verifier="Reid", disposition="APPROVE"
    )
    driver = engine.FakeDriver(script={
        "build": {"mode": "good"},
        "build.verify": {"mode": "good", "instance": wrong_key_verdict},
    })
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "halted", (
        "HIGH-1(b) regression: a verdict signed by the WRONG verifier's key satisfied the check -- "
        + json.dumps(result)
    )
    assert result["escalation_path"]


def test_run_required_verifier_fails_closed_with_empty_verifier_keys(
    engine, rroot, verifier_gpg_keys, monkeypatch
):
    """Fable's explicit callout: 'If verifier_keys is empty [fail-closed],
    a required-verifier stage cannot pass without a signed verdict —
    that's correct fail-closed behavior.' Proves it directly: a
    core/policy/policy.yaml IS present but registers NO verifier keys at
    all; a REAL, validly-signed APPROVE verdict (a genuine GPG signature,
    not a forgery) still cannot satisfy the verifier, because
    `policy.verifier_keys` has no entry to check the signature against —
    fail-closed by omission, an honestly-documented outcome, not a bug."""
    monkeypatch.chdir(rroot)
    policy_dir = rroot / "core" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "policy.yaml").write_text(
        yaml.safe_dump({"policy": {"version": 1, "rules": [], "hard_floor_rules": [], "verifier_keys": {}}}),
        encoding="utf-8",
    )
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("build", verifier_required=True, verifier_agent="Reid")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    signed = _signed_verdict(engine, verifier_gpg_keys["Reid"], verifier="Reid", disposition="APPROVE")
    driver = engine.FakeDriver(script={
        "build": {"mode": "good"},
        "build.verify": {"mode": "good", "instance": signed},
    })
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "halted"
    assert result["escalation_path"]


def test_run_verifier_identity_mismatch_treated_as_failed_verification(
    engine, rroot, verifier_gpg_keys, monkeypatch
):
    """Incidental hardening alongside HIGH-1: `_run_check_artifact`'s
    signature check proves SOME registered verifier's key signed the
    verdict — not that it's the SPECIFIC verifier this task's crew-plan
    actually required. A validly-signed verdict genuinely produced by a
    DIFFERENT (still-registered) verifier's own identity than
    `verifier.agent` must be treated as a failed verification, not
    silently accepted as satisfying this task's mandatory verifier."""
    monkeypatch.chdir(rroot)
    _write_policy_with_keys(rroot, verifier_gpg_keys)
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("build", verifier_required=True, verifier_agent="Reid")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    # Genuinely, validly signed BY Quinn, claiming to BE Quinn (a real,
    # registered verifier — not a wrong-key forgery). The crew-plan
    # required Reid.
    quinn_verdict = _signed_verdict(engine, verifier_gpg_keys["Quinn"], verifier="Quinn", disposition="APPROVE")
    driver = engine.FakeDriver(script={
        "build": {"mode": "good"},
        "build.verify": {"mode": "good", "instance": quinn_verdict},
    })
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "halted"
    assert "verifier" in result["halt_reason"].lower()
    assert result["escalation_path"]
    esc_fm = yaml.safe_load(_frontmatter_text(Path(result["escalation_path"]).read_text(encoding="utf-8")))
    assert esc_fm["reason"] == "verifier_identity_mismatch"


# ---------------------------------------------------------------------------
# 12. HIGH-2 — the GATE NAME enforces mandatory verification, not the
#     task author's self-declared risk flags.
# ---------------------------------------------------------------------------

def test_run_refuses_plan_with_externally_visible_gate_but_no_required_verifier(engine, rroot):
    """HIGH-2 FIX proof: reproduces Fable's exact scenario — brief 'Publish
    the public marketing site to prod', in a stage gated on
    'verification-before-externally-visible', with `verifier.required:
    false` and none of the self-declared risk flags set. `run` must REFUSE
    this plan outright — the GATE NAME enforces the verifier, not the task
    author's self-classification. WITHOUT the fix, this plan validates
    clean and `run` would complete with NO verdict ever dispatched."""
    plan = _crew_plan("2026-07-07-publish-site", [
        {
            "stage": 1, "gate_in": "verification-before-externally-visible", "parallel": False,
            "tasks": [_task("publish-site", verifier_required=False)],
        },
    ])
    plan["crew_plan"]["stages"][0]["tasks"][0]["brief"]["objective"] = (
        "Publish the public marketing site to prod."
    )
    plan_path = _write_plan(rroot, "plan.json", plan)

    driver = engine.FakeDriver(default_mode="good")
    with pytest.raises(engine.RunError, match="verification-before-externally-visible"):
        engine._do_run(rroot, plan_path, driver, by="tester")
    assert driver.calls == []


def test_run_accepts_plan_with_externally_visible_gate_and_properly_wired_verifier(engine, rroot):
    """Positive control for HIGH-2: the SAME gate name with a task that IS
    fully wired for mandatory verification (verifier.required: true, a
    real verifier agent, non-empty primary_artifacts) must NOT be refused
    by the new lint — proving the check is scoped to the actual bypass,
    not a blanket ban on this gate name."""
    plan = _crew_plan("2026-07-07-publish-site-ok", [
        {
            "stage": 1, "gate_in": "verification-before-externally-visible", "parallel": False,
            "tasks": [_task("publish-site", verifier_required=True, verifier_agent="Reid")],
        },
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)
    crew_plan = engine._run_load_and_validate_crew_plan(rroot, plan_path)
    assert crew_plan["mission_id"] == "2026-07-07-publish-site-ok"


# ---------------------------------------------------------------------------
# 13. HIGH-3 — task.id / mission_id path-traversal payloads must be
#     rejected at BOTH the schema layer AND `run`'s own defense-in-depth
#     containment check.
# ---------------------------------------------------------------------------

def test_crew_plan_schema_rejects_task_id_path_traversal(rroot):
    """HIGH-3 FIX proof (schema layer): Fable's exact reproduction —
    `id: "../../../../../../tmp/PWNED"` — must now fail `tessctl validate
    crew-plan`. WITHOUT the `pattern` constraint on Task.id, this exact
    payload validates PASS."""
    plan = _crew_plan("2026-07-07-traversal-test", [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("../../../../../../tmp/PWNED")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)
    r = _run_cli(rroot, "validate", "crew-plan", str(plan_path))
    assert r.returncode != 0, r.stdout + r.stderr


def test_crew_plan_schema_rejects_mission_id_path_traversal(rroot):
    """HIGH-3 FIX proof (schema layer, mission_id half): the identical
    traversal payload in `mission_id` must also fail validation — `run`
    builds `missions/<mission_id>/...` directly from this field too."""
    plan = _crew_plan("../../../../tmp/PWNED-mission", [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("t1")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)
    r = _run_cli(rroot, "validate", "crew-plan", str(plan_path))
    assert r.returncode != 0, r.stdout + r.stderr


def test_run_refuses_task_id_path_traversal_at_load(engine, rroot):
    """HIGH-3 FIX proof (via `_do_run` directly, not just the standalone
    `tessctl validate` CLI): the traversal payload is refused BEFORE any
    dispatch — `driver.calls` stays empty."""
    mission_id = _new_mission(engine, rroot)
    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("../../../../../../tmp/PWNED")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)
    driver = engine.FakeDriver(default_mode="good")
    with pytest.raises(engine.RunError, match="failed validation"):
        engine._do_run(rroot, plan_path, driver, by="tester")
    assert driver.calls == []


def test_run_containment_assert_rejects_escaping_path(engine, tmp_path):
    """HIGH-3 defense-in-depth proof: `_run_assert_contained` itself — the
    belt-and-suspenders layer Fable's fix explicitly asked for — refuses a
    path that resolves outside `missions/`, independent of the schema
    layer entirely (e.g. a hand-authored instance file that skipped
    `tessctl validate`, or any future code path that forgets to)."""
    root = tmp_path / "os"
    (root / "missions").mkdir(parents=True)
    escaping = root / "missions" / ".." / ".." / "PWNED" / "evil.json"
    with pytest.raises(engine.RunError, match="escapes"):
        engine._run_assert_contained(root, escaping, what="test write")

    # A legitimate, within-bounds path is accepted and returned resolved.
    ok_path = root / "missions" / "m1" / "returns" / "t1.return.json"
    resolved = engine._run_assert_contained(root, ok_path, what="test write")
    assert resolved == ok_path.resolve()


def test_run_check_artifact_refuses_path_escaping_missions_root(engine, tmp_path):
    """HIGH-3 defense-in-depth proof, at the actual call site: even a
    `_run_check_artifact` call bypassing the crew-plan schema layer
    entirely (calling the RUN-region function directly, as a stand-in for
    any future/alternate code path that constructed `path_rel` from an
    unvalidated id) is refused, never silently read from outside root."""
    root = tmp_path / "os"
    (root / "core" / "contracts").mkdir(parents=True)
    for fname in ("return-manifest.schema.json", "verdict.schema.json"):
        shutil.copy2(CONTRACTS_SRC / fname, root / "core" / "contracts" / fname)
    raw = {"ok": True, "timed_out": False}
    with pytest.raises(engine.RunError, match="escapes"):
        engine._run_check_artifact(root, "../../../../tmp/PWNED.return.json", "return-manifest", raw)


# ---------------------------------------------------------------------------
# 14. MEDIUM-2 — `run`'s own artifact-existence check must be ROOT-relative,
#     not CWD-relative.
# ---------------------------------------------------------------------------

def test_run_check_artifact_rejects_return_manifest_whose_declared_artifact_is_cwd_relative_only(
    engine, rroot, monkeypatch
):
    """MEDIUM-2 FIX proof: `_lint_return_manifest`'s own existence check
    (`Path(path).exists()`) is CWD-relative, not root-relative. `tessctl
    run`'s OWN artifact check must not inherit that blind spot: a
    return-manifest declaring an `artifacts[].path` that happens to exist
    relative to the tessctl PROCESS's CWD, but does NOT exist under `root`,
    must still be rejected. WITHOUT the fix, running from a CWD that
    happens to contain a same-named file lets a non-existent-under-root
    artifact pass (H4's own 'fabricated artifact' guarantee silently
    defeated)."""
    mission_id = _new_mission(engine, rroot)

    # A decoy directory, SIBLING to root, that becomes the tessctl
    # PROCESS's CWD — containing a file at the SAME relative path the
    # return-manifest will (falsely) declare as its artifact.
    decoy_cwd = rroot.parent / "decoy-cwd"
    decoy_cwd.mkdir()
    decoy_relative = "not-really-under-root/output.txt"
    (decoy_cwd / "not-really-under-root").mkdir()
    (decoy_cwd / decoy_relative).write_text("decoy content\n", encoding="utf-8")
    assert not (rroot / decoy_relative).exists()  # confirm the REAL root has no such file

    monkeypatch.chdir(decoy_cwd)  # tessctl PROCESS's CWD != root

    return_path_rel = engine._run_artifact_path(mission_id, "t1", "return-manifest")
    instance = {
        "task_id": "t1", "mission_id": mission_id, "agent": "fake-agent",
        "status": "complete", "self_reported_complete": True,
        "artifacts": [{"path": decoy_relative, "description": "decoy"}],
        "claims": [{"claim": "done", "inferred": False, "evidence": decoy_relative}],
        "flags": [],
    }
    return_path = rroot / return_path_rel
    return_path.parent.mkdir(parents=True, exist_ok=True)
    return_path.write_text(json.dumps(instance), encoding="utf-8")

    raw = {"ok": True, "timed_out": False}
    ok, violations, failure_state, cause_class, checked = engine._run_check_artifact(
        rroot, return_path_rel, "return-manifest", raw
    )
    assert ok is False, (
        "MEDIUM-2 regression: a return-manifest whose declared artifact only exists "
        "relative to CWD (not root) was accepted"
    )
    assert any("root" in v.lower() for v in violations), violations
