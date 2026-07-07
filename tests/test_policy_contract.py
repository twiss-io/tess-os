"""
Phase 2 (`policy.schema.json`) — schema + lint unit tests, in the same style
as tests/test_contracts_validate.py's coverage of the original four
contracts.

Spec: docs/ULTIMATE_FRAMEWORK_PLAN.md Phase 2, Design Decisions #2 + #6;
core/contracts/policy.schema.json; core/policy/policy.yaml.

Coverage:
  * The schema is valid JSON and loads via load_contract_schema().
  * A valid policy instance passes schema_validate() with [].
  * Structural violations are rejected (missing required top-level key,
    wrong classification enum value, wrong hard-floor category enum value).
  * The `require_verdict: true` -> `allowed_verifiers` non-empty conditional
    actually gates.
  * Lint: duplicate rule ids across rules[]/hard_floor_rules[]; a
    require_verdict:true rule whose globs are all blank.
  * The shipped core/policy/policy.yaml instance itself validates cleanly
    (also covered end-to-end in test_contracts_wiring.py).
  * `tessctl validate policy <file>` CLI round-trip (the fifth contract type
    is a first-class citizen of the existing Phase 0 CLI, not a bolt-on).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"


@pytest.fixture
def cli_root(project):
    dst = project.root / "core" / "contracts"
    shutil.copytree(CONTRACTS_SRC, dst)
    return project.root


def _valid_policy():
    return {
        "policy": {
            "version": 1,
            "rules": [
                {
                    "id": "prod-service",
                    "description": "Production API service code.",
                    "globs": ["src/api/**"],
                    "classification": ["prod_touching", "client_facing"],
                    "require_verdict": True,
                    "allowed_verifiers": ["Reid", "Quinn"],
                },
                {
                    "id": "internal-tooling",
                    "description": "Internal-only scripts — discretionary review.",
                    "globs": ["scripts/**"],
                    "classification": ["prod_touching"],
                    "require_verdict": False,
                },
            ],
            "hard_floor_rules": [
                {
                    "id": "credentials",
                    "category": "credentials",
                    "description": "Secret/config surfaces.",
                    "globs": ["**/*.env", "**/secrets/**"],
                },
                {
                    "id": "client-external-claims",
                    "category": "client_external_claims",
                    "description": "Not path-detectable — empty on purpose.",
                    "globs": [],
                },
            ],
        }
    }


def _validate(engine, instance):
    schema = engine.load_contract_schema(REPO_ROOT, "policy")
    base_dir = REPO_ROOT / "core" / "contracts"
    return engine.schema_validate(instance, schema, schema, base_dir)


# ---------------------------------------------------------------------------
# Schema loads + valid instance passes
# ---------------------------------------------------------------------------

def test_policy_schema_is_valid_json_and_loads(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "policy")
    assert isinstance(schema, dict)
    assert schema.get("$schema", "").startswith("http://json-schema.org/draft-07")


def test_valid_policy_instance_passes(engine):
    assert _validate(engine, _valid_policy()) == []
    assert engine._lint_contract("policy", _valid_policy()) == []


def test_policy_is_fifth_contract_schema(engine):
    assert engine.CONTRACT_SCHEMAS["policy"] == "policy.schema.json"
    assert set(engine.CONTRACT_SCHEMAS) == {"brief", "crew-plan", "verdict", "return-manifest", "policy"}


# ---------------------------------------------------------------------------
# Structural violations
# ---------------------------------------------------------------------------

def test_policy_missing_wrapper_key_rejected(engine):
    violations = _validate(engine, {"not_policy": {}})
    assert any("policy" in v for v in violations)


def test_policy_wrong_classification_enum_rejected(engine):
    bad = _valid_policy()
    bad["policy"]["rules"][0]["classification"] = ["wibble"]
    violations = _validate(engine, bad)
    assert any("classification" in v or "wibble" in v for v in violations)


def test_hard_floor_wrong_category_enum_rejected(engine):
    bad = _valid_policy()
    bad["policy"]["hard_floor_rules"][0]["category"] = "not-a-real-category"
    violations = _validate(engine, bad)
    assert any("category" in v or "not-a-real-category" in v for v in violations)


def test_policy_missing_required_top_level_field_rejected(engine):
    bad = _valid_policy()
    del bad["policy"]["version"]
    violations = _validate(engine, bad)
    assert any("version" in v for v in violations)


# ---------------------------------------------------------------------------
# require_verdict -> allowed_verifiers conditional
# ---------------------------------------------------------------------------

def test_require_verdict_true_requires_nonempty_allowed_verifiers(engine):
    bad = _valid_policy()
    del bad["policy"]["rules"][0]["allowed_verifiers"]
    violations = _validate(engine, bad)
    assert any("allowed_verifiers" in v for v in violations)

    bad2 = _valid_policy()
    bad2["policy"]["rules"][0]["allowed_verifiers"] = []
    violations2 = _validate(engine, bad2)
    assert any("allowed_verifiers" in v for v in violations2)


def test_require_verdict_false_does_not_need_allowed_verifiers(engine):
    ok = _valid_policy()
    # rules[1] ("internal-tooling") already has require_verdict: False and no
    # allowed_verifiers key at all.
    assert _validate(engine, ok) == []


# ---------------------------------------------------------------------------
# Lint checks
# ---------------------------------------------------------------------------

def test_lint_duplicate_rule_id_across_rules_and_hard_floor_rejected(engine):
    bad = _valid_policy()
    bad["policy"]["hard_floor_rules"][0]["id"] = "prod-service"  # collides with rules[0].id
    violations = engine._lint_contract("policy", bad)
    assert any("duplicate rule id" in v and "prod-service" in v for v in violations)


def test_lint_require_verdict_true_with_blank_globs_rejected(engine):
    bad = _valid_policy()
    bad["policy"]["rules"][0]["globs"] = ["   "]
    violations = engine._lint_contract("policy", bad)
    assert any("prod-service" in v and "never match" in v for v in violations)


# ---------------------------------------------------------------------------
# The shipped default instance
# ---------------------------------------------------------------------------

def test_shipped_default_policy_yaml_validates_cleanly(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "policy")
    instance = engine.load_contract_instance(REPO_ROOT / "core" / "policy" / "policy.yaml")
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(instance, schema, schema, base_dir)
    violations += engine._lint_contract("policy", instance)
    assert violations == [], violations


# ---------------------------------------------------------------------------
# CLI: `tessctl validate policy <file>`
# ---------------------------------------------------------------------------

def test_cli_validate_policy_valid_exits_zero(cli_root, run_cli, tmp_path):
    f = tmp_path / "policy.json"
    f.write_text(json.dumps(_valid_policy()))
    r = run_cli(cli_root, "validate", "policy", str(f))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_cli_validate_policy_invalid_exits_nonzero_json(cli_root, run_cli, tmp_path):
    bad = _valid_policy()
    del bad["policy"]["hard_floor_rules"]
    f = tmp_path / "bad_policy.json"
    f.write_text(json.dumps(bad))
    r = run_cli(cli_root, "validate", "policy", str(f), "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["valid"] is False
    assert payload["classification"]["signal"] == "schema_miss_degraded_output"
