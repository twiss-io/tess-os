"""Reverse-direction checks for the advisory AEC governance defaults."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from conftest import REPO_ROOT
from tools import aec_support_policy_validator as validator
from tools.validate_aec_support_policy import main as cli_main


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())


def _fixture_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    for relative in (
        validator.SCHEMA_PATH,
        validator.POLICY_PATH,
        Path("adapters/manifests/claude-code.adapter-manifest.json"),
        Path("README.md"),
        Path("docs/STATUS.md"),
        validator.ADR_PATH,
    ):
        _copy_file(REPO_ROOT / relative, root / relative)
    return root


def _read_policy(root: Path) -> Dict[str, object]:
    return json.loads((root / validator.POLICY_PATH).read_text(encoding="utf-8"))


def _write_policy(root: Path, data: Dict[str, object]) -> None:
    (root / validator.POLICY_PATH).write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def _tree_bytes(root: Path) -> List[Tuple[str, bytes]]:
    return [
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    ]


def _tier(policy: Dict[str, object], name: str) -> Dict[str, object]:
    tiers = policy["security_tiers"]
    assert isinstance(tiers, list)
    return next(item for item in tiers if isinstance(item, dict) and item.get("tier") == name)


def test_real_checkout_contract_and_docs_are_consistent():
    assert validator.validate_repository(REPO_ROOT) == []


def test_aec_decision_relative_links_resolve_inside_repository():
    source = (REPO_ROOT / validator.ADR_PATH).read_text(encoding="utf-8")
    destinations = re.findall(r"\[[^\]]+\]\(([^)]+)\)", source)
    assert destinations
    for destination in destinations:
        assert not destination.startswith(("http://", "https://", "/"))
        target = (REPO_ROOT / validator.ADR_PATH.parent / destination).resolve()
        target.relative_to(REPO_ROOT.resolve())
        assert target.is_file(), destination


def test_cli_is_stable_advisory_output_and_validator_is_read_only(tmp_path, capsys, monkeypatch):
    root = _fixture_repository(tmp_path)
    before = _tree_bytes(root)

    assert cli_main(["--root", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "advisory": True,
        "runtime_enforcement": False,
        "findings": [],
        "valid": True,
    }
    assert _tree_bytes(root) == before

    source = Path(validator.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
    )
    assert not {"socket", "subprocess", "urllib", "http", "requests"} & imports


def test_strict_json_and_schema_drift_fail_closed(tmp_path):
    root = _fixture_repository(tmp_path)
    policy_path = root / validator.POLICY_PATH
    text = policy_path.read_text(encoding="utf-8")
    policy_path.write_text(
        text.replace(
            '"schema_version": "tess.aec-support-policy.v1",',
            '"schema_version": "tess.aec-support-policy.v1",\n  "schema_version": "tess.aec-support-policy.v1",',
            1,
        ),
        encoding="utf-8",
    )
    findings = validator.validate_repository(root)
    assert any("duplicate object key 'schema_version'" in finding for finding in findings)

    root = _fixture_repository(tmp_path / "schema")
    schema_path = root / validator.SCHEMA_PATH
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["additionalProperties"] = True
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    findings = validator.validate_repository(root)
    assert any("closed top-level object" in finding for finding in findings)


def test_high_assurance_cannot_be_claimed_without_independent_evidence(tmp_path):
    root = _fixture_repository(tmp_path)
    policy = _read_policy(root)
    protected = _tier(policy, "protected-repository")
    protected["implementation_status"] = "available"
    evidence = protected["required_evidence"]
    assert isinstance(evidence, list)
    evidence.remove("independent-execution-receipt")
    _write_policy(root, policy)

    findings = validator.validate_repository(root)
    assert any("high-assurance claim lacks" in finding for finding in findings)
    assert any("remain 'planned'" in finding for finding in findings)


@pytest.mark.parametrize("tier_name", ["local-informational", "auditable-non-protected"])
def test_c1_and_c2_runtime_tiers_cannot_be_promoted_while_enforcement_is_planned(
    tmp_path, tier_name
):
    root = _fixture_repository(tmp_path)
    policy = _read_policy(root)
    _tier(policy, tier_name)["implementation_status"] = "available"
    _write_policy(root, policy)
    findings = validator.validate_repository(root)
    assert any("remain 'planned'" in finding for finding in findings)


def test_same_user_boundary_cannot_self_promote_above_t1(tmp_path):
    root = _fixture_repository(tmp_path)
    policy = _read_policy(root)
    boundary = policy["trust_boundary"]
    assert isinstance(boundary, dict)
    boundary["same_user_ceiling"] = "T3"
    boundary["above_t1_requires"] = ["producer-self-report"]
    _write_policy(root, policy)

    findings = validator.validate_repository(root)
    assert any("same_user_ceiling: must be T1" in finding for finding in findings)
    assert any("independent receipt and immutable artifact binding" in finding for finding in findings)


def test_above_t1_requires_receipt_and_immutable_binding_independently(tmp_path):
    for index, missing in enumerate(
        ("independent-execution-receipt", "immutable-artifact-binding")
    ):
        root = _fixture_repository(tmp_path / str(index))
        policy = _read_policy(root)
        boundary = policy["trust_boundary"]
        assert isinstance(boundary, dict)
        requirements = boundary["above_t1_requires"]
        assert isinstance(requirements, list)
        requirements.remove(missing)
        _write_policy(root, policy)
        findings = validator.validate_repository(root)
        assert any("independent receipt and immutable artifact binding" in finding for finding in findings)


def test_adapter_c3_cannot_imply_or_satisfy_aec_c3_t2(tmp_path):
    root = _fixture_repository(tmp_path)
    adapter = json.loads(
        (root / "adapters/manifests/claude-code.adapter-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert adapter["support_level"] == "C3"
    policy = _read_policy(root)
    assert _tier(policy, "protected-repository")["minimum"] == {
        "completeness": "AEC-C3",
        "trust": "T2",
    }
    boundary = policy["trust_boundary"]
    assert isinstance(boundary, dict)
    boundary["adapter_capability_levels_do_not_satisfy_aec"] = False
    _write_policy(root, policy)
    findings = validator.validate_repository(root)
    assert any("adapter C-levels cannot imply AEC assurance" in finding for finding in findings)


def test_sensitive_paths_and_secret_categories_cannot_be_admitted(tmp_path):
    root = _fixture_repository(tmp_path)
    policy = _read_policy(root)
    defaults = policy["data_defaults"]
    assert isinstance(defaults, dict)
    paths = defaults["excluded_index_paths"]
    categories = defaults["excluded_durable_categories"]
    assert isinstance(paths, list) and isinstance(categories, list)
    paths.remove("clients/**")
    categories.remove("secret-value")
    defaults["included_index_paths"] = ["clients/**"]
    defaults["allowed_durable_categories"] = ["secret-value"]
    _write_policy(root, policy)

    findings = validator.validate_repository(root)
    assert any("sensitive path exclusions cannot be weakened" in finding for finding in findings)
    assert any("secret/raw exclusions cannot be weakened" in finding for finding in findings)
    assert any("field 'included_index_paths' is not allowed" in finding for finding in findings)
    assert any("field 'allowed_durable_categories' is not allowed" in finding for finding in findings)


def test_cloud_credentials_provider_and_cost_defaults_fail_closed(tmp_path):
    root = _fixture_repository(tmp_path)
    policy = _read_policy(root)
    provider = policy["provider_execution"]
    credentials = policy["credentials"]
    cost = policy["cost"]
    products = policy["products"]
    assert all(isinstance(item, dict) for item in (provider, credentials, cost, products))
    provider["default"] = "enabled"
    provider["required_per_run_declarations"] = ["endpoint"]
    credentials["ambient_environment_inheritance"] = "allowed"
    cost["default_budget_usd"] = 10
    cost["default_hard_stop"] = False
    cloud = products["tess_cloud"]
    assert isinstance(cloud, dict)
    cloud["status"] = "available"
    cloud["enabled"] = True
    _write_policy(root, policy)

    findings = validator.validate_repository(root)
    assert any("provider_execution.default: must be disabled" in finding for finding in findings)
    assert any("endpoint, region, retention, and tool profile" in finding for finding in findings)
    assert any("must deny ambient/secret context" in finding for finding in findings)
    assert any("default_budget_usd: must be numeric zero" in finding for finding in findings)
    assert any("default_hard_stop: must be true" in finding for finding in findings)
    assert any("products.tess_cloud: must remain planned and disabled" in finding for finding in findings)


def test_public_docs_cannot_promote_planned_runtime_or_products(tmp_path):
    root = _fixture_repository(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\n| Tess Cloud | **Available** | Contradictory added claim. |\n",
        encoding="utf-8",
    )
    status = root / "docs/STATUS.md"
    status.write_text(
        status.read_text(encoding="utf-8")
        + "\n| AEC runtime assurance grading and enforcement | **Available** | Contradictory added claim. |\n",
        encoding="utf-8",
    )
    findings = validator.validate_repository(root)
    assert any("README.md:" in finding and "planned-only" in finding for finding in findings)
    assert any("docs/STATUS.md:" in finding and "planned-only" in finding for finding in findings)


def test_symlinked_contract_input_is_rejected(tmp_path):
    root = _fixture_repository(tmp_path)
    policy_path = root / validator.POLICY_PATH
    outside = root / "outside.json"
    outside.write_bytes(policy_path.read_bytes())
    policy_path.unlink()
    policy_path.symlink_to(outside)
    findings = validator.validate_repository(root)
    assert any("aec-support-policy.template.json: symlinks are not allowed" in finding for finding in findings)
