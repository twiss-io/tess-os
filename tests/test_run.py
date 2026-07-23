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
                     findings=None, primary_artifacts=None,
                     covers_paths=None, artifact_hashes=None):
    """Builds a schema-valid verdict dict and signs it with `key` (a
    SimpleNamespace from the `verifier_gpg_keys` fixture), using the
    engine's own `verdict_canonical_bytes()` so the signature verifies
    exactly like a real `tessctl verdict sign` output would.

    `covers_paths`/`artifact_hashes` (LOW FIX test scaffolding, gate-parity
    residual): OMITTED entirely by default — exactly the pre-fix shape every
    OTHER test in this file still legitimately uses, since those tests all
    fail (or are meant to fail) at signature/identity checks that run
    BEFORE `_run_check_verdict_artifact_binding` ever fires. Only the tests
    that need a verdict to actually clear the new binding check pass them
    explicitly."""
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
    if covers_paths is not None:
        verdict["covers_paths"] = covers_paths
    if artifact_hashes is not None:
        verdict["artifact_hashes"] = artifact_hashes
    verdict["signature"] = sign_verdict_for_test(engine, verdict, key)
    return verdict


def _real_artifact_return_instance(mission_id, task_id, artifact_rel, *, description="Real output"):
    """A schema-valid return-manifest `instance` dict declaring exactly ONE
    real, test-controlled artifact at `artifact_rel` (the caller is
    responsible for actually writing that file to disk BEFORE this instance
    is used, so `_run_check_return_manifest_artifacts_exist_under_root`'s
    existence check — and, with the LOW fix, the artifact-hash binding
    check's own hashing — both see genuine on-disk content). LOW FIX test
    scaffolding: used in place of FakeDriver's own self-referencing default
    return-manifest (`artifacts: [{"path": <the manifest's own path>}]`)
    whenever a test needs to predict, in advance, the EXACT content whose
    git-blob-hash a verdict's `artifact_hashes` must match — a self-
    referencing default's content depends on FakeDriver's own internal
    dict shape, which these tests should not have to replicate."""
    return {
        "task_id": task_id, "mission_id": mission_id, "agent": "fake-agent",
        "status": "complete", "self_reported_complete": True,
        "artifacts": [{"path": artifact_rel, "description": description}],
        "claims": [{"claim": f"{task_id} done", "inferred": False, "evidence": artifact_rel}],
        "flags": [],
    }


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

    # LOW FIX (gate-parity) test scaffolding: "build"'s real artifact must
    # exist on disk BEFORE the run, so its git-blob-hash is known in
    # advance and the signed verdict below can genuinely bind to it.
    build_artifact_rel = "build-artifact.txt"
    (rroot / build_artifact_rel).write_text("Real build artifact content.\n", encoding="utf-8")
    build_return_instance = _real_artifact_return_instance(mission_id, "build", build_artifact_rel)
    build_hash = engine._run_artifact_current_blob_hash(rroot, build_artifact_rel)

    # HIGH-1(b): a mandatory verifier's verdict must be SIGNED by a
    # registered key to satisfy `run` now — FakeDriver's own "good" mode
    # verdict has no signature, so this test (a genuine passing-path
    # regression guard, not just a HIGH-1 proof test) provides one via the
    # scripted "instance" override. LOW FIX (gate-parity): it must ALSO
    # genuinely cover+hash "build"'s real artifact now, or the new binding
    # check would (correctly) reject even this genuine same-task verdict.
    signed_verdict = _signed_verdict(
        engine, verifier_gpg_keys["Reid"], disposition="APPROVE",
        primary_artifacts=[build_artifact_rel],
        covers_paths=[build_artifact_rel],
        artifact_hashes={build_artifact_rel: build_hash},
    )
    driver = engine.FakeDriver(script={
        "build": {"mode": "good", "instance": build_return_instance},
        "build.verify": {"mode": "good", "instance": signed_verdict},
    })
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

    prior_commitment = None
    for i, p in enumerate(attempt_files, start=1):
        v = _run_cli(rroot, "validate", "retry", str(p))
        assert v.returncode == 0, f"{p} failed validate:\n{v.stdout}{v.stderr}"
        rec = yaml.safe_load(_frontmatter_text(p.read_text(encoding="utf-8")))
        assert rec["attempt"] == i
        assert rec["failure_state"] == "degraded"
        assert rec["cause_class"] == "context-gap"
        commitment = (rec["brief_digest_sha256"], rec["brief_length"])
        assert "brief_text" not in rec
        if prior_commitment is not None:
            assert commitment != prior_commitment, "consecutive attempts must have DIFFERENT commitments"
        prior_commitment = commitment

    # Escalation record: projected reason/attempt codes only, and the mission
    # record's state flipped to code-red.  Runtime identifiers stay out of
    # durable front matter; correlation uses opaque labels.
    esc_path = Path(result["escalation_path"])
    assert esc_path.exists()
    esc_fm = yaml.safe_load(_frontmatter_text(esc_path.read_text(encoding="utf-8")))
    assert esc_fm["reason_code"] == "retry_cap_exhausted"
    assert esc_fm["mission_label"].startswith("mission-")
    assert esc_fm["task_label"].startswith("task-")
    assert "mission_id" not in esc_fm and "task" not in esc_fm
    esc_body = esc_path.read_text(encoding="utf-8")
    assert "Per-attempt analysis" in esc_body
    assert "attempt 1" in esc_body and "attempt 2" in esc_body and "attempt 3" in esc_body

    mission = engine._read_mission_record(rroot, mission_id)
    assert mission["state"] == "code-red"


def test_run_escalation_persists_only_projected_diagnostics(engine, rroot, monkeypatch):
    """Untrusted validator/tool/verdict values must never become YAML history."""
    monkeypatch.chdir(rroot)
    mission_id = _new_mission(engine, rroot)
    raw = "P73_ESCALATION_SENTINEL_GPG_GIT_ARTIFACT_HASH"

    path = engine._run_write_escalation(
        rroot,
        mission_id,
        "safe-task",
        "retry_cap_exhausted",
        {
            "attempts": [{
                "attempt": 1,
                "failure_state": "degraded",
                "cause_class": "context-gap",
                "brief_change_code": "changed-brief",
                "driver_diagnostic": raw,
            }],
            "last_violations": [
                f"gpg and git failed for artifact /private/{raw}; sha256={raw}",
            ],
            "verdict": {
                "verifier": raw,
                "disposition": "BLOCK",
                "summary_line": raw,
                "covers_paths": [f"artifacts/{raw}.json"],
                "artifact_hashes": {f"artifacts/{raw}.json": raw},
                "signature": {"signature_armored": raw},
            },
            "expected_verifier": raw,
            "actual_verifier": raw,
            "unrecognized_raw_detail": raw,
        },
        by=raw,
    )

    persisted = path.read_text(encoding="utf-8")
    fm = yaml.safe_load(_frontmatter_text(persisted))
    assert raw not in persisted
    assert "artifact_hashes" not in persisted and "covers_paths" not in persisted
    assert "last_violations" not in fm and "verdict" not in fm
    assert fm["last_violation_count"] == 1
    assert fm["last_violation_codes"] == ["VERDICT_SIGNATURE_INVALID"]
    assert fm["verdict_code"] == "VERDICT_BLOCK"
    assert fm["verdict_verifier_label"].startswith("verifier-")
    assert fm["expected_verifier_label"].startswith("verifier-")
    assert fm["actual_verifier_label"].startswith("verifier-")
    assert fm["halted_by_label"].startswith("actor-")


def test_run_retry_escalation_projects_raw_last_violations(engine, rroot, monkeypatch):
    """The retry path passes raw violations only to the projection boundary."""
    monkeypatch.chdir(rroot)
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)
    raw = "P73_RETRY_ESCALATION_RAW_GPG_GIT_PATH_HASH"

    def raw_failure(*_args, **_kwargs):
        return (
            False,
            [f"gpg and git failure at artifacts/{raw}.json sha256={raw}"],
            "degraded",
            "context-gap",
            None,
        )

    monkeypatch.setattr(engine, "_run_check_artifact", raw_failure)
    plan = _crew_plan(mission_id, [{
        "stage": 1, "gate_in": "intake-before-anything", "parallel": False,
        "tasks": [_task("raw-diagnostic")],
    }])
    result = engine._do_run(
        rroot, _write_plan(rroot, "raw-diagnostic-plan.json", plan),
        engine.FakeDriver(default_mode="good"), by="tester",
    )

    assert result["status"] == "halted"
    persisted = Path(result["escalation_path"]).read_text(encoding="utf-8")
    fm = yaml.safe_load(_frontmatter_text(persisted))
    assert raw not in persisted
    assert fm["last_violation_count"] == 1
    assert fm["last_violation_codes"] == ["VERDICT_SIGNATURE_INVALID"]


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
    commitments = []
    for p in attempt_files:
        rec = yaml.safe_load(_frontmatter_text(p.read_text(encoding="utf-8")))
        assert rec["failure_state"] == "empty"
        assert rec["cause_class"] == "transient"
        commitments.append((rec["brief_digest_sha256"], rec["brief_length"]))
        assert "brief_text" not in rec
    assert len(set(commitments)) == 1, "transient cause should NOT force a brief change"


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
    assert esc_fm["reason_code"] == "verifier_block"
    assert esc_fm["verdict_code"] == "VERDICT_BLOCK"
    assert esc_fm["verdict_verifier_label"].startswith("verifier-")
    assert "verdict" not in esc_fm

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

    # LOW FIX (gate-parity) test scaffolding: Quinn's verdict must
    # genuinely cover+hash "build"'s real artifact — otherwise the NEW
    # binding check (not the identity-mismatch check this test targets)
    # would be what rejects it, and the test would no longer be proving
    # what its name says it proves.
    build_artifact_rel = "build-artifact.txt"
    (rroot / build_artifact_rel).write_text("Real build artifact content.\n", encoding="utf-8")
    build_return_instance = _real_artifact_return_instance(mission_id, "build", build_artifact_rel)
    build_hash = engine._run_artifact_current_blob_hash(rroot, build_artifact_rel)

    # Genuinely, validly signed BY Quinn, claiming to BE Quinn (a real,
    # registered verifier — not a wrong-key forgery). The crew-plan
    # required Reid.
    quinn_verdict = _signed_verdict(
        engine, verifier_gpg_keys["Quinn"], verifier="Quinn", disposition="APPROVE",
        primary_artifacts=[build_artifact_rel],
        covers_paths=[build_artifact_rel],
        artifact_hashes={build_artifact_rel: build_hash},
    )
    driver = engine.FakeDriver(script={
        "build": {"mode": "good", "instance": build_return_instance},
        "build.verify": {"mode": "good", "instance": quinn_verdict},
    })
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "halted"
    assert "verifier" in result["halt_reason"].lower()
    assert result["escalation_path"]
    esc_fm = yaml.safe_load(_frontmatter_text(Path(result["escalation_path"]).read_text(encoding="utf-8")))
    assert esc_fm["reason_code"] == "verifier_identity_mismatch"
    assert esc_fm["expected_verifier_label"].startswith("verifier-")
    assert esc_fm["actual_verifier_label"].startswith("verifier-")


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
    """The shared artifact boundary resolves evidence from root, never CWD."""
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


def test_run_fake_no_verifier_halts_for_external_return_manifest_artifact(engine, rroot, monkeypatch):
    """A fake internal task cannot complete by citing `/etc/hosts` as output."""
    monkeypatch.chdir(rroot)
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)
    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("external-artifact", verifier_required=False)]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)
    external_return = {
        "task_id": "external-artifact", "mission_id": mission_id, "agent": "fake-agent",
        "status": "complete", "self_reported_complete": True,
        "artifacts": [{"path": "/etc/hosts", "description": "external host file"}],
        "claims": [{"claim": "done", "evidence": "/etc/hosts", "inferred": False}],
        "flags": [],
    }
    driver = engine.FakeDriver(script={
        "external-artifact": {"mode": "good", "instance": external_return},
    })

    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "halted", result
    assert result["status"] != "complete"
    assert "attempt cap" in result["halt_reason"]
    retries = sorted((_mission_dir(rroot, mission_id) / "retries").glob("external-artifact.attempt-*.md"))
    assert len(retries) == 3
    # Retry records are deliberately privacy-safe projections: they prove the
    # failed task was retried and halted without persisting the attacker-supplied
    # external path in mission state.
    retry_text = retries[-1].read_text(encoding="utf-8")
    assert "/etc/hosts" not in retry_text
    assert "failure_state: degraded" in retry_text
    assert len([call for call in driver.calls if call["task_id"] == "external-artifact"]) == 3
    assert all(not call["task_id"].endswith(".verify") for call in driver.calls)


def test_run_artifact_hash_keeps_opened_file_during_directory_swap(engine, tmp_path, monkeypatch):
    """A directory-to-symlink swap cannot redirect verdict binding outside root."""
    root = tmp_path / "os"
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True)
    trusted = b"trusted in-root evidence\n"
    (artifacts / "evidence.md").write_bytes(trusted)

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evidence.md").write_bytes(b"external evidence\n")
    expected = subprocess.check_output(
        ["git", "hash-object", str(artifacts / "evidence.md")], text=True
    ).strip()

    real_open = engine.os.open
    swapped = False

    def swap_directory_before_final_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if not swapped and str(path) == "evidence.md" and dir_fd is not None:
            artifacts.rename(root / "artifacts-original")
            artifacts.symlink_to(outside, target_is_directory=True)
            swapped = True
        if dir_fd is None:
            return real_open(path, flags, mode)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(engine.os, "open", swap_directory_before_final_open)

    observed = engine._run_artifact_current_blob_hash(root, "artifacts/evidence.md")

    assert swapped, "regression setup did not replace the checked directory"
    assert (root / "artifacts").is_symlink()
    assert observed == expected, "verdict binding must read the originally opened in-root file"


# ---------------------------------------------------------------------------
# 15. LOW (Fable re-verification, gate-parity residual) — `run`'s verdict
#     check must bind a verdict's `covers_paths`/`artifact_hashes` to what
#     THIS task actually produced, not just verify its signature. Without
#     this, a validly-signed APPROVE verdict genuinely written for a
#     DIFFERENT task's artifacts could be replayed to satisfy THIS task's
#     mandatory verifier — the one gap left between `run`'s trust model and
#     `tessctl gate`'s own diff-bound covering-verdict check.
# ---------------------------------------------------------------------------

def test_run_verdict_artifact_binding_rejects_cross_task_replay(
    engine, rroot, verifier_gpg_keys, monkeypatch
):
    """LOW FIX proof — the residual this PR closes: a validly-signed,
    disposition:APPROVE verdict written for a DIFFERENT task's real artifact
    ("task A") — correct covers_paths, correct artifact_hashes, a real GPG
    signature from a registered key, exactly what a genuine verifier flow
    produces — is scripted as THIS task's ("build", standing in for "task
    B") verifier response instead. "build" produced its OWN, genuinely
    different artifact (different path AND different content) that the
    replayed verdict's covers_paths/artifact_hashes says nothing about.
    WITHOUT `_run_check_verdict_artifact_binding`, the signature check alone
    is satisfied (it IS a real, validly-signed, registered-key APPROVE) and
    this cross-task replay would silently clear the mandatory verifier. WITH
    the fix, "build"'s real artifact is not covered/hashed by the replayed
    verdict at all, so the binding check rejects it and the run halts on
    retry-cap exhaustion instead of completing."""
    monkeypatch.chdir(rroot)
    _write_policy_with_keys(rroot, verifier_gpg_keys)
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)

    # "Task A" — some OTHER task/context entirely, reviewed and approved
    # elsewhere. A real, validly-signed, genuinely-covering verdict for
    # TASK A's own artifact.
    task_a_artifact = rroot / "task-a-artifact.txt"
    task_a_artifact.write_text("Task A's real, previously-reviewed output.\n", encoding="utf-8")
    task_a_hash = engine._run_artifact_current_blob_hash(rroot, "task-a-artifact.txt")
    replayed_verdict = _signed_verdict(
        engine, verifier_gpg_keys["Reid"], disposition="APPROVE",
        primary_artifacts=["task-a-artifact.txt"],
        covers_paths=["task-a-artifact.txt"],
        artifact_hashes={"task-a-artifact.txt": task_a_hash},
    )

    # "build" (standing in for "task B") produces its OWN, genuinely
    # different real artifact — different path, different content, never
    # mentioned anywhere in the replayed verdict above.
    build_artifact_rel = "task-b-artifact.txt"
    (rroot / build_artifact_rel).write_text("Task B's real, DIFFERENT output.\n", encoding="utf-8")
    build_return_instance = _real_artifact_return_instance(mission_id, "build", build_artifact_rel)

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("build", verifier_required=True, verifier_agent="Reid")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    driver = engine.FakeDriver(script={
        "build": {"mode": "good", "instance": build_return_instance},
        "build.verify": {"mode": "good", "instance": replayed_verdict},
    })
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "halted", (
        "LOW regression: a verdict signed for and covering a DIFFERENT task's artifact "
        "satisfied THIS task's mandatory verifier (cross-task verdict replay) -- "
        + json.dumps(result)
    )
    assert result["escalation_path"]

    # The retry ledger deliberately does NOT persist the rejection detail:
    # it stores only a brief commitment, so a verifier/driver-controlled
    # failure cannot be retained as plaintext in mission records.  The halt
    # above proves the replay still cannot clear verification.
    # Filename note: the retry ledger's on-disk key is `_retry_task_slug`'s
    # kebab-slug of the task id (MEDIUM-1, Fable integrity review, part of
    # goal-mission-ledger's own history) — "build.verify" slugifies to
    # "build-verify" (dot is non-alnum, collapsed to a hyphen like every
    # other separator), NOT the literal dotted string.
    retries_dir = _mission_dir(rroot, mission_id) / "retries"
    attempt_files = sorted(retries_dir.glob("build-verify.attempt-*.md"))
    assert attempt_files, "expected at least one logged retry attempt for build.verify"
    combined = "\n".join(p.read_text(encoding="utf-8") for p in attempt_files)
    assert "brief_text" not in combined
    assert "artifact-hash binding" not in combined


def test_run_verdict_artifact_binding_accepts_genuine_covering_verdict(
    engine, rroot, verifier_gpg_keys, monkeypatch
):
    """Happy-path companion proof: a verdict that IS genuinely signed for,
    and correctly covers+hashes, THIS task's own real artifact must still
    pass — the binding check is not a blanket rejection, only a targeted
    one. A verifier that writes the verdict for the artifacts it actually
    reviewed (the only way a real, honest verifier flow ever produces a
    verdict — see docs/GATE_QUICKSTART.md's own `git hash-object` recipe)
    clears the binding check exactly like it always should."""
    monkeypatch.chdir(rroot)
    _write_policy_with_keys(rroot, verifier_gpg_keys)
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)

    artifact_rel = "genuine-artifact.txt"
    (rroot / artifact_rel).write_text("Genuinely reviewed output.\n", encoding="utf-8")
    return_instance = _real_artifact_return_instance(mission_id, "build", artifact_rel)
    current_hash = engine._run_artifact_current_blob_hash(rroot, artifact_rel)
    genuine_verdict = _signed_verdict(
        engine, verifier_gpg_keys["Reid"], disposition="APPROVE",
        primary_artifacts=[artifact_rel],
        covers_paths=[artifact_rel],
        artifact_hashes={artifact_rel: current_hash},
    )

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("build", verifier_required=True, verifier_agent="Reid")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    driver = engine.FakeDriver(script={
        "build": {"mode": "good", "instance": return_instance},
        "build.verify": {"mode": "good", "instance": genuine_verdict},
    })
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "complete", result
    assert all(t["status"] == "complete" for t in result["tasks"])

    build_verdict_path = _mission_dir(rroot, mission_id) / "returns" / "build.verify.verdict.json"
    assert build_verdict_path.exists()
    v = _run_cli(rroot, "validate", "verdict", str(build_verdict_path))
    assert v.returncode == 0, v.stdout + v.stderr


def test_run_verdict_artifact_binding_skipped_for_block_disposition(
    engine, rroot, verifier_gpg_keys, monkeypatch
):
    """Gate-parity scope proof: the binding check applies ONLY to
    disposition:APPROVE verdicts, mirroring `tessctl gate`'s own
    `_gate_find_covering_approved_verdicts`, which never even considers a
    BLOCK verdict for covering-checks — only an APPROVE claims to clear
    anything. A validly-signed BLOCK with NO covers_paths/artifact_hashes at
    all must still halt the run on its own terms (a genuine BLOCK), not be
    rejected for a binding mismatch it was never trying to claim in the
    first place."""
    monkeypatch.chdir(rroot)
    _write_policy_with_keys(rroot, verifier_gpg_keys)
    mission_id = _new_mission(engine, rroot)
    evidence = rroot / "evidence.md"
    evidence.write_text("proof\n", encoding="utf-8")
    _clear_all_five_gates(engine, rroot, mission_id, evidence)

    artifact_rel = "build-artifact.txt"
    (rroot / artifact_rel).write_text("Real build artifact content.\n", encoding="utf-8")
    return_instance = _real_artifact_return_instance(mission_id, "build", artifact_rel)

    # No covers_paths/artifact_hashes at all — would fail the binding check
    # if it applied to BLOCK, exactly like the pre-fix default shape.
    blocking_verdict = _signed_verdict(engine, verifier_gpg_keys["Reid"], disposition="BLOCK")

    plan = _crew_plan(mission_id, [
        {"stage": 1, "gate_in": "intake-before-anything", "parallel": False,
         "tasks": [_task("build", verifier_required=True, verifier_agent="Reid")]},
    ])
    plan_path = _write_plan(rroot, "plan.json", plan)

    driver = engine.FakeDriver(script={
        "build": {"mode": "good", "instance": return_instance},
        "build.verify": {"mode": "blocking", "instance": blocking_verdict},
    })
    result = engine._do_run(rroot, plan_path, driver, by="tester")

    assert result["status"] == "halted"
    assert "BLOCKED" in result["halt_reason"], result["halt_reason"]
    esc_fm = yaml.safe_load(_frontmatter_text(Path(result["escalation_path"]).read_text(encoding="utf-8")))
    assert esc_fm["reason_code"] == "verifier_block"
