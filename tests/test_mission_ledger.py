"""
Goal #5 — `tessctl mission` + `gate-status` + the typed-retry ledger
(mission records as code).

Spec: docs/ULTIMATE_FRAMEWORK_PLAN.md §C3 (Gate system module) + §C4 (Typed
Retry module); conductor/doctrine.md "The Gates" table; conductor/
mission-states.md; conductor/subagent-failure-protocol.md. Contracts:
core/contracts/mission.schema.json, core/contracts/retry.schema.json.
Implementation: the MISSION LEDGER region of .tess/bin/tessctl (directly
below cmd_gate()).

Coverage (per the dispatch brief's explicit acceptance list):
  * `mission new` scaffolds mission.md + mission.json, both of which pass
    `tessctl validate mission <file>` (dogfood) — proven both via the CLI
    and by calling the engine's own self-validate helper directly.
  * mission id derivation (date-slug) + collision suffixing.
  * `mission status` (human + --json) and `gate-status` (read-only report).
  * `gate clear` REFUSES without --evidence (argparse-level, exit 2) and
    REFUSES when --evidence does not exist on disk (exit 1, no mutation) —
    and records who/when/evidence in the mission record once it succeeds.
  * `retry check`/`retry log` BLOCK a 4th attempt (the 3-attempt cap).
  * `retry check`/`retry log` BLOCK an identical-brief retry for a
    non-transient cause, but ALLOW a changed-brief retry or a same-brief
    transient-cause retry.
  * every written retry attempt file passes `tessctl validate retry`.
  * the mission lint (`_lint_mission`): duplicate/missing/unrecognized gate
    names, and a cleared gate whose evidence path does not exist on disk.
  * `missions/**` stays invisible to `doctor`/`verify`/`lock --check` (it is
    in tess.manifest.json's never_touch, not owned_globs — no keystone
    tracking) even after mission/gate/retry activity has occurred.
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

HAS_GIT = shutil.which("git") is not None
HAS_GPG = shutil.which("gpg") is not None
# `gate clear` dispatches through the top-level "gate" command, which
# _TOOL_REQUIREMENTS hard-requires git+gpg for uniformly across ALL of its
# subcommands (same coarse-but-precedented per-command granularity
# test_gate_spine.py's own module docstring already documents) — "mission"
# and "retry" carry no such requirement, only "gate clear" does.
HAS_GATE_TOOLS = HAS_GIT and HAS_GPG


# ---------------------------------------------------------------------------
# Fixtures — a MINIMAL synthetic root (not a full repo copy): mission/gate/
# retry commands never touch owned_globs/never_touch/tess.lock at all, they
# only need tess.manifest.json to exist (find_tess_root()) and the two new
# schemas at core/contracts/ (cmd_validate's load path).
# ---------------------------------------------------------------------------

@pytest.fixture
def mroot(tmp_path):
    root = tmp_path / "os"
    contracts_dir = root / "core" / "contracts"
    contracts_dir.mkdir(parents=True)
    for fname in ("mission.schema.json", "retry.schema.json"):
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


def _run(root, *args, input_text=None):
    env = {**os.environ, "TESS_ROOT": str(root)}
    return subprocess.run(
        [sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
        cwd=str(root), env=env, capture_output=True, text=True, input=input_text,
    )


def _mission_dir(root, mission_id):
    return root / "missions" / mission_id


# ---------------------------------------------------------------------------
# `tessctl mission new` — scaffold + dogfood validate
# ---------------------------------------------------------------------------

def test_mission_new_scaffolds_md_and_json_both_valid(mroot):
    r = _run(mroot, "mission", "new", "Revenue conversation Q3 push", "--outcome-type", "build")
    assert r.returncode == 0, r.stdout + r.stderr

    # id = <today>-<slug>
    ids = [p.name for p in (mroot / "missions").iterdir() if p.is_dir()]
    assert len(ids) == 1
    mission_id = ids[0]
    assert mission_id.endswith("-revenue-conversation-q3-push")
    assert mission_id[:4].isdigit()  # YYYY- prefix

    md = _mission_dir(mroot, mission_id) / "mission.md"
    js = _mission_dir(mroot, mission_id) / "mission.json"
    assert md.exists() and js.exists()
    assert (_mission_dir(mroot, mission_id) / "retries" / ".gitkeep").exists()

    for f in (md, js):
        v = _run(mroot, "validate", "mission", str(f))
        assert v.returncode == 0, f"{f} failed validate:\n{v.stdout}\n{v.stderr}"

    # Both serializations carry the SAME fields.
    md_fm = yaml.safe_load(md.read_text(encoding="utf-8").split("---", 2)[1])
    js_obj = json.loads(js.read_text(encoding="utf-8"))
    assert md_fm == js_obj
    assert js_obj["outcome_type"] == "build"
    assert js_obj["state"] == "intake"
    assert len(js_obj["gates"]) == 5
    assert all(g["cleared"] is False for g in js_obj["gates"])


def test_mission_new_id_collision_gets_suffixed(mroot):
    r1 = _run(mroot, "mission", "new", "Same Name")
    r2 = _run(mroot, "mission", "new", "Same Name")
    assert r1.returncode == 0 and r2.returncode == 0
    ids = sorted(p.name for p in (mroot / "missions").iterdir() if p.is_dir())
    assert len(ids) == 2
    assert ids[0] != ids[1]
    assert ids[1] == ids[0] + "-2"


def test_mission_new_empty_slug_refused(mroot):
    r = _run(mroot, "mission", "new", "!!! ???")
    assert r.returncode != 0
    assert "no usable characters" in (r.stdout + r.stderr)
    assert not (mroot / "missions").exists() or not list((mroot / "missions").iterdir())


def test_mission_status_human_and_json(mroot):
    _run(mroot, "mission", "new", "Status Test Mission")
    mission_id = next(p.name for p in (mroot / "missions").iterdir() if p.is_dir())

    r = _run(mroot, "mission", "status", mission_id)
    assert r.returncode == 0
    assert "0/5 cleared" in r.stdout
    assert "intake-before-anything" in r.stdout

    rj = _run(mroot, "mission", "status", mission_id, "--json")
    assert rj.returncode == 0
    obj = json.loads(rj.stdout)
    assert obj["id"] == mission_id
    assert len(obj["gates"]) == 5


def test_mission_status_unknown_id_exits_nonzero(mroot):
    r = _run(mroot, "mission", "status", "does-not-exist")
    assert r.returncode != 0
    assert "no mission record found" in (r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# `tessctl gate-status` — read-only report
# ---------------------------------------------------------------------------

def test_gate_status_reports_all_pending_then_cleared(mroot):
    _run(mroot, "mission", "new", "Gate Status Mission")
    mission_id = next(p.name for p in (mroot / "missions").iterdir() if p.is_dir())

    r = _run(mroot, "gate-status", mission_id)
    assert r.returncode == 0
    assert "0/5 gates cleared" in r.stdout
    assert "[pending]" in r.stdout

    rj = _run(mroot, "gate-status", mission_id, "--json")
    gates = json.loads(rj.stdout)["gates"]
    assert len(gates) == 5 and all(g["cleared"] is False for g in gates)


# ---------------------------------------------------------------------------
# `tessctl gate clear` — the write side. REFUSES without real evidence.
# ---------------------------------------------------------------------------

pytestmark_gate = pytest.mark.skipif(not HAS_GATE_TOOLS, reason="git + gpg required (tessctl gate's blanket tool check)")


@pytestmark_gate
def test_gate_clear_refuses_without_evidence_flag(mroot):
    _run(mroot, "mission", "new", "Clear Mission A")
    mission_id = next(p.name for p in (mroot / "missions").iterdir() if p.is_dir())

    r = _run(mroot, "gate", "clear", "intake-before-anything", "--mission", mission_id)
    assert r.returncode != 0
    assert "--evidence" in (r.stdout + r.stderr)

    # No mutation happened.
    status = json.loads(_run(mroot, "mission", "status", mission_id, "--json").stdout)
    assert all(g["cleared"] is False for g in status["gates"])


@pytestmark_gate
def test_gate_clear_refuses_when_evidence_path_missing(mroot):
    _run(mroot, "mission", "new", "Clear Mission B")
    mission_id = next(p.name for p in (mroot / "missions").iterdir() if p.is_dir())

    r = _run(mroot, "gate", "clear", "intake-before-anything",
             "--mission", mission_id, "--evidence", "no-such-file.md")
    assert r.returncode != 0
    assert "REFUSED" in (r.stdout + r.stderr)
    assert "does not exist" in (r.stdout + r.stderr)

    status = json.loads(_run(mroot, "mission", "status", mission_id, "--json").stdout)
    assert all(g["cleared"] is False for g in status["gates"])


@pytestmark_gate
def test_gate_clear_succeeds_with_real_evidence_and_records_who_when(mroot):
    _run(mroot, "mission", "new", "Clear Mission C")
    mission_id = next(p.name for p in (mroot / "missions").iterdir() if p.is_dir())
    evidence = mroot / "leah-research-brief.md"
    evidence.write_text("# Research brief\n\nFindings...\n", encoding="utf-8")

    r = _run(mroot, "gate", "clear", "research-before-build",
             "--mission", mission_id, "--evidence", str(evidence), "--by", "leah")
    assert r.returncode == 0, r.stdout + r.stderr

    js = json.loads((_mission_dir(mroot, mission_id) / "mission.json").read_text(encoding="utf-8"))
    gate = next(g for g in js["gates"] if g["name"] == "research-before-build")
    assert gate["cleared"] is True
    assert gate["cleared_by"] == "leah"
    assert gate["cleared_at"]
    assert gate["evidence"] == "leah-research-brief.md"  # stored repo-relative

    # Both serializations stay in sync, and both still validate.
    md = _mission_dir(mroot, mission_id) / "mission.md"
    md_fm = yaml.safe_load(md.read_text(encoding="utf-8").split("---", 2)[1])
    assert md_fm == js
    for f in (md, _mission_dir(mroot, mission_id) / "mission.json"):
        v = _run(mroot, "validate", "mission", str(f))
        assert v.returncode == 0, v.stdout + v.stderr


@pytestmark_gate
def test_gate_clear_unknown_gate_name_rejected_by_argparse(mroot):
    _run(mroot, "mission", "new", "Clear Mission D")
    mission_id = next(p.name for p in (mroot / "missions").iterdir() if p.is_dir())
    evidence = mroot / "e.md"
    evidence.write_text("x", encoding="utf-8")

    r = _run(mroot, "gate", "clear", "not-a-real-gate",
             "--mission", mission_id, "--evidence", str(evidence))
    assert r.returncode == 2  # argparse `choices=` usage error


@pytestmark_gate
def test_gate_clear_unknown_mission_refused(mroot):
    evidence = mroot / "e.md"
    evidence.write_text("x", encoding="utf-8")
    r = _run(mroot, "gate", "clear", "intake-before-anything",
             "--mission", "does-not-exist", "--evidence", str(evidence))
    assert r.returncode != 0
    assert "no mission record found" in (r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# `tessctl retry log|check` — the typed-retry ledger
# ---------------------------------------------------------------------------

def _new_mission(mroot, name="Retry Mission"):
    _run(mroot, "mission", "new", name)
    return next(p.name for p in (mroot / "missions").iterdir() if p.is_dir())


def _brief(mroot, name, text):
    p = mroot / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_retry_check_cap_only_when_no_prior_attempts(mroot):
    mission_id = _new_mission(mroot)
    r = _run(mroot, "retry", "check", "taskX", "--mission", mission_id)
    assert r.returncode == 0
    assert "attempt 1" in r.stdout and "ALLOWED" in r.stdout


def test_retry_log_writes_valid_attempt_file(mroot):
    mission_id = _new_mission(mroot)
    brief = _brief(mroot, "brief1.md", "Investigate the failing test.")

    r = _run(mroot, "retry", "log", "taskX", "--mission", mission_id,
              "--cause", "context-gap", "--failure-state", "degraded", "--brief", brief)
    assert r.returncode == 0, r.stdout + r.stderr

    attempt = mroot / "missions" / mission_id / "retries" / "taskX.attempt-1.md"
    assert attempt.exists()
    v = _run(mroot, "validate", "retry", str(attempt))
    assert v.returncode == 0, v.stdout + v.stderr

    fm = yaml.safe_load(attempt.read_text(encoding="utf-8").split("---", 2)[1])
    assert fm["attempt"] == 1
    assert fm["cause_class"] == "context-gap"
    assert fm["failure_state"] == "degraded"
    assert fm["brief_text"] == "Investigate the failing test."
    assert fm["mission_id"] == mission_id


def test_retry_blocks_identical_brief_for_context_gap_but_allows_changed_brief(mroot):
    mission_id = _new_mission(mroot)
    brief_a = _brief(mroot, "brief-a.md", "Same wording every time.")
    brief_b = _brief(mroot, "brief-b.md", "Different wording — read the config first.")

    r1 = _run(mroot, "retry", "log", "taskY", "--mission", mission_id,
              "--cause", "context-gap", "--failure-state", "degraded", "--brief", brief_a)
    assert r1.returncode == 0, r1.stdout + r1.stderr

    # identical brief, non-transient cause -> BLOCKED (check AND log)
    check_same = _run(mroot, "retry", "check", "taskY", "--mission", mission_id,
                       "--cause", "context-gap", "--brief", brief_a)
    assert check_same.returncode == 1
    assert "BLOCKED" in check_same.stdout
    assert "same-brief retry forbidden" in check_same.stdout

    log_same = _run(mroot, "retry", "log", "taskY", "--mission", mission_id,
                     "--cause", "context-gap", "--failure-state", "degraded", "--brief", brief_a)
    assert log_same.returncode != 0
    assert "REFUSED" in (log_same.stdout + log_same.stderr)
    # No attempt-2 file was written by the refused call.
    assert not (mroot / "missions" / mission_id / "retries" / "taskY.attempt-2.md").exists()

    # changed brief, same non-transient cause -> ALLOWED
    check_changed = _run(mroot, "retry", "check", "taskY", "--mission", mission_id,
                          "--cause", "context-gap", "--brief", brief_b)
    assert check_changed.returncode == 0
    assert "ALLOWED" in check_changed.stdout

    log_changed = _run(mroot, "retry", "log", "taskY", "--mission", mission_id,
                        "--cause", "context-gap", "--failure-state", "degraded", "--brief", brief_b)
    assert log_changed.returncode == 0, log_changed.stdout + log_changed.stderr
    assert (mroot / "missions" / mission_id / "retries" / "taskY.attempt-2.md").exists()


def test_retry_allows_identical_brief_for_transient_cause(mroot):
    mission_id = _new_mission(mroot)
    brief_a = _brief(mroot, "brief-a.md", "Retry the flaky network call.")

    r1 = _run(mroot, "retry", "log", "taskZ", "--mission", mission_id,
              "--cause", "transient", "--failure-state", "timeout", "--brief", brief_a)
    assert r1.returncode == 0

    check_same_transient = _run(mroot, "retry", "check", "taskZ", "--mission", mission_id,
                                 "--cause", "transient", "--brief", brief_a)
    assert check_same_transient.returncode == 0
    assert "ALLOWED" in check_same_transient.stdout

    r2 = _run(mroot, "retry", "log", "taskZ", "--mission", mission_id,
              "--cause", "transient", "--failure-state", "timeout", "--brief", brief_a)
    assert r2.returncode == 0, r2.stdout + r2.stderr


def test_retry_blocks_a_4th_attempt(mroot):
    mission_id = _new_mission(mroot)
    briefs = [_brief(mroot, f"brief-{i}.md", f"Attempt number {i} wording.") for i in range(1, 5)]

    for i in range(3):
        r = _run(mroot, "retry", "log", "taskCap", "--mission", mission_id,
                  "--cause", "wrong-approach", "--failure-state", "error", "--brief", briefs[i])
        assert r.returncode == 0, r.stdout + r.stderr

    check4 = _run(mroot, "retry", "check", "taskCap", "--mission", mission_id)
    assert check4.returncode == 1
    assert "attempt 4" in check4.stdout
    assert "BLOCKED" in check4.stdout
    assert "cap" in check4.stdout

    log4 = _run(mroot, "retry", "log", "taskCap", "--mission", mission_id,
                "--cause", "wrong-approach", "--failure-state", "error", "--brief", briefs[3])
    assert log4.returncode != 0
    assert "REFUSED" in (log4.stdout + log4.stderr)
    assert not (mroot / "missions" / mission_id / "retries" / "taskCap.attempt-4.md").exists()

    remaining = sorted((mroot / "missions" / mission_id / "retries").glob("taskCap.attempt-*.md"))
    assert len(remaining) == 3


def test_retry_log_missing_mission_refused(mroot):
    brief = _brief(mroot, "b.md", "text")
    r = _run(mroot, "retry", "log", "taskA", "--mission", "does-not-exist",
              "--cause", "transient", "--failure-state", "error", "--brief", brief)
    assert r.returncode != 0
    assert "no mission record found" in (r.stdout + r.stderr)


def test_retry_log_missing_brief_file_refused(mroot):
    mission_id = _new_mission(mroot)
    r = _run(mroot, "retry", "log", "taskA", "--mission", mission_id,
              "--cause", "transient", "--failure-state", "error", "--brief", "no-such-brief.md")
    assert r.returncode != 0
    assert "not found" in (r.stdout + r.stderr)


def test_retry_check_requires_cause_and_brief_together(mroot):
    mission_id = _new_mission(mroot)
    brief = _brief(mroot, "b.md", "text")
    r1 = _run(mroot, "retry", "check", "taskA", "--mission", mission_id, "--cause", "transient")
    assert r1.returncode != 0
    r2 = _run(mroot, "retry", "check", "taskA", "--mission", mission_id, "--brief", brief)
    assert r2.returncode != 0


# ---------------------------------------------------------------------------
# Lint — `_lint_mission` (engine-level, no subprocess needed)
# ---------------------------------------------------------------------------

def _valid_mission_instance():
    return {
        "id": "2026-07-07-test-mission",
        "name": "Test Mission",
        "created_at": "2026-07-07T00:00:00Z",
        "state": "intake",
        "gates": [
            {"name": g, "cleared": False, "cleared_by": None, "cleared_at": None, "evidence": None}
            for g in (
                "intake-before-anything",
                "research-before-build",
                "crew-before-deploy",
                "review-before-synthesis",
                "verification-before-externally-visible",
            )
        ],
    }


def test_lint_mission_valid_instance_passes(engine):
    inst = _valid_mission_instance()
    assert engine._lint_mission(inst) == []


def test_lint_mission_missing_gate_flagged(engine):
    inst = _valid_mission_instance()
    inst["gates"] = inst["gates"][:-1]  # drop verification-before-externally-visible
    violations = engine._lint_mission(inst)
    assert any("missing canonical gate" in v for v in violations)


def test_lint_mission_duplicate_gate_flagged(engine):
    inst = _valid_mission_instance()
    inst["gates"].append(dict(inst["gates"][0]))
    violations = engine._lint_mission(inst)
    assert any("duplicate gate name" in v for v in violations)


def test_lint_mission_unrecognized_gate_flagged(engine):
    inst = _valid_mission_instance()
    inst["gates"][0] = {"name": "made-up-gate", "cleared": False,
                         "cleared_by": None, "cleared_at": None, "evidence": None}
    violations = engine._lint_mission(inst)
    assert any("unrecognized gate name" in v for v in violations)


def test_lint_mission_cleared_gate_with_missing_evidence_file_flagged(engine, tmp_path):
    inst = _valid_mission_instance()
    inst["gates"][0]["cleared"] = True
    inst["gates"][0]["cleared_by"] = "ada"
    inst["gates"][0]["cleared_at"] = "2026-07-07T00:00:00Z"
    inst["gates"][0]["evidence"] = str(tmp_path / "does-not-exist.md")
    violations = engine._lint_mission(inst)
    assert any("does not exist on disk" in v for v in violations)


def test_lint_mission_cleared_gate_with_real_evidence_file_passes(engine, tmp_path):
    real = tmp_path / "evidence.md"
    real.write_text("proof", encoding="utf-8")
    inst = _valid_mission_instance()
    inst["gates"][0]["cleared"] = True
    inst["gates"][0]["cleared_by"] = "ada"
    inst["gates"][0]["cleared_at"] = "2026-07-07T00:00:00Z"
    inst["gates"][0]["evidence"] = str(real)
    assert engine._lint_mission(inst) == []


def test_mission_schema_rejects_cleared_gate_without_evidence(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "mission")
    inst = _valid_mission_instance()
    inst["gates"][0]["cleared"] = True  # cleared_by/cleared_at/evidence left null
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations, "cleared:true with null cleared_by/cleared_at/evidence should fail schema"


def test_retry_schema_rejects_attempt_above_cap(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "retry")
    inst = {
        "mission_id": "2026-07-07-x", "task": "t", "attempt": 4,
        "failure_state": "error", "cause_class": "transient",
        "brief_text": "x", "logged_at": "2026-07-07T00:00:00Z",
    }
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations, "attempt: 4 should fail schema's maximum: 3"


# ---------------------------------------------------------------------------
# missions/** stays outside keystone tracking even after activity
# ---------------------------------------------------------------------------

_COPY_IGNORE = shutil.ignore_patterns(".git", "tests", ".pytest_cache", "__pycache__", ".github")


@pytest.fixture
def real_root(tmp_path):
    dst = tmp_path / "os"
    shutil.copytree(REPO_ROOT, dst, ignore=_COPY_IGNORE)
    return dst


def test_missions_dir_invisible_to_doctor_verify_lock_check(real_root):
    _run(real_root, "mission", "new", "Regression Check Mission")
    mission_id = next(p.name for p in (real_root / "missions").iterdir()
                       if p.is_dir() and p.name != "README.md")

    d = _run(real_root, "doctor")
    assert d.returncode == 0, d.stdout + d.stderr
    assert "missions/" not in d.stdout

    v = _run(real_root, "verify")
    assert v.returncode == 0, v.stdout + v.stderr

    lc = _run(real_root, "lock", "--check")
    assert lc.returncode == 0, lc.stdout + lc.stderr

    # Manifest actually declares it never_touch (static wiring check).
    manifest = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))
    assert "missions/**" in manifest["never_touch"]
