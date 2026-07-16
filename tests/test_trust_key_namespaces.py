"""Verifier and operator sign-off public keys are distinct BASE trust domains."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent


def _git(root: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Trust namespace test",
        "GIT_AUTHOR_EMAIL": "trust@tess.test",
        "GIT_COMMITTER_NAME": "Trust namespace test",
        "GIT_COMMITTER_EMAIL": "trust@tess.test",
    }
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _policy(*, verifier_path: str, signoff_path: str) -> dict:
    return {
        "policy": {
            "version": 1,
            "rules": [],
            "hard_floor_rules": [],
            "verifier_keys": {
                "Reid": {"fingerprint": "A" * 40, "public_key_file": verifier_path},
            },
            "signoff_keys": {
                "Xavier": {"fingerprint": "B" * 40, "public_key_file": signoff_path},
            },
        }
    }


def test_key_path_validators_accept_only_role_specific_namespaces(engine):
    assert engine._gate_validate_verifier_key_file_rel(
        "Reid", ".tess/keys/verifiers/reid.asc",
    ) == (".tess/keys/verifiers/reid.asc", None)
    assert engine._gate_validate_signoff_key_file_rel(
        "Xavier", ".tess/keys/signoffs/xavier.asc",
    ) == (".tess/keys/signoffs/xavier.asc", None)

    for path in (
        ".tess/keys/signoffs/reid.asc",
        ".tess/keys/twiss-release-key.asc",
        "core/policy/reid.asc",
        ".tess/keys/verifiers\\reid.asc",
    ):
        accepted, reason = engine._gate_validate_verifier_key_file_rel("Reid", path)
        assert accepted is None
        assert "dedicated verifier-key namespace" in reason

    for path in (
        ".tess/keys/verifiers/xavier.asc",
        ".tess/keys/twiss-release-key.asc",
        "core/policy/xavier.asc",
        ".tess/keys/signoffs\\xavier.asc",
    ):
        accepted, reason = engine._gate_validate_signoff_key_file_rel("Xavier", path)
        assert accepted is None
        assert "dedicated sign-off-key namespace" in reason


def test_policy_schema_and_lint_reject_cross_namespace_redirects(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "policy")
    instance = _policy(
        verifier_path=".tess/keys/signoffs/reid.asc",
        signoff_path=".tess/keys/verifiers/xavier.asc",
    )

    errors = engine.schema_validate(
        instance, schema, schema, REPO_ROOT / "core" / "contracts",
    )
    errors += engine._lint_contract("policy", instance)

    assert any("verifiers" in error for error in errors)
    assert any("signoffs" in error for error in errors)


def test_shipped_policy_governs_both_key_namespaces_and_lock_pins_controls(engine):
    policy_path = REPO_ROOT / "core" / "policy" / "policy.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    matches, hard_floor = engine._gate_classify_paths(
        policy,
        [
            ".tess/keys/verifiers/reid.asc",
            ".tess/keys/signoffs/xavier.asc",
        ],
    )

    assert hard_floor == {}
    assert set(matches) == {
        ".tess/keys/verifiers/reid.asc",
        ".tess/keys/signoffs/xavier.asc",
    }
    for path, rules in matches.items():
        assert [rule["id"] for rule in rules] == ["tess-os-security-tier-doctrine"], path

    assert policy_path.read_bytes() == (
        REPO_ROOT / ".tess" / "core" / "policy" / "policy.yaml"
    ).read_bytes()
    assert (REPO_ROOT / "core" / "contracts" / "policy.schema.json").read_bytes() == (
        REPO_ROOT / ".tess" / "core" / "contracts" / "policy.schema.json"
    ).read_bytes()
    lock = yaml.safe_load((REPO_ROOT / ".tess" / "tess.lock").read_text(encoding="utf-8"))
    assert lock["files"][".tess/core/policy/policy.yaml"]["tier"] == "security"
    assert lock["files"][".tess/core/contracts/policy.schema.json"]["tier"] == "security"


def test_base_loaders_reject_cross_namespace_even_when_redirect_blob_exists(engine, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    verifier = root / ".tess" / "keys" / "verifiers" / "reid.asc"
    signoff = root / ".tess" / "keys" / "signoffs" / "xavier.asc"
    verifier.parent.mkdir(parents=True)
    signoff.parent.mkdir(parents=True)
    verifier.write_text("test-only verifier public bytes\n", encoding="utf-8")
    signoff.write_text("test-only signoff public bytes\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "BASE with isolated public-key bytes")
    base = _git(root, "rev-parse", "HEAD")
    redirected = _policy(
        verifier_path=".tess/keys/signoffs/xavier.asc",
        signoff_path=".tess/keys/verifiers/reid.asc",
    )

    verifier_blobs, verifier_errors = engine._gate_load_baseline_verifier_key_blobs(
        root, redirected, base,
    )
    signoff_blobs, signoff_errors = engine._gate_load_baseline_signoff_key_blobs(
        root, redirected, base,
    )

    assert verifier_blobs == {}
    assert signoff_blobs == {}
    assert "dedicated verifier-key namespace" in verifier_errors["Reid"]
    assert "dedicated sign-off-key namespace" in signoff_errors["Xavier"]


def _key_registry_base(
    root: Path,
    *,
    verifier_bytes: bytes,
    signoff_bytes: bytes,
) -> tuple[dict, str]:
    verifier_path = ".tess/keys/verifiers/reid.asc"
    signoff_path = ".tess/keys/signoffs/xavier.asc"
    verifier = root / verifier_path
    signoff = root / signoff_path
    verifier.parent.mkdir(parents=True)
    signoff.parent.mkdir(parents=True)
    verifier.write_bytes(verifier_bytes)
    signoff.write_bytes(signoff_bytes)
    policy = _policy(verifier_path=verifier_path, signoff_path=signoff_path)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "immutable BASE key registries")
    return policy, _git(root, "rev-parse", "HEAD")


def test_policy_lint_rejects_primary_fingerprint_reuse_across_roles(engine):
    instance = _policy(
        verifier_path=".tess/keys/verifiers/reid.asc",
        signoff_path=".tess/keys/signoffs/xavier.asc",
    )
    instance["policy"]["signoff_keys"]["Xavier"]["fingerprint"] = "A" * 40

    errors = engine._lint_contract("policy", instance)

    assert any("PRIMARY_FINGERPRINT_REUSE_FORBIDDEN" in error for error in errors)
    assert any("distinct primary keys" in error for error in errors)


def test_immutable_base_rejects_normalized_fingerprint_alias_across_roles(
    engine, tmp_path,
):
    root = tmp_path / "fingerprint-alias"
    root.mkdir()
    policy, base = _key_registry_base(
        root,
        verifier_bytes=b"test verifier public bytes\n",
        signoff_bytes=b"different signoff public bytes\n",
    )
    policy["policy"]["verifier_keys"]["Reid"]["fingerprint"] = "A" * 40
    policy["policy"]["signoff_keys"]["Xavier"]["fingerprint"] = ":".join(
        ["aa"] * 20
    )

    state = engine._gate_load_baseline_key_registry_state(root, policy, base)

    for role, name in (("verifier", "Reid"), ("signoff", "Xavier")):
        blobs, errors = state[role]
        assert blobs == {}
        assert "PRIMARY_FINGERPRINT_REUSE_FORBIDDEN" in errors[name]
        assert "distinct primary keys" in errors[name]


def test_immutable_base_rejects_identical_public_key_bytes_across_roles(
    engine, tmp_path,
):
    root = tmp_path / "identical-key-bytes"
    root.mkdir()
    shared = b"test-only identical OpenPGP public export bytes\n"
    policy, base = _key_registry_base(
        root,
        verifier_bytes=shared,
        signoff_bytes=shared,
    )

    state = engine._gate_load_baseline_key_registry_state(root, policy, base)

    for role, name in (("verifier", "Reid"), ("signoff", "Xavier")):
        blobs, errors = state[role]
        assert blobs == {}
        assert "PRIMARY_KEY_BYTES_REUSE_FORBIDDEN" in errors[name]
        assert "role or alias reuse fails closed" in errors[name]


def _namespace_gate_repo(root: Path, *, existing_path: str | None = None) -> str:
    engine_dest = root / ".tess" / "bin" / "tessctl"
    engine_dest.parent.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / ".tess" / "bin" / "tessctl", engine_dest)
    os.chmod(engine_dest, 0o755)
    contracts = root / "core" / "contracts"
    contracts.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "core" / "contracts" / "policy.schema.json", contracts)
    shutil.copy2(REPO_ROOT / "core" / "contracts" / "verdict.schema.json", contracts)
    policy = {
        "policy": {
            "version": 1,
            "rules": [{
                "id": "trust-key-registry",
                "description": "test-only trust registry governance",
                "globs": [
                    ".tess/keys/verifiers/**",
                    ".tess/keys/signoffs/**",
                ],
                "classification": ["prod_touching"],
                "require_verdict": True,
                "allowed_verifiers": ["Reid", "Cyra"],
            }],
            "hard_floor_rules": [],
            "verifier_keys": {},
            "signoff_keys": {},
        }
    }
    policy_path = root / "core" / "policy" / "policy.yaml"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")
    if existing_path:
        path = root / existing_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test-only BASE public bytes\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "BASE")
    return _git(root, "rev-parse", "HEAD")


@pytest.mark.parametrize("namespace", ["verifiers", "signoffs"])
@pytest.mark.parametrize("transition", ["add", "modify"])
def test_ordinary_add_and_modify_key_transitions_are_policy_blocked(
    run_cli, tmp_path, namespace, transition,
):
    root = tmp_path / f"{namespace}-{transition}"
    root.mkdir()
    rel = f".tess/keys/{namespace}/test-only.asc"
    base = _namespace_gate_repo(
        root, existing_path=rel if transition == "modify" else None,
    )
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"test-only {transition} candidate public bytes\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", f"{transition} {namespace} key bytes")
    head = _git(root, "rev-parse", "HEAD")

    result = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout, result.stderr
    payload = json.loads(result.stdout)
    assert payload["authoritative"] is False
    assert payload["blocked"] is True
    assert rel in payload["changed_paths"]
    assert any(rel in reason and "no covering APPROVE" in reason for reason in payload["reasons"])


def test_policy_schema_mirrors_remain_valid_json():
    for rel in (
        "core/contracts/policy.schema.json",
        ".tess/core/contracts/policy.schema.json",
    ):
        json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))
