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

    # MEDIUM-1 (Fable integrity review): the ledger key is the NORMALIZED
    # task slug ("taskx", not "taskX") — see test_retry_ledger_key_is_
    # normalized_task_slug below for the dedicated proof of this.
    attempt = mroot / "missions" / mission_id / "retries" / "taskx.attempt-1.md"
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
    # No attempt-2 file was written by the refused call. (Ledger key is the
    # normalized task slug — "tasky", not "taskY" — MEDIUM-1.)
    assert not (mroot / "missions" / mission_id / "retries" / "tasky.attempt-2.md").exists()

    # changed brief, same non-transient cause -> ALLOWED
    check_changed = _run(mroot, "retry", "check", "taskY", "--mission", mission_id,
                          "--cause", "context-gap", "--brief", brief_b)
    assert check_changed.returncode == 0
    assert "ALLOWED" in check_changed.stdout

    log_changed = _run(mroot, "retry", "log", "taskY", "--mission", mission_id,
                        "--cause", "context-gap", "--failure-state", "degraded", "--brief", brief_b)
    assert log_changed.returncode == 0, log_changed.stdout + log_changed.stderr
    assert (mroot / "missions" / mission_id / "retries" / "tasky.attempt-2.md").exists()


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
    # Ledger key is the normalized task slug — "taskcap", not "taskCap" (MEDIUM-1).
    assert not (mroot / "missions" / mission_id / "retries" / "taskcap.attempt-4.md").exists()

    remaining = sorted((mroot / "missions" / mission_id / "retries").glob("taskcap.attempt-*.md"))
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


# =============================================================================
# Fable integrity review (PR #44 follow-up) — MEDIUM-1, MEDIUM-2, LOW-1, LOW-2.
# Each block below reproduces the exact evasion Fable found, proves it is now
# blocked, and (for the write-side findings) proves nothing escaped onto disk.
# =============================================================================


# ---------------------------------------------------------------------------
# MEDIUM-1 — the retry cap is keyed on a NORMALIZED task slug, not the
# literal caller-supplied string. Before the fix, `deploy` hitting the
# 3-attempt cap did not stop `deploy ` (trailing space) or `Deploy`
# (capitalized) from each opening a fresh, unused attempt-1.
# ---------------------------------------------------------------------------

def test_retry_ledger_key_is_normalized_task_slug(mroot):
    mission_id = _new_mission(mroot)
    brief = _brief(mroot, "brief.md", "Some brief text.")
    r = _run(mroot, "retry", "log", "Deploy Now", "--mission", mission_id,
             "--cause", "transient", "--failure-state", "error", "--brief", brief)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (mroot / "missions" / mission_id / "retries" / "deploy-now.attempt-1.md").exists()


def test_retry_cap_evasion_via_cosmetic_rename_is_blocked(mroot):
    """Fable's exact repro: 'deploy' hits the 3-attempt cap, then 'deploy '
    (trailing space) and 'Deploy' (capitalized) are each attempted.
    BEFORE the fix, each cosmetic variant scanned an EMPTY directory
    listing under its own literal spelling and opened a fresh attempt-1 —
    the cap tracked the caller's exact spelling, not the task. AFTER the
    fix, both variants share the SAME cap budget as 'deploy' and are
    blocked as a 4th attempt, with no new attempt file written for either."""
    mission_id = _new_mission(mroot)
    briefs = [_brief(mroot, f"deploy-brief-{i}.md", f"Deploy attempt {i}.") for i in range(1, 4)]

    for i in range(3):
        r = _run(mroot, "retry", "log", "deploy", "--mission", mission_id,
                  "--cause", "transient", "--failure-state", "error", "--brief", briefs[i])
        assert r.returncode == 0, r.stdout + r.stderr

    # Cap reached on the canonical spelling.
    check_canonical = _run(mroot, "retry", "check", "deploy", "--mission", mission_id)
    assert check_canonical.returncode == 1
    assert "attempt 4" in check_canonical.stdout and "BLOCKED" in check_canonical.stdout

    # Trailing-space cosmetic variant: must be BLOCKED as attempt 4, not
    # allowed through as a fresh attempt 1.
    check_space = _run(mroot, "retry", "check", "deploy ", "--mission", mission_id)
    assert check_space.returncode == 1, check_space.stdout
    assert "attempt 4" in check_space.stdout
    assert "BLOCKED" in check_space.stdout

    log_space = _run(mroot, "retry", "log", "deploy ", "--mission", mission_id,
                      "--cause", "transient", "--failure-state", "error", "--brief", briefs[0])
    assert log_space.returncode != 0
    assert "REFUSED" in (log_space.stdout + log_space.stderr)

    # Capitalized cosmetic variant: same story.
    check_cap = _run(mroot, "retry", "check", "Deploy", "--mission", mission_id)
    assert check_cap.returncode == 1, check_cap.stdout
    assert "attempt 4" in check_cap.stdout
    assert "BLOCKED" in check_cap.stdout

    log_cap = _run(mroot, "retry", "log", "Deploy", "--mission", mission_id,
                    "--cause", "transient", "--failure-state", "error", "--brief", briefs[0])
    assert log_cap.returncode != 0
    assert "REFUSED" in (log_cap.stdout + log_cap.stderr)

    # Exactly 3 attempt files exist total, ALL sharing the one normalized
    # slug — no fresh attempt-1 was ever created for a cosmetic variant.
    retries_dir = mroot / "missions" / mission_id / "retries"
    all_files = sorted(p.name for p in retries_dir.iterdir() if p.name != ".gitkeep")
    assert all_files == ["deploy.attempt-1.md", "deploy.attempt-2.md", "deploy.attempt-3.md"]


# ---------------------------------------------------------------------------
# MEDIUM-2 — `gate clear --evidence` (and `_lint_mission`'s re-check, run by
# `tessctl validate mission`) requires a REAL, REGULAR, NON-EMPTY file
# INSIDE the repo. Existence alone (the original check) was satisfied by an
# empty file, /dev/null, or a bare directory — Fable's exact repro: each of
# these "cleared" the gate.
# ---------------------------------------------------------------------------

@pytestmark_gate
def test_gate_clear_refuses_empty_evidence_file(mroot):
    mission_id = _new_mission(mroot, "Empty Evidence Mission")
    empty = mroot / "empty-evidence.md"
    empty.write_text("", encoding="utf-8")

    r = _run(mroot, "gate", "clear", "intake-before-anything",
              "--mission", mission_id, "--evidence", str(empty))
    assert r.returncode != 0
    assert "REFUSED" in (r.stdout + r.stderr)
    assert "empty" in (r.stdout + r.stderr).lower()

    status = json.loads(_run(mroot, "mission", "status", mission_id, "--json").stdout)
    assert all(g["cleared"] is False for g in status["gates"])


@pytestmark_gate
def test_gate_clear_refuses_directory_evidence(mroot):
    mission_id = _new_mission(mroot, "Directory Evidence Mission")
    a_dir = mroot / "a-directory"
    a_dir.mkdir()

    r = _run(mroot, "gate", "clear", "intake-before-anything",
              "--mission", mission_id, "--evidence", str(a_dir))
    assert r.returncode != 0
    assert "REFUSED" in (r.stdout + r.stderr)
    assert "not a regular file" in (r.stdout + r.stderr)

    status = json.loads(_run(mroot, "mission", "status", mission_id, "--json").stdout)
    assert all(g["cleared"] is False for g in status["gates"])


@pytestmark_gate
@pytest.mark.skipif(not Path("/dev/null").exists(), reason="/dev/null not present on this platform")
def test_gate_clear_refuses_dev_null_evidence(mroot):
    mission_id = _new_mission(mroot, "Dev Null Evidence Mission")

    r = _run(mroot, "gate", "clear", "intake-before-anything",
              "--mission", mission_id, "--evidence", "/dev/null")
    assert r.returncode != 0
    assert "REFUSED" in (r.stdout + r.stderr)

    status = json.loads(_run(mroot, "mission", "status", mission_id, "--json").stdout)
    assert all(g["cleared"] is False for g in status["gates"])


@pytestmark_gate
@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo not available on this platform")
def test_gate_clear_refuses_fifo_evidence(mroot):
    """A non-regular file INSIDE the repo (so containment alone would have
    let it through) — proves the is_file() check specifically, distinct
    from the outside-root containment check."""
    mission_id = _new_mission(mroot, "FIFO Evidence Mission")
    fifo = mroot / "a-fifo"
    os.mkfifo(fifo)

    r = _run(mroot, "gate", "clear", "intake-before-anything",
              "--mission", mission_id, "--evidence", str(fifo))
    assert r.returncode != 0
    assert "REFUSED" in (r.stdout + r.stderr)
    assert "not a regular file" in (r.stdout + r.stderr)


@pytestmark_gate
def test_gate_clear_refuses_evidence_outside_root(mroot, tmp_path_factory):
    mission_id = _new_mission(mroot, "Outside Root Evidence Mission")
    outside = tmp_path_factory.mktemp("outside-repo") / "evidence.md"
    outside.write_text("real content, but in the wrong tree", encoding="utf-8")

    r = _run(mroot, "gate", "clear", "intake-before-anything",
              "--mission", mission_id, "--evidence", str(outside))
    assert r.returncode != 0
    assert "REFUSED" in (r.stdout + r.stderr)
    assert "outside the Tess root" in (r.stdout + r.stderr)

    status = json.loads(_run(mroot, "mission", "status", mission_id, "--json").stdout)
    assert all(g["cleared"] is False for g in status["gates"])


# MEDIUM-2, continued — the SAME check via `tessctl validate mission`, on a
# HAND-CRAFTED record `gate clear` never wrote. This is the second half of
# Fable's finding: "`_lint_mission`'s re-check has the same weak check ->
# `tessctl validate` doesn't catch it either."

def _hand_crafted_cleared_mission(mroot, evidence_value):
    inst = _valid_mission_instance()
    inst["gates"][0]["cleared"] = True
    inst["gates"][0]["cleared_by"] = "attacker"
    inst["gates"][0]["cleared_at"] = "2026-07-07T00:00:00Z"
    inst["gates"][0]["evidence"] = evidence_value
    path = mroot / "hand-crafted-mission.json"
    path.write_text(json.dumps(inst), encoding="utf-8")
    return path


def test_validate_mission_rejects_empty_file_evidence(mroot):
    empty = mroot / "empty.md"
    empty.write_text("", encoding="utf-8")
    path = _hand_crafted_cleared_mission(mroot, "empty.md")

    r = _run(mroot, "validate", "mission", str(path))
    assert r.returncode != 0, r.stdout + r.stderr
    assert "empty" in r.stdout.lower()


def test_validate_mission_rejects_directory_evidence(mroot):
    a_dir = mroot / "a-directory"
    a_dir.mkdir()
    path = _hand_crafted_cleared_mission(mroot, "a-directory")

    r = _run(mroot, "validate", "mission", str(path))
    assert r.returncode != 0, r.stdout + r.stderr
    assert "not a regular file" in r.stdout


def test_validate_mission_rejects_dev_null_evidence(mroot):
    path = _hand_crafted_cleared_mission(mroot, "/dev/null")

    r = _run(mroot, "validate", "mission", str(path))
    assert r.returncode != 0, r.stdout + r.stderr


def test_validate_mission_rejects_outside_root_evidence(mroot, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside-repo") / "evidence.md"
    outside.write_text("real content, wrong tree", encoding="utf-8")
    path = _hand_crafted_cleared_mission(mroot, str(outside))

    r = _run(mroot, "validate", "mission", str(path))
    assert r.returncode != 0, r.stdout + r.stderr
    assert "outside the Tess root" in r.stdout


def test_validate_mission_accepts_real_evidence(mroot):
    """Non-vacuous control: the SAME hand-crafted-record path, with a real,
    regular, non-empty, in-repo evidence file, still validates clean."""
    real = mroot / "real-evidence.md"
    real.write_text("genuine evidence content", encoding="utf-8")
    path = _hand_crafted_cleared_mission(mroot, "real-evidence.md")

    r = _run(mroot, "validate", "mission", str(path))
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# LOW-1 — the same-brief check compares a proposed brief against EVERY
# prior attempt for the task (not just the immediately preceding one), and
# normalizes internal whitespace before comparing.
# ---------------------------------------------------------------------------

def test_retry_blocks_ping_pong_back_to_first_brief(mroot):
    """A -> B -> A: attempt 3 proposes the SAME brief as attempt 1, even
    though it differs from attempt 2 (the immediately preceding one).
    BEFORE the fix, the check only compared against the LAST attempt, so
    this ping-pong was allowed through on attempt 3; AFTER the fix it is
    blocked, because attempt 1 is still a literal match."""
    mission_id = _new_mission(mroot)
    brief_a = _brief(mroot, "ping-pong-a.md", "Investigate the queue backlog.")
    brief_b = _brief(mroot, "ping-pong-b.md", "Check the worker pool size instead.")

    r1 = _run(mroot, "retry", "log", "pingpong", "--mission", mission_id,
              "--cause", "context-gap", "--failure-state", "degraded", "--brief", brief_a)
    assert r1.returncode == 0, r1.stdout + r1.stderr

    r2 = _run(mroot, "retry", "log", "pingpong", "--mission", mission_id,
              "--cause", "context-gap", "--failure-state", "degraded", "--brief", brief_b)
    assert r2.returncode == 0, r2.stdout + r2.stderr

    # Attempt 3 proposes brief_a again — a literal match of attempt 1, NOT
    # of the immediately preceding attempt 2.
    check3 = _run(mroot, "retry", "check", "pingpong", "--mission", mission_id,
                   "--cause", "context-gap", "--brief", brief_a)
    assert check3.returncode == 1, check3.stdout
    assert "BLOCKED" in check3.stdout
    assert "same-brief retry forbidden" in check3.stdout

    log3 = _run(mroot, "retry", "log", "pingpong", "--mission", mission_id,
                "--cause", "context-gap", "--failure-state", "degraded", "--brief", brief_a)
    assert log3.returncode != 0
    assert "REFUSED" in (log3.stdout + log3.stderr)
    assert not (mroot / "missions" / mission_id / "retries" / "pingpong.attempt-3.md").exists()


def test_retry_blocks_whitespace_only_reformatted_brief(mroot):
    """A brief that is byte-different from the prior one ONLY by
    whitespace reformatting (extra spaces, re-wrapped lines, doubled blank
    lines) must still read as the SAME brief — the original check trimmed
    only leading/trailing whitespace, so internal reformatting evaded the
    same-brief-forbidden rule."""
    mission_id = _new_mission(mroot)
    brief_a_path = mroot / "reformat-a.md"
    brief_a_path.write_text(
        "Investigate the failing test.\n\nCheck the config file.\n", encoding="utf-8",
    )
    brief_b_path = mroot / "reformat-b.md"
    brief_b_path.write_text(
        "Investigate   the failing test.\nCheck the config file.\n\n\n", encoding="utf-8",
    )

    r1 = _run(mroot, "retry", "log", "reformat-task", "--mission", mission_id,
              "--cause", "context-gap", "--failure-state", "degraded", "--brief", str(brief_a_path))
    assert r1.returncode == 0, r1.stdout + r1.stderr

    check2 = _run(mroot, "retry", "check", "reformat-task", "--mission", mission_id,
                   "--cause", "context-gap", "--brief", str(brief_b_path))
    assert check2.returncode == 1, check2.stdout
    assert "BLOCKED" in check2.stdout
    assert "whitespace normalization" in check2.stdout

    log2 = _run(mroot, "retry", "log", "reformat-task", "--mission", mission_id,
                "--cause", "context-gap", "--failure-state", "degraded", "--brief", str(brief_b_path))
    assert log2.returncode != 0
    assert "REFUSED" in (log2.stdout + log2.stderr)


def test_retry_allows_genuinely_different_third_brief_after_ping_pong(mroot):
    """Non-vacuous control: a THIRD attempt with genuinely new content
    (not matching EITHER prior attempt) is still allowed."""
    mission_id = _new_mission(mroot)
    brief_a = _brief(mroot, "control-a.md", "Investigate the queue backlog.")
    brief_b = _brief(mroot, "control-b.md", "Check the worker pool size instead.")
    brief_c = _brief(mroot, "control-c.md", "Actually re-read the upstream API docs.")

    _run(mroot, "retry", "log", "control-task", "--mission", mission_id,
         "--cause", "context-gap", "--failure-state", "degraded", "--brief", brief_a)
    _run(mroot, "retry", "log", "control-task", "--mission", mission_id,
         "--cause", "context-gap", "--failure-state", "degraded", "--brief", brief_b)

    check3 = _run(mroot, "retry", "check", "control-task", "--mission", mission_id,
                   "--cause", "context-gap", "--brief", brief_c)
    assert check3.returncode == 0, check3.stdout
    assert "ALLOWED" in check3.stdout


# ---------------------------------------------------------------------------
# LOW-2 — an unvalidated task/--mission argument must never let a write
# land outside missions/<id>/.
# ---------------------------------------------------------------------------

def test_retry_log_task_traversal_stays_inside_retries_dir(mroot):
    """`task` reaches the ledger key ONLY via `_retry_task_slug` — the slug
    alphabet is [a-z0-9-], so '../' components in a caller-supplied task
    string can never reach the filesystem as anything but a literal
    (harmless) hyphen run."""
    mission_id = _new_mission(mroot)
    brief = _brief(mroot, "traversal-brief.md", "Traversal-safety check.")

    r = _run(mroot, "retry", "log", "../../evil-task", "--mission", mission_id,
              "--cause", "transient", "--failure-state", "error", "--brief", brief)
    assert r.returncode == 0, r.stdout + r.stderr

    retries_dir = mroot / "missions" / mission_id / "retries"
    written = [p for p in retries_dir.iterdir() if p.name != ".gitkeep"]
    assert len(written) == 1
    assert "/" not in written[0].name and ".." not in written[0].name
    assert written[0].name == "evil-task.attempt-1.md"

    # Nothing was written anywhere outside mroot.
    assert not (mroot.parent / "evil-task.attempt-1.md").exists()
    assert not (mroot.parent.parent / "evil-task.attempt-1.md").exists()


def test_retry_log_mission_id_traversal_cannot_escape_missions_dir(mroot, tmp_path):
    """`--mission '../../../escaped-mission'` computed against
    root/missions/<id> climbs three levels above `mroot` (missions -> os ->
    tmp_path -> tmp_path's parent) before the fix's mission-id validation
    ever runs — this asserts BOTH the refusal and that nothing was ever
    created at the precise location the traversal targeted."""
    brief = _brief(mroot, "b.md", "text")
    escape_target = tmp_path.parent / "escaped-mission"

    r = _run(mroot, "retry", "log", "task", "--mission", "../../../escaped-mission",
              "--cause", "transient", "--failure-state", "error", "--brief", brief)
    assert r.returncode != 0
    assert "invalid mission id" in (r.stdout + r.stderr)
    assert not escape_target.exists()


def test_gate_clear_absolute_mission_id_rejected(mroot):
    """The Path.__truediv__ footgun: an ABSOLUTE mission id joined with
    `root / MISSIONS_DIR / mission_id` silently discards root + MISSIONS_DIR
    entirely (the SAME footgun the verdict-signing `public_key_file`
    containment check elsewhere in this file already guards against)."""
    evidence = mroot / "e.md"
    evidence.write_text("x", encoding="utf-8")

    r = _run(mroot, "gate", "clear", "intake-before-anything",
              "--mission", "/tmp/absolute-mission-id-should-be-rejected",
              "--evidence", str(evidence))
    assert r.returncode != 0
    assert "invalid mission id" in (r.stdout + r.stderr)


def test_gate_status_dotdot_mission_id_rejected(mroot):
    r = _run(mroot, "gate-status", "..")
    assert r.returncode != 0
    assert "invalid mission id" in (r.stdout + r.stderr)


def test_mission_status_slash_mission_id_rejected(mroot):
    r = _run(mroot, "mission", "status", "some/../../thing")
    assert r.returncode != 0
    assert "invalid mission id" in (r.stdout + r.stderr)
