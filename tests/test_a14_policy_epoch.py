"""A14 normal-PR policy attenuation must fail closed.

No verifier/sign-off identity is generated or used here.  These reverse tests
prove that an ordinary candidate range cannot weaken the policy floor even if
the checkout bytes are swapped after the candidate commit is created.
"""

from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT


GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "A14 Test",
    "GIT_AUTHOR_EMAIL": "a14@tess.test",
    "GIT_COMMITTER_NAME": "A14 Test",
    "GIT_COMMITTER_EMAIL": "a14@tess.test",
}


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, env=GIT_ENV,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _rule(rule_id="prod", globs=None, allowed=None):
    return {
        "id": rule_id,
        "description": "protected production surface",
        "globs": globs or ["src/prod/**"],
        "classification": ["prod_touching"],
        "require_verdict": True,
        "allowed_verifiers": allowed or ["Reid"],
    }


def _hard_floor(rule_id="money", globs=None, category="money_movement"):
    return {
        "id": rule_id,
        "description": "operator-controlled hard floor",
        "globs": globs or ["billing/**"],
        "category": category,
    }


def _key(fingerprint="A" * 40, public_key_file=".tess/keys/verifiers/reid.asc"):
    return {"fingerprint": fingerprint, "public_key_file": public_key_file}


def _policy(rules=None, hard_floors=None, verifier_keys=None, signoff_keys=None):
    return {
        "policy": {
            "version": 1,
            "rules": list(rules if rules is not None else [_rule()]),
            "verifier_keys": dict(verifier_keys or {}),
            "signoff_keys": dict(signoff_keys or {}),
            "hard_floor_rules": list(hard_floors or []),
        }
    }


def _repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "core" / "contracts", root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True)
    (root / "core" / "policy" / "policy.yaml").write_text(
        yaml.safe_dump(_policy(), sort_keys=False), encoding="utf-8",
    )
    (root / "src" / "prod").mkdir(parents=True)
    (root / "src" / "prod" / "app.py").write_text("print('v1')\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "a14@tess.test")
    _git(root, "config", "user.name", "A14 Test")
    return root, _commit(root, "baseline")


def _run_gate(root: Path, phase: str, base: str, head: str):
    result = subprocess.run(
        [
            sys.executable, str(REPO_ROOT / ".tess" / "bin" / "tessctl"),
            "gate", phase, "--base", base, "--head", head, "--json",
        ],
        cwd=str(root), env={**os.environ, "TESS_ROOT": str(root)},
        capture_output=True, text=True,
    )
    return result, json.loads(result.stdout)


@pytest.mark.parametrize(
    ("baseline", "candidate", "expected"),
    [
        (_policy(), _policy([]), "rule 'prod' was removed"),
        (
            _policy(),
            _policy([{**_rule(), "require_verdict": False}]),
            "disabled require_verdict",
        ),
        (
            _policy([_rule(globs=["src/prod/**", "infra/prod/**"])]),
            _policy([_rule(globs=["src/prod/**"])]),
            "removed or rewrote established glob",
        ),
        (
            _policy(),
            _policy([{**_rule(), "classification": []}]),
            "removed classification",
        ),
        (
            _policy(),
            _policy([_rule(allowed=["Reid", "Quinn"])]),
            "widened allowed_verifiers",
        ),
        (
            _policy(hard_floors=[_hard_floor()]),
            _policy(hard_floors=[]),
            "hard-floor rule 'money' was removed",
        ),
        (
            _policy(hard_floors=[_hard_floor()]),
            _policy(hard_floors=[_hard_floor(category="destructive_prod_data")]),
            "changed category",
        ),
        (
            _policy(hard_floors=[_hard_floor(globs=["billing/**", "ledger/**"])]),
            _policy(hard_floors=[_hard_floor(globs=["billing/**"])]),
            "removed or rewrote established glob",
        ),
    ],
)
def test_full_attenuation_matrix_requires_external_policy_epoch(
    engine, baseline, candidate, expected,
):
    reasons = engine._gate_policy_attenuation_reasons(baseline, candidate)
    assert any(expected in reason for reason in reasons)


def test_additive_rule_and_glob_expansion_remain_normal_pr_changes(engine):
    candidate = _policy([
        {**_rule(globs=["src/prod/**", "infra/prod/**"]),
         "classification": ["prod_touching", "client_facing"]},
        _rule("client", ["client/**"]),
    ])
    assert engine._gate_policy_attenuation_reasons(_policy(), candidate) == []


def test_narrower_verifier_set_remains_a_normal_pr_change(engine):
    baseline = _policy([_rule(allowed=["Reid", "Quinn"])])
    candidate = _policy([_rule(allowed=["Reid"])])
    assert engine._gate_policy_attenuation_reasons(baseline, candidate) == []


@pytest.mark.parametrize(
    ("baseline_keys", "candidate_keys"),
    [
        ({}, {"Reid": _key()}),
        ({"Reid": _key()}, {}),
        ({"Reid": _key()}, {"Cyra": _key()}),
        ({"Reid": _key()}, {"Reid": _key("B" * 40)}),
        (
            {"Reid": _key()},
            {"Reid": _key(public_key_file=".tess/keys/verifiers/reid-v2.asc")},
        ),
    ],
    ids=("add", "remove", "identity-rename", "fingerprint-rotate", "key-path-change"),
)
@pytest.mark.parametrize("registry", ("verifier_keys", "signoff_keys"))
def test_any_trust_registry_delta_requires_external_policy_epoch(
    engine, registry, baseline_keys, candidate_keys,
):
    kwargs = {registry: baseline_keys}
    baseline = _policy(**kwargs)
    kwargs = {registry: candidate_keys}
    candidate = _policy(**kwargs)

    reasons = engine._gate_policy_attenuation_reasons(baseline, candidate)

    assert any(f"trust registry '{registry}' changed" in reason for reason in reasons)


@pytest.mark.parametrize("registry", ("verifier_keys", "signoff_keys"))
def test_unchanged_trust_registry_remains_equal(engine, registry):
    keys = {"Reid" if registry == "verifier_keys" else "Xavier": _key()}
    kwargs = {registry: keys}
    assert engine._gate_policy_attenuation_reasons(
        _policy(**kwargs), _policy(**kwargs),
    ) == []


@pytest.mark.parametrize("registry", ("verifier_keys", "signoff_keys"))
def test_removing_present_empty_registry_is_an_epoch_delta(engine, registry):
    baseline = _policy()
    candidate = _policy()
    candidate["policy"].pop(registry)

    reasons = engine._gate_policy_attenuation_reasons(baseline, candidate)

    assert any(f"trust registry '{registry}' changed" in reason for reason in reasons)


@pytest.mark.parametrize("registry", ("verifier_keys", "signoff_keys"))
@pytest.mark.parametrize("phase", ("ci", "pre-push"))
def test_removing_present_empty_registry_is_denied_in_authoritative_gate_modes(
    tmp_path, phase, registry,
):
    root, base = _repo(tmp_path)
    policy_path = root / "core" / "policy" / "policy.yaml"
    candidate = _policy()
    candidate["policy"].pop(registry)
    policy_path.write_text(
        yaml.safe_dump(candidate, sort_keys=False), encoding="utf-8",
    )
    head = _commit(root, f"attempt removal of present empty {registry}")

    result, payload = _run_gate(root, phase, base, head)

    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["blocked"] is True
    assert any(reason.startswith("POLICY_EPOCH_RESET_REQUIRED:") for reason in payload["reasons"])


@pytest.mark.parametrize("phase", ("ci", "pre-push"))
@pytest.mark.parametrize(
    ("registry", "baseline_keys", "candidate_keys"),
    [
        ("verifier_keys", {}, {"Reid": _key()}),
        ("verifier_keys", {"Reid": _key()}, {"Reid": _key("B" * 40)}),
        ("signoff_keys", {}, {"Xavier": _key()}),
        (
            "signoff_keys",
            {"Xavier": _key()},
            {"Xavier": _key(public_key_file=".tess/keys/signoffs/xavier-v2.asc")},
        ),
    ],
    ids=("verifier-add", "verifier-fingerprint", "signoff-add", "signoff-path"),
)
def test_trust_registry_bootstrap_is_denied_in_authoritative_gate_modes(
    tmp_path, phase, registry, baseline_keys, candidate_keys,
):
    root, base = _repo(tmp_path)
    policy_path = root / "core" / "policy" / "policy.yaml"
    policy_path.write_text(
        yaml.safe_dump(_policy(**{registry: baseline_keys}), sort_keys=False),
        encoding="utf-8",
    )
    if baseline_keys:
        base = _commit(root, f"establish {registry} baseline")
    policy_path.write_text(
        yaml.safe_dump(_policy(**{registry: candidate_keys}), sort_keys=False),
        encoding="utf-8",
    )
    head = _commit(root, f"attempt ordinary-PR {registry} change")

    result, payload = _run_gate(root, phase, base, head)

    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["blocked"] is True
    assert any(reason.startswith("POLICY_EPOCH_RESET_REQUIRED:") for reason in payload["reasons"])


def test_committed_attenuation_is_detected_from_head_even_if_disk_is_swapped(engine, tmp_path):
    root, base = _repo(tmp_path)
    policy_path = root / "core" / "policy" / "policy.yaml"
    baseline_text = policy_path.read_text(encoding="utf-8")

    policy_path.write_text(yaml.safe_dump(_policy([]), sort_keys=False), encoding="utf-8")
    head = _commit(root, "A14 push 1: narrow policy")

    # Evaluate-then-swap reverse direction: disk looks strong, immutable HEAD
    # remains attenuated.  The decision must follow HEAD.
    policy_path.write_text(baseline_text, encoding="utf-8")
    changed = engine._gate_diff_paths(root, base, head)
    result = engine._gate_run_ship_check(root, changed, head_shas=[head], base_shas=[base])

    assert result["blocked"] is True
    assert any("POLICY_EPOCH_RESET_REQUIRED" in reason for reason in result["reasons"])


def test_merge_base_mismatch_fails_closed(engine, tmp_path):
    root, common = _repo(tmp_path)
    (root / "main.txt").write_text("main\n", encoding="utf-8")
    current_base = _commit(root, "advance target branch")
    _git(root, "checkout", "-q", "-b", "candidate", common)
    (root / "candidate.txt").write_text("candidate\n", encoding="utf-8")
    head = _commit(root, "divergent candidate")

    reasons = engine._gate_validate_single_range(root, [current_base], [head])
    assert reasons and reasons[0].startswith("MERGE_BASE_MISMATCH:")


def test_missing_policy_at_real_base_fails_closed(engine, tmp_path):
    root, _strong_base = _repo(tmp_path)
    policy_path = root / "core" / "policy" / "policy.yaml"
    policy_path.unlink()
    missing_policy_base = _commit(root, "counterfactual forced policy deletion")
    policy_path.write_text(yaml.safe_dump(_policy([]), sort_keys=False), encoding="utf-8")
    head = _commit(root, "candidate starts from missing-policy base")

    changed = engine._gate_diff_paths(root, missing_policy_base, head)
    result = engine._gate_run_ship_check(
        root, changed, head_shas=[head], base_shas=[missing_policy_base],
    )

    assert result["blocked"] is True
    assert any("IMMUTABLE_BASE_POLICY_REQUIRED" in reason for reason in result["reasons"])


def test_malformed_policy_at_real_base_fails_closed(engine, tmp_path):
    root, _strong_base = _repo(tmp_path)
    policy_path = root / "core" / "policy" / "policy.yaml"
    policy_path.write_text("policy: [\n", encoding="utf-8")
    malformed_policy_base = _commit(root, "counterfactual forced malformed policy")
    policy_path.write_text(yaml.safe_dump(_policy([]), sort_keys=False), encoding="utf-8")
    head = _commit(root, "candidate starts from malformed-policy base")

    changed = engine._gate_diff_paths(root, malformed_policy_base, head)
    result = engine._gate_run_ship_check(
        root, changed, head_shas=[head], base_shas=[malformed_policy_base],
    )

    assert result["blocked"] is True
    assert any("IMMUTABLE_BASE_POLICY_INVALID" in reason for reason in result["reasons"])


def test_empty_tree_is_the_only_policyless_bootstrap_subject(engine, tmp_path):
    root, _base = _repo(tmp_path)
    policy, policy_ref, errors = engine._gate_load_policy_at_base_strict(
        root, [engine.EMPTY_TREE_SHA],
    )

    assert policy is None
    assert policy_ref == engine.EMPTY_TREE_SHA
    assert errors == []
