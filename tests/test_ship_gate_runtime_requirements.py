"""Immutable-BASE ship-gate dependency pin and policy coverage."""

from __future__ import annotations

from pathlib import Path

import yaml

from conftest import REPO_ROOT


REQUIREMENTS = REPO_ROOT / ".tess" / "ci" / "ship-gate-requirements.txt"
LIVE_POLICY = REPO_ROOT / "core" / "policy" / "policy.yaml"
CORE_POLICY = REPO_ROOT / ".tess" / "core" / "policy" / "policy.yaml"
REQUIREMENTS_REL = ".tess/ci/ship-gate-requirements.txt"
PY_YAML_HASH = "0f29edc409a6392443abf94b9cf89ce99889a1dd5376d94316ae5145dfedd5d6"


def _policy() -> dict:
    return yaml.safe_load(LIVE_POLICY.read_text(encoding="utf-8"))


def test_ship_gate_requirement_is_exact_binary_hash_pin():
    effective = [
        line.strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert effective == [
        "PyYAML==6.0.3 \\",
        f"--hash=sha256:{PY_YAML_HASH}",
    ]


def test_ci_dependency_path_is_covered_by_mirrored_security_policy(engine):
    assert CORE_POLICY.read_bytes() == LIVE_POLICY.read_bytes()
    policy = _policy()
    rule = next(
        item for item in policy["policy"]["rules"]
        if item["id"] == "tess-os-security-tier-doctrine"
    )
    assert ".tess/ci/**" in rule["globs"]
    assert rule["require_verdict"] is True
    assert set(rule["allowed_verifiers"]) == {"Reid", "Cyra"}
    assert engine.path_matches_globs(REQUIREMENTS_REL, rule["globs"])


def test_ci_dependency_change_without_verdict_is_denied(engine):
    policy = _policy()
    matches, hard_floor = engine._gate_classify_paths(policy, [REQUIREMENTS_REL])
    assert hard_floor == {}
    assert REQUIREMENTS_REL in matches
    reasons = engine._gate_covering_gap_report(
        matches,
        [],
        {REQUIREMENTS_REL: {"candidate-blob"}},
        REPO_ROOT,
        policy,
    )
    assert any(
        REQUIREMENTS_REL in reason and "no covering APPROVE verdict" in reason
        for reason in reasons
    )


def test_policy_mirror_lock_hash_is_current(engine):
    lock = engine.load_lock(REPO_ROOT)
    row = lock["files"][".tess/core/policy/policy.yaml"]
    assert row["tier"] == "security"
    assert Path(REPO_ROOT / row["live_path"]).read_bytes() == CORE_POLICY.read_bytes()
    assert engine.sha256_file(CORE_POLICY) == row["base_sha"]
