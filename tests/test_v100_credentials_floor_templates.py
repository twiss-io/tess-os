"""v1.0.0 — committed `.env` templates are outside the credentials hard floor.

`.env.example` is a public template (placeholder names, no values). While it
sat under the credentials hard floor, every release that edited it needed a
signed operator sign-off, and no sign-off key exists, so such a release could
never merge. The floor now carries a narrow `exclude_globs` carve-out for
`*.env.example` / `*.env.<name>.example`. Real secret files stay covered.

Checked here:
  * the SHIPPED policy (both copies) classifies real secrets as hard floor and
    the templates as not;
  * `tessctl gate ci` end to end: a `.env` change is blocked for want of a
    sign-off, a `.env.example` change is not;
  * the carve-out cannot apply to the push that introduces it: a baseline
    policy without the exclusion still floors `.env.example` (baseline union).
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_COPIES = [
    REPO_ROOT / "core" / "policy" / "policy.yaml",
    REPO_ROOT / ".tess" / "core" / "policy" / "policy.yaml",
]

SECRETS = [
    ".env",
    ".env.local",
    ".env.production",
    "app/.env",
    "app/.env.staging",
    "prod.env",
    "secrets/api.example",
    "secrets/token.txt",
    "vault.age",
    "keys/my-identity.age",
]
TEMPLATES = [
    ".env.example",
    "create-tess/template/.env.example",
    "starter/.env.example",
    "app/.env.local.example",
]


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _credentials_rule(policy: dict) -> dict:
    [rule] = [r for r in policy["policy"]["hard_floor_rules"] if r["id"] == "credentials"]
    return rule


def test_both_policy_copies_carry_the_same_credentials_floor():
    rules = [_credentials_rule(_load(p)) for p in POLICY_COPIES]
    assert rules[0] == rules[1]
    assert rules[0]["exclude_globs"] == ["**/*.env.example", "**/*.env.*.example"]


@pytest.mark.parametrize("policy_path", POLICY_COPIES, ids=["core", ".tess/core"])
def test_shipped_policy_floors_secrets_but_not_templates(engine, policy_path):
    _, floor = engine._gate_classify_paths(_load(policy_path), SECRETS + TEMPLATES)
    for path in SECRETS:
        assert [r["id"] for r in floor.get(path, [])] == ["credentials"], path
    for path in TEMPLATES:
        assert path not in floor, f"{path} must not need an operator sign-off"


def test_exclusion_does_not_apply_to_the_push_that_adds_it(engine):
    """Baseline union: a policy relaxation is never self-applying."""
    new = _load(POLICY_COPIES[0])
    baseline = copy.deepcopy(new)
    _credentials_rule(baseline).pop("exclude_globs")
    changed = [".env.example", ".env"]
    path_matches, floor = engine._gate_classify_paths(new, changed)
    assert ".env.example" not in floor
    engine._gate_union_baseline_matches(baseline, changed, path_matches, floor)
    assert [r["id"] for r in floor[".env.example"]] == ["credentials"]
    assert floor[".env.example"][0].get("_gate_baseline_only") is True


def test_policy_with_exclude_globs_is_schema_valid(engine):
    schema = json.loads((REPO_ROOT / "core" / "contracts" / "policy.schema.json").read_text("utf-8"))
    hf = schema["$defs"]["HardFloorRule"]
    assert "exclude_globs" in hf["properties"]
    for path in POLICY_COPIES:
        errors = engine.schema_validate(_load(path), schema, schema, REPO_ROOT / "core" / "contracts")
        assert not errors, errors


# --------------------------------------------------------------------------
# End to end through `tessctl gate ci`
# --------------------------------------------------------------------------

def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def floor_repo(project):
    root = project.root
    shutil.copytree(REPO_ROOT / "core" / "contracts", root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)
    policy = {"policy": {"version": 1, "rules": [],
                         "hard_floor_rules": [_credentials_rule(_load(POLICY_COPIES[0]))]}}
    (root / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    (root / ".env.example").write_text("API_KEY=your-key-here\n", encoding="utf-8")
    _git(root, "init", "-b", "main", "-q")
    _git(root, "config", "user.email", "test@tess.test")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")
    return root


def _gate_after_writing(root: Path, run_cli, rel_path: str) -> tuple[int, dict]:
    base = _git(root, "rev-parse", "HEAD")
    (root / rel_path).write_text("API_KEY=changed-placeholder\n", encoding="utf-8")
    _git(root, "add", "-f", rel_path)
    _git(root, "commit", "-q", "-m", f"edit {rel_path}")
    head = _git(root, "rev-parse", "HEAD")
    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    return r.returncode, json.loads(r.stdout)


def test_gate_blocks_a_dot_env_change_without_a_signoff(floor_repo, run_cli):
    code, payload = _gate_after_writing(floor_repo, run_cli, ".env")
    assert code == 1
    assert payload["blocked"] is True
    assert any(r.startswith("HARD_FLOOR_UNSATISFIED") for r in payload["reasons"]), payload


def test_gate_passes_a_dot_env_example_change_without_a_signoff(floor_repo, run_cli):
    code, payload = _gate_after_writing(floor_repo, run_cli, ".env.example")
    assert code == 0, payload
    assert payload["blocked"] is False
    assert not any(r.startswith("HARD_FLOOR") for r in payload.get("reasons", [])), payload
