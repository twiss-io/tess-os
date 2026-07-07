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


def test_m1_brief_destructive_requires_step(engine):
    bad = _valid_brief()
    bad["destructive"] = True
    violations = _validate(engine, "brief", bad)
    assert any("step" in v for v in violations)

    ok = _valid_brief()
    ok["destructive"] = True
    ok["step"] = "verify"
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


# ---------------------------------------------------------------------------
# H1 — null-verifier bypass (Fable adversarial review, BLOCK finding).
# Proves the previously-passing bad instance now FAILS: a prod-touching task
# with verifier: {agent: null, required: true, primary_artifacts: []} used to
# pass because the schema only checked verifier.required == true.
# ---------------------------------------------------------------------------

def test_h1_prod_touching_null_verifier_bypass_now_fails(engine):
    bad = _valid_crew_plan()
    task = bad["crew_plan"]["stages"][0]["tasks"][0]
    task["prod_touching"] = True
    # required: true is satisfied, but agent is null and primary_artifacts is
    # empty — this is the exact instance the Fable review reported as a
    # false-ACCEPT.
    task["verifier"] = {"agent": None, "required": True, "primary_artifacts": []}
    violations = _validate(engine, "crew-plan", bad)
    assert violations != [], "null-verifier bypass: bad instance must now FAIL validation"
    assert any("agent" in v or "primary_artifacts" in v or "verifier" in v for v in violations)

    # Same shape, but with a real named verifier and a non-empty artifact
    # list, still passes — the fix doesn't break the legitimate case.
    ok = _valid_crew_plan()
    ok_task = ok["crew_plan"]["stages"][0]["tasks"][0]
    ok_task["prod_touching"] = True
    ok_task["verifier"] = {"agent": "Reid", "required": True, "primary_artifacts": ["diff/here"]}
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


# ---------------------------------------------------------------------------
# H2 — HIGH-and-approve (Fable adversarial review, BLOCK finding). A verdict
# with a HIGH finding + disposition: APPROVE used to pass with no gate at
# all. Three proof tests: the bare bypass now fails; the same bypass with an
# explicit accepted_high_findings entry passes for a non-security verifier;
# the same escape is refused outright for Cyra (security has no escape).
# ---------------------------------------------------------------------------

def _high_finding(location="api/users.ts:112"):
    return {
        "severity": "HIGH",
        "location": location,
        "finding": "missing authorization check on admin endpoint",
        "risk": "privilege escalation",
        "fix": "add role check middleware",
    }


def test_h2_high_finding_approve_without_acceptance_now_fails(engine):
    bad = _valid_verdict()
    bad["verifier"] = "Reid"
    bad["output_domain"] = "Code diff / PR"
    bad["findings"].append(_high_finding())
    bad["severity_counts"]["high"] = 1
    bad["disposition"] = "APPROVE"
    violations = _validate(engine, "verdict", bad)
    assert violations != [], "HIGH + APPROVE with no acceptance must now FAIL validation"


def test_h2_high_finding_approve_with_acceptance_passes_non_security(engine):
    ok = _valid_verdict()
    ok["verifier"] = "Reid"
    ok["output_domain"] = "Code diff / PR"
    ok["findings"].append(_high_finding())
    ok["severity_counts"]["high"] = 1
    ok["disposition"] = "APPROVE"
    ok["accepted_high_findings"] = [
        {"location": "api/users.ts:112", "rationale": "Tracked as a fast-follow; endpoint is feature-flagged off in prod."}
    ]
    schema_violations = _validate(engine, "verdict", ok)
    lint_violations = engine._lint_contract("verdict", ok)
    assert schema_violations == [] and lint_violations == [], schema_violations + lint_violations


def test_h2_cyra_high_finding_approve_with_acceptance_still_fails(engine):
    bad = _valid_verdict()
    bad["verifier"] = "Cyra"
    bad["output_domain"] = "Security"
    bad["findings"].append(_high_finding())
    bad["severity_counts"]["high"] = 1
    bad["disposition"] = "APPROVE"
    bad["accepted_high_findings"] = [
        {"location": "api/users.ts:112", "rationale": "Accepted risk — do not ship for security domain."}
    ]
    violations = _validate(engine, "verdict", bad)
    assert violations != [], "Cyra (security) verdict must have no accepted_high_findings escape from BLOCK"
    assert any("BLOCK" in v for v in violations)


def test_h2_lint_requires_every_high_finding_individually_acknowledged(engine):
    bad = _valid_verdict()
    bad["verifier"] = "Reid"
    bad["output_domain"] = "Code diff / PR"
    bad["findings"].append(_high_finding("api/users.ts:112"))
    bad["findings"].append(_high_finding("api/orders.ts:44"))
    bad["severity_counts"]["high"] = 2
    bad["disposition"] = "APPROVE_WITH_SUGGESTIONS"
    # Only ONE of the two HIGH findings is acknowledged — a blanket escape
    # must not cover findings it never named.
    bad["accepted_high_findings"] = [
        {"location": "api/users.ts:112", "rationale": "Tracked as a fast-follow."}
    ]
    lint_violations = engine._lint_contract("verdict", bad)
    assert any("orders.ts:44" in v for v in lint_violations)


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


def test_h4_return_manifest_complete_status_requires_nonempty_claims(engine):
    bad = _valid_return_manifest()
    bad["status"] = "complete"
    bad["claims"] = []
    violations = _validate(engine, "return-manifest", bad)
    assert any("claims" in v for v in violations), (
        "status: complete with zero claims (an artifact that exists but nothing is "
        "actually asserted about it) must now FAIL validation"
    )

    ok = _valid_return_manifest()
    ok["status"] = "partial"
    ok["claims"] = []
    assert _validate(engine, "return-manifest", ok) == []


# ---------------------------------------------------------------------------
# H4 — fabricated artifacts / shape-only guarantee (Fable adversarial
# review, BLOCK finding). Proves the previously-passing bad instance now
# FAILS: status: complete with an artifact path that does not exist on disk.
# ---------------------------------------------------------------------------

def test_h4_return_manifest_artifact_path_must_exist_on_disk(engine, tmp_path):
    real_artifact = tmp_path / "offer-read.md"
    real_artifact.write_text("# Claims + Evidence\n")

    bad = _valid_return_manifest()
    bad["artifacts"] = [{"path": str(tmp_path / "does-not-exist.md"), "description": "fabricated"}]
    violations = engine._lint_contract("return-manifest", bad)
    assert violations != [], "a return-manifest pointing at a non-existent artifact path must FAIL"
    assert any("does-not-exist.md" in v for v in violations)

    ok = _valid_return_manifest()
    ok["artifacts"] = [{"path": str(real_artifact), "description": "claims + evidence table"}]
    assert engine._lint_contract("return-manifest", ok) == []


def test_h4_cli_validate_return_manifest_fabricated_artifact_path_fails(cli_root, run_cli, tmp_path):
    bad = _valid_return_manifest()
    bad["artifacts"] = [{"path": str(tmp_path / "never-written.md"), "description": "claimed but absent"}]
    f = tmp_path / "bad_return.json"
    f.write_text(json.dumps(bad))
    r = run_cli(cli_root, "validate", "return-manifest", str(f), "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["valid"] is False
    assert any("never-written.md" in v for v in payload["violations"])


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
# M2 — crew-plan lint: dangling depends_on, duplicate task ids, duplicate/
# out-of-order stage numbers (cheap MEDIUM, Fable adversarial review).
# ---------------------------------------------------------------------------

def test_m2_lint_crew_plan_dangling_depends_on_rejected(engine):
    bad = _valid_crew_plan()
    bad["crew_plan"]["stages"][0]["parallel"] = False
    bad["crew_plan"]["stages"][0]["tasks"][0]["depends_on"] = ["ghost-task-that-does-not-exist"]
    violations = engine._lint_contract("crew-plan", bad)
    assert any("ghost-task-that-does-not-exist" in v for v in violations)


def test_m2_lint_crew_plan_duplicate_task_id_rejected(engine):
    bad = _valid_crew_plan()
    stage = bad["crew_plan"]["stages"][0]
    stage["parallel"] = False
    dup_task = copy.deepcopy(stage["tasks"][0])
    dup_task["id"] = stage["tasks"][0]["id"]  # exact same id, duplicated
    stage["tasks"].append(dup_task)
    violations = engine._lint_contract("crew-plan", bad)
    assert any("duplicate task id" in v for v in violations)


def test_m2_lint_crew_plan_duplicate_stage_numbers_rejected(engine):
    bad = _valid_crew_plan()
    stage2 = copy.deepcopy(bad["crew_plan"]["stages"][0])
    stage2["tasks"][0]["id"] = "offer-read-2"
    stage2["stage"] = 1  # duplicate of stage 1
    bad["crew_plan"]["stages"].append(stage2)
    violations = engine._lint_contract("crew-plan", bad)
    assert any("stage number" in v for v in violations)


def test_m2_lint_crew_plan_out_of_order_stage_numbers_rejected(engine):
    bad = _valid_crew_plan()
    stage0 = copy.deepcopy(bad["crew_plan"]["stages"][0])
    stage0["tasks"][0]["id"] = "offer-read-early"
    stage0["stage"] = 0  # inserted AFTER stage 1 in list order, out of sequence
    bad["crew_plan"]["stages"].append(stage0)
    violations = engine._lint_contract("crew-plan", bad)
    assert any("stage number" in v for v in violations)


# ---------------------------------------------------------------------------
# $ref resolution across files (crew-plan Task.brief -> brief.schema.json)
# ---------------------------------------------------------------------------

def test_crew_plan_brief_ref_enforces_six_field_brief_contract(engine):
    bad = _valid_crew_plan()
    del bad["crew_plan"]["stages"][0]["tasks"][0]["brief"]["objective"]
    violations = _validate(engine, "crew-plan", bad)
    assert any("objective" in v for v in violations)


# ---------------------------------------------------------------------------
# H3 — cross-file $ref root_schema bug (Fable adversarial review, BLOCK
# finding). A $ref that crosses into an EXTERNAL document must rebind
# root_schema to that document, so the external document's OWN internal
# "#/$defs/..." pointers resolve against ITSELF — not against whatever
# document originally called schema_validate(). Reproduced with two tiny
# synthetic schema files (none of the four real contracts currently have a
# same-named $defs collision — the bug is latent, per the Fable review —
# so this constructs the collision directly): a "referrer" schema $refs an
# "external" schema which has its own strict internal $defs.Strict; the
# referrer ALSO happens to define its own $defs.Strict with the same name
# but a much looser (permissive) shape. Before the fix, the external
# document's internal "#/$defs/Strict" ref would silently resolve against
# the REFERRER's looser Strict def (root_schema never rebound) and a bad
# instance would falsely validate. After the fix, it resolves against the
# external document's own (correct, strict) Strict def.
# ---------------------------------------------------------------------------

def _write_h3_fixture_schemas(tmp_path):
    external = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"child": {"$ref": "#/$defs/Strict"}},
        "required": ["child"],
        "additionalProperties": False,
        "$defs": {
            "Strict": {
                "type": "object",
                "properties": {"value": {"type": "string", "minLength": 5}},
                "required": ["value"],
                "additionalProperties": False,
            }
        },
    }
    referrer = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"outer": {"$ref": "external.schema.json#"}},
        "required": ["outer"],
        "additionalProperties": False,
        # Same name, deliberately looser shape — this is what a buggy
        # root_schema-never-rebound resolver would incorrectly find instead
        # of external.schema.json's own $defs.Strict.
        "$defs": {"Strict": {"type": "object"}},
    }
    (tmp_path / "external.schema.json").write_text(json.dumps(external))
    (tmp_path / "referrer.schema.json").write_text(json.dumps(referrer))
    return referrer


def test_h3_external_ref_internal_defs_not_masked_by_referrer_same_named_def(engine, tmp_path):
    referrer_schema = _write_h3_fixture_schemas(tmp_path)

    # "value" is only 2 chars — violates external.schema.json's own strict
    # $defs.Strict (minLength: 5). If root_schema were still the referrer at
    # this point (the bug), "#/$defs/Strict" would resolve to the referrer's
    # bare {"type": "object"} def instead — which has no minLength
    # constraint at all — and this instance would incorrectly PASS.
    bad_instance = {"outer": {"child": {"value": "ab"}}}
    violations = engine.schema_validate(bad_instance, referrer_schema, referrer_schema, tmp_path)
    assert violations != [], (
        "external $def must NOT be masked by a same-named, looser $def in the referrer"
    )
    assert any("minLength" in v for v in violations)

    # A genuinely valid instance (value long enough) still passes correctly.
    ok_instance = {"outer": {"child": {"value": "abcdef"}}}
    assert engine.schema_validate(ok_instance, referrer_schema, referrer_schema, tmp_path) == []


def test_h3_crew_plan_brief_ref_still_resolves_correctly(engine):
    """Sanity check the fix through the REAL crew-plan -> brief $ref path
    (no $defs collision exists there today, but this pins that the fix
    didn't regress the ordinary cross-file case)."""
    ok = _valid_crew_plan()
    assert _validate(engine, "crew-plan", ok) == []


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
    # M3 FIX (Fable adversarial review): a missing instance file is an infra
    # error, not a schema-miss — it now exits 2 (distinct from the
    # schema-miss exit 1), not 1.
    r = run_cli(cli_root, "validate", "brief", "/does/not/exist.json")
    assert r.returncode == 2
    assert "not found" in (r.stdout + r.stderr)


def test_m3_cli_validate_missing_file_classified_empty_transient_not_degraded(cli_root, run_cli):
    r = run_cli(cli_root, "validate", "brief", "/does/not/exist.json", "--json")
    assert r.returncode == 2, "infra errors must exit with a code distinct from schema-miss (1)"
    payload = json.loads(r.stdout)
    assert payload["valid"] is False
    c = payload["classification"]
    assert c["signal"] == "validation_infra_error"
    assert c["failure_state"] == "empty"
    assert c["cause_class"] == "transient"
    assert c["same_brief_retry_forbidden"] is False, "a missing instance file must PERMIT a same-brief retry"


def test_m3_cli_validate_unparsable_instance_is_error_not_empty(cli_root, run_cli, tmp_path):
    f = tmp_path / "broken.json"
    f.write_text("{not valid json")
    r = run_cli(cli_root, "validate", "brief", str(f), "--json")
    assert r.returncode == 2
    payload = json.loads(r.stdout)
    c = payload["classification"]
    assert c["failure_state"] == "error"
    assert c["cause_class"] == "wrong-approach"
    assert c["same_brief_retry_forbidden"] is True
