"""
Phase 0 (contracts-as-code): core/contracts/*.schema.json + `tessctl validate`.

Spec: docs/ULTIMATE_FRAMEWORK_PLAN.md Phase 0, Design Decision #3
("Contracts become schemas"); core/contracts/README.md.

Coverage:
  * All four schemas parse as valid JSON and load via load_contract_schema().
  * A valid instance of each contract type passes schema_validate() with [].
  * Specific invalid instances are rejected with the expected violation
    (missing required brief field; wrong verdict disposition enum; etc.)
  * The four doctrine-mandated if/then conditionals actually gate:
      - brief: milestones required when prod_touching / estimated_minutes>15
      - crew-plan.Task: verifier.required must be true when prod-touching/
        client-facing/externally-visible/irreversible
      - verdict: disposition must be BLOCK when any finding is CRITICAL
      - return-manifest.Claim: non-inferred claim requires non-empty evidence
  * The two lint checks (crew-plan §3.2 rule 7 + synthesis.inputs; verdict
    severity_counts) fire on the relational violations plain schema can't
    express.
  * $ref resolution works across files (crew-plan Task.brief -> brief.schema.json).
  * classify_schema_miss() returns the degraded_output signal doctrine calls for.
  * The `tessctl validate` CLI: exit codes, --json output, .md front-matter
    instances, and the unknown-contract-type / missing-file error paths.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cli_root(project):
    """A project root (from the shared `project` fixture) with the real
    core/contracts/*.schema.json copied in, ready for CLI-level `tessctl
    validate` invocations via `run_cli`."""
    dst = project.root / "core" / "contracts"
    shutil.copytree(CONTRACTS_SRC, dst)
    return project.root


def _valid_brief():
    return {
        "objective": "Quantify where in the funnel conversion is dropping, stage by stage.",
        "output_contract": "/tmp/conv-analysis.md — sections [Funnel table, Drop-off stage, Evidence]",
        "tools_sources_constraints": "Read the CRM export at /data/crm.csv; every number traces to a quoted row; inference labelled.",
        "not_responsible_for": "Recommending fixes (that is stage 2).",
        "milestones": [
            {"deliverable": "Funnel table", "acceptance_evidence": "quoted source rows", "owner": "leah"}
        ],
        "escalation_trigger": "Export missing or stages unmappable -> stop, surface to conductor.",
        "prod_touching": False,
        "estimated_minutes": 20,
    }


def _valid_crew_plan():
    return {
        "crew_plan": {
            "mission_id": "2026-07-07-rev-conv-001",
            "outcome_owner": "revenue-orchestrator",
            "outcome_type": "recover",
            "notes": "Diagnose the conversion drop before any intervention.",
            "stages": [
                {
                    "stage": 1,
                    "gate_in": "intake-before-anything",
                    "parallel": True,
                    "tasks": [
                        {
                            "id": "offer-read",
                            "agent": "apolline",
                            "role": "Owner",
                            "depends_on": [],
                            "brief": {
                                "objective": "Read the current offer page and summarize positioning claims.",
                                "output_contract": "/tmp/offer-read.md — sections [Claims, Evidence]",
                                "tools_sources_constraints": "Read the live offer page; quote exact claims.",
                                "not_responsible_for": "Recommending new copy.",
                                "milestones": [],
                                "escalation_trigger": "Page unreachable -> stop, surface to conductor.",
                            },
                            "verifier": {"agent": None, "required": False, "primary_artifacts": []},
                        }
                    ],
                }
            ],
            "synthesis": {
                "owner": "revenue-orchestrator",
                "format": "output-framework.md/10-section",
                "inputs": ["offer-read"],
            },
            "escalations": [
                "Conversion drop traces to a product defect -> hand to Product & Delivery Orchestrator."
            ],
        }
    }


def _valid_verdict():
    return {
        "verifier": "Cyra",
        "output_domain": "Security",
        "primary_artifacts_read": ["api/auth/session.ts"],
        "findings": [
            {
                "severity": "MEDIUM",
                "location": "api/users.ts:112",
                "finding": "no rate limiting on login endpoint",
                "risk": "brute force risk",
                "fix": "add rate limiter middleware",
            }
        ],
        "severity_counts": {"critical": 0, "high": 0, "medium": 1, "low": 0},
        "summary_line": "Reviewed API security posture. Found 0 CRITICAL, 0 HIGH, 1 MEDIUM, 0 LOW. Top priority: rate limiting.",
        "disposition": "APPROVE_WITH_SUGGESTIONS",
    }


def _valid_return_manifest():
    return {
        "task_id": "offer-read",
        "mission_id": "2026-07-07-rev-conv-001",
        "agent": "apolline",
        "status": "complete",
        "self_reported_complete": True,
        "artifacts": [{"path": "/tmp/offer-read.md", "description": "claims + evidence table"}],
        "claims": [
            {
                "claim": "The offer page states a 14-day trial.",
                "evidence": "https://example.com/offer (line 22)",
                "inferred": False,
            }
        ],
        "flags": [],
    }


VALID_INSTANCES = {
    "brief": _valid_brief,
    "crew-plan": _valid_crew_plan,
    "verdict": _valid_verdict,
    "return-manifest": _valid_return_manifest,
}


# ---------------------------------------------------------------------------
# Schemas load + valid instances pass
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("contract_type", ["brief", "crew-plan", "verdict", "return-manifest"])
def test_schema_is_valid_json_and_loads(engine, contract_type):
    schema = engine.load_contract_schema(REPO_ROOT, contract_type)
    assert isinstance(schema, dict)
    assert schema.get("$schema", "").startswith("http://json-schema.org/draft-07")


@pytest.mark.parametrize("contract_type", ["brief", "crew-plan", "verdict", "return-manifest"])
def test_valid_instance_passes(engine, contract_type):
    schema = engine.load_contract_schema(REPO_ROOT, contract_type)
    instance = VALID_INSTANCES[contract_type]()
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(instance, schema, schema, base_dir)
    assert violations == []


def test_unknown_contract_type_raises(engine):
    with pytest.raises(engine.ContractError):
        engine.load_contract_schema(REPO_ROOT, "not-a-real-contract")


# ---------------------------------------------------------------------------
# Specific invalid instances — structural (missing field / wrong enum)
# ---------------------------------------------------------------------------

def _validate(engine, contract_type, instance):
    schema = engine.load_contract_schema(REPO_ROOT, contract_type)
    base_dir = REPO_ROOT / "core" / "contracts"
    return engine.schema_validate(instance, schema, schema, base_dir)


def test_brief_missing_required_field_rejected(engine):
    bad = _valid_brief()
    del bad["objective"]
    violations = _validate(engine, "brief", bad)
    assert any("objective" in v for v in violations)


def test_crew_plan_wrong_outcome_type_enum_rejected(engine):
    bad = _valid_crew_plan()
    bad["crew_plan"]["outcome_type"] = "wibble"
    violations = _validate(engine, "crew-plan", bad)
    assert any("outcome_type" in v or "wibble" in v for v in violations)


def test_crew_plan_missing_wrapper_key_rejected(engine):
    bad = {"not_crew_plan": {}}
    violations = _validate(engine, "crew-plan", bad)
    assert any("crew_plan" in v for v in violations)


def test_verdict_wrong_disposition_enum_rejected(engine):
    bad = _valid_verdict()
    bad["disposition"] = "LGTM"
    violations = _validate(engine, "verdict", bad)
    assert any("disposition" in v or "LGTM" in v for v in violations)


def test_return_manifest_missing_status_rejected(engine):
    bad = _valid_return_manifest()
    del bad["status"]
    violations = _validate(engine, "return-manifest", bad)
    assert any("status" in v for v in violations)


# ---------------------------------------------------------------------------
# The four doctrine-mandated if/then conditionals ("can't sound done")
# ---------------------------------------------------------------------------

def test_brief_prod_touching_requires_nonempty_milestones(engine):
    bad = _valid_brief()
    bad["prod_touching"] = True
    bad["milestones"] = []
    violations = _validate(engine, "brief", bad)
    assert any("milestones" in v for v in violations)

    ok = _valid_brief()
    ok["prod_touching"] = True
    ok["milestones"] = [{"deliverable": "x", "acceptance_evidence": "y", "owner": "z"}]
    assert _validate(engine, "brief", ok) == []


def test_brief_over_15_minutes_requires_nonempty_milestones(engine):
    bad = _valid_brief()
    bad["prod_touching"] = False
    bad["estimated_minutes"] = 20
    bad["milestones"] = []
    violations = _validate(engine, "brief", bad)
    assert any("milestones" in v for v in violations)

    ok = _valid_brief()
    ok["prod_touching"] = False
    ok["estimated_minutes"] = 10
    ok["milestones"] = []
    assert _validate(engine, "brief", ok) == []


def test_crew_plan_prod_touching_task_requires_verifier_required_true(engine):
    bad = _valid_crew_plan()
    task = bad["crew_plan"]["stages"][0]["tasks"][0]
    task["prod_touching"] = True
    task["verifier"] = {"agent": None, "required": False, "primary_artifacts": []}
    violations = _validate(engine, "crew-plan", bad)
    assert any("verifier" in v for v in violations)

    ok = _valid_crew_plan()
    task = ok["crew_plan"]["stages"][0]["tasks"][0]
    task["prod_touching"] = True
    task["verifier"] = {"agent": "Reid", "required": True, "primary_artifacts": ["diff/here"]}
    assert _validate(engine, "crew-plan", ok) == []


def test_verdict_critical_finding_requires_block_disposition(engine):
    bad = _valid_verdict()
    bad["findings"].append({
        "severity": "CRITICAL",
        "location": "auth/session.ts:47",
        "finding": "JWT secret hardcoded in source",
        "risk": "credential exposure",
        "fix": "move to environment variable",
    })
    bad["severity_counts"]["critical"] = 1
    bad["disposition"] = "APPROVE"
    violations = _validate(engine, "verdict", bad)
    assert any("BLOCK" in v for v in violations)

    ok = copy.deepcopy(bad)
    ok["disposition"] = "BLOCK"
    assert _validate(engine, "verdict", ok) == []


def test_return_manifest_non_inferred_claim_requires_evidence(engine):
    bad = _valid_return_manifest()
    bad["claims"][0]["inferred"] = False
    bad["claims"][0]["evidence"] = ""
    violations = _validate(engine, "return-manifest", bad)
    assert any("evidence" in v for v in violations)

    ok = _valid_return_manifest()
    ok["claims"][0]["inferred"] = True
    del ok["claims"][0]["evidence"]
    assert _validate(engine, "return-manifest", ok) == []


def test_return_manifest_complete_status_requires_nonempty_artifacts(engine):
    bad = _valid_return_manifest()
    bad["status"] = "complete"
    bad["artifacts"] = []
    violations = _validate(engine, "return-manifest", bad)
    assert any("artifacts" in v for v in violations)

    ok = _valid_return_manifest()
    ok["status"] = "error"
    ok["artifacts"] = []
    ok["claims"] = []
    assert _validate(engine, "return-manifest", ok) == []


# ---------------------------------------------------------------------------
# Lint checks (relational rules beyond plain schema)
# ---------------------------------------------------------------------------

def test_lint_crew_plan_parallel_forbids_intra_stage_depends_on(engine):
    bad = _valid_crew_plan()
    bad["crew_plan"]["stages"][0]["parallel"] = True
    bad["crew_plan"]["stages"][0]["tasks"][0]["depends_on"] = ["some-other-task"]
    violations = engine._lint_contract("crew-plan", bad)
    assert any("parallel" in v for v in violations)


def test_lint_crew_plan_synthesis_inputs_must_reference_real_task_ids(engine):
    bad = _valid_crew_plan()
    bad["crew_plan"]["synthesis"]["inputs"] = ["does-not-exist"]
    violations = engine._lint_contract("crew-plan", bad)
    assert any("does-not-exist" in v for v in violations)


def test_lint_verdict_severity_counts_must_match_findings_tally(engine):
    bad = _valid_verdict()
    bad["severity_counts"]["medium"] = 5
    violations = engine._lint_contract("verdict", bad)
    assert any("medium" in v.lower() for v in violations)


# ---------------------------------------------------------------------------
# $ref resolution across files (crew-plan Task.brief -> brief.schema.json)
# ---------------------------------------------------------------------------

def test_crew_plan_brief_ref_enforces_six_field_brief_contract(engine):
    bad = _valid_crew_plan()
    del bad["crew_plan"]["stages"][0]["tasks"][0]["brief"]["objective"]
    violations = _validate(engine, "crew-plan", bad)
    assert any("objective" in v for v in violations)


# ---------------------------------------------------------------------------
# Schema-miss -> degraded_output classification
# ---------------------------------------------------------------------------

def test_classify_schema_miss_shape(engine):
    c = engine.classify_schema_miss("brief", ["$: missing required property 'objective'"])
    assert c["signal"] == "schema_miss_degraded_output"
    assert c["failure_state"] == "degraded"
    assert c["cause_class"] == "context-gap"
    assert c["same_brief_retry_forbidden"] is True
    assert c["attempt_cap"] == 3
    assert c["violation_count"] == 1


# ---------------------------------------------------------------------------
# Instance-file loading (.json / .yaml / .md front-matter)
# ---------------------------------------------------------------------------

def test_load_contract_instance_json(engine, tmp_path):
    p = tmp_path / "b.json"
    p.write_text(json.dumps(_valid_brief()))
    assert engine.load_contract_instance(p)["objective"]


def test_load_contract_instance_yaml(engine, tmp_path):
    import yaml
    p = tmp_path / "b.yaml"
    p.write_text(yaml.safe_dump(_valid_brief()))
    assert engine.load_contract_instance(p)["objective"]


def test_load_contract_instance_md_frontmatter(engine, tmp_path):
    p = tmp_path / "b.md"
    p.write_text(
        "---\n"
        "objective: Do the thing.\n"
        "output_contract: /tmp/out.md\n"
        "tools_sources_constraints: Read /tmp/in.md\n"
        "not_responsible_for: The other thing.\n"
        "milestones: []\n"
        "escalation_trigger: If stuck, stop.\n"
        "---\n\n"
        "# Body — not part of the contract instance\n"
    )
    instance = engine.load_contract_instance(p)
    assert instance["objective"] == "Do the thing."


def test_load_contract_instance_md_without_frontmatter_raises(engine, tmp_path):
    p = tmp_path / "no_fm.md"
    p.write_text("# Just prose, no front-matter\n")
    with pytest.raises(engine.ContractError):
        engine.load_contract_instance(p)


def test_load_contract_instance_unsupported_extension_raises(engine, tmp_path):
    p = tmp_path / "b.txt"
    p.write_text("objective: x")
    with pytest.raises(engine.ContractError):
        engine.load_contract_instance(p)


def test_load_contract_instance_missing_file_raises(engine, tmp_path):
    with pytest.raises(engine.ContractError):
        engine.load_contract_instance(tmp_path / "nope.json")


# ---------------------------------------------------------------------------
# CLI: `tessctl validate <contract-type> <file>`
# ---------------------------------------------------------------------------

def test_cli_validate_valid_brief_exits_zero(cli_root, run_cli, tmp_path):
    f = tmp_path / "brief.json"
    f.write_text(json.dumps(_valid_brief()))
    r = run_cli(cli_root, "validate", "brief", str(f))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_cli_validate_invalid_brief_exits_nonzero_json(cli_root, run_cli, tmp_path):
    bad = _valid_brief()
    del bad["objective"]
    f = tmp_path / "bad_brief.json"
    f.write_text(json.dumps(bad))
    r = run_cli(cli_root, "validate", "brief", str(f), "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["valid"] is False
    assert payload["classification"]["signal"] == "schema_miss_degraded_output"
    assert payload["classification"]["failure_state"] == "degraded"
    assert payload["classification"]["cause_class"] == "context-gap"
    assert payload["classification"]["same_brief_retry_forbidden"] is True


def test_cli_validate_verdict_critical_forces_block(cli_root, run_cli, tmp_path):
    bad = _valid_verdict()
    bad["findings"].append({
        "severity": "CRITICAL",
        "location": "x:1",
        "finding": "f",
        "risk": "r",
        "fix": "f",
    })
    bad["severity_counts"]["critical"] = 1
    bad["disposition"] = "APPROVE"
    f = tmp_path / "bad_verdict.json"
    f.write_text(json.dumps(bad))
    r = run_cli(cli_root, "validate", "verdict", str(f), "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert any("BLOCK" in v for v in payload["violations"])


def test_cli_validate_unknown_contract_type_argparse_error(cli_root, run_cli, tmp_path):
    f = tmp_path / "x.json"
    f.write_text("{}")
    r = run_cli(cli_root, "validate", "not-a-type", str(f))
    assert r.returncode != 0
    assert "invalid choice" in (r.stdout + r.stderr)


def test_cli_validate_missing_file(cli_root, run_cli):
    r = run_cli(cli_root, "validate", "brief", "/does/not/exist.json")
    assert r.returncode == 1
    assert "not found" in (r.stdout + r.stderr)
