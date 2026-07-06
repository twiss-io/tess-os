"""
Phase 2 — `tessctl gate` decision engine (docs/ULTIMATE_FRAMEWORK_PLAN.md
Design Decisions #2 "deterministic gate spine" + #6 "verification produces a
gateable artifact").

Coverage (per the dispatch brief's explicit test list):
  * the gate BLOCKS a prod-touching change with no verdict
  * ALLOWS it with a valid covering APPROVE verdict
  * BLOCKS with a BLOCK / HIGH-unaccepted verdict
  * BLOCKS a schema-invalid contract
  * the policy correctly classifies paths
  * fail-closed on error (bad ref, missing/invalid policy, missing hard-floor
    sign-off)
  * `tessctl gate pre-commit` (staged-only, contract validation)
  * `tessctl gate pre-push` explicit --base/--head AND the git stdin protocol
  * `tessctl gate ci` (same logic, explicit refs)

Hook install + real git commit/push firing is covered separately in
tests/test_gate_hooks.py (mirrors tests/test_hook_coexistence.py's pattern
for the vault guard).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"

HAS_GIT = shutil.which("git") is not None
pytestmark = pytest.mark.skipif(not HAS_GIT, reason="git required")


def _git(root, *args, check=True, input_text=None):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@tess.test",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@tess.test",
    }
    r = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, env=env, input=input_text,
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}\n{r.stdout}")
    return r


_TEST_POLICY = {
    "policy": {
        "version": 1,
        "rules": [
            {
                "id": "prod-src",
                "description": "test-only prod rule",
                "globs": ["src/prod/**"],
                "classification": ["prod_touching"],
                "require_verdict": True,
                "allowed_verifiers": ["Reid"],
            },
        ],
        "hard_floor_rules": [
            {
                "id": "money",
                "category": "money_movement",
                "description": "test-only hard floor",
                "globs": ["payments/**"],
            },
        ],
    }
}


def _init_repo(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@tess.test")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")


@pytest.fixture
def gate_repo(project):
    """A real git repo with the real core/contracts/*.schema.json + a
    test-scoped core/policy/policy.yaml, one initial commit."""
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)
    (root / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(_TEST_POLICY), encoding="utf-8")

    _init_repo(root)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")
    return root


def _base_sha(root):
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _commit_all(root, message):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _valid_verdict(covers_paths, disposition="APPROVE", verifier="Reid", findings=None):
    return {
        "verifier": verifier,
        "output_domain": "Code diff / PR",
        "primary_artifacts_read": list(covers_paths),
        "findings": findings or [],
        "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "summary_line": "Reviewed. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Top priority: none.",
        "disposition": disposition,
        "covers_paths": list(covers_paths),
    }


def _write_verdict(root, rel_path, verdict_dict):
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\n" + yaml.safe_dump(verdict_dict) + "---\n\n# Verdict body (not part of the contract instance)\n",
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# 1) BLOCKS a prod-touching change with no verdict
# ---------------------------------------------------------------------------

def test_ci_blocks_prod_touching_change_with_no_verdict(gate_repo, run_cli):
    base = _base_sha(gate_repo)
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    head = _commit_all(gate_repo, "add prod change")

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("src/prod/app.py" in reason and "no covering APPROVE verdict" in reason for reason in payload["reasons"])


# ---------------------------------------------------------------------------
# 2) ALLOWS with a valid covering APPROVE verdict
# ---------------------------------------------------------------------------

def test_ci_allows_prod_touching_change_with_covering_approve_verdict(gate_repo, run_cli):
    base = _base_sha(gate_repo)
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    _write_verdict(
        gate_repo, "missions/m1/verdicts/prod-src.verdict.md",
        _valid_verdict(covers_paths=["src/prod/**"]),
    )
    head = _commit_all(gate_repo, "add prod change + covering verdict")

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is False
    assert payload["reasons"] == []


def test_verdict_covering_a_different_path_does_not_satisfy(gate_repo, run_cli):
    """A real, valid APPROVE verdict that covers an UNRELATED path must not
    satisfy a rule on a path it never scoped itself to (fail-closed by
    omission, not fail-open)."""
    base = _base_sha(gate_repo)
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    _write_verdict(
        gate_repo, "missions/m1/verdicts/unrelated.verdict.md",
        _valid_verdict(covers_paths=["docs/**"]),
    )
    head = _commit_all(gate_repo, "prod change + unrelated verdict")

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True


# ---------------------------------------------------------------------------
# 3) BLOCKS with a BLOCK / HIGH-unaccepted verdict
# ---------------------------------------------------------------------------

def test_ci_blocks_when_only_covering_verdict_is_disposition_block(gate_repo, run_cli):
    base = _base_sha(gate_repo)
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    _write_verdict(
        gate_repo, "missions/m1/verdicts/prod-src.verdict.md",
        _valid_verdict(covers_paths=["src/prod/**"], disposition="BLOCK"),
    )
    head = _commit_all(gate_repo, "prod change + BLOCK verdict")

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("no covering APPROVE verdict" in reason for reason in payload["reasons"])


def test_ci_blocks_when_covering_verdict_has_unaccepted_high_finding(gate_repo, run_cli):
    """A verdict claiming APPROVE with a HIGH finding and no
    accepted_high_findings is itself schema-INVALID (Phase 0's own H2 rule) —
    it can never count as a covering verdict, so the ship-gate still blocks."""
    base = _base_sha(gate_repo)
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    bad_verdict = _valid_verdict(
        covers_paths=["src/prod/**"],
        disposition="APPROVE",
        findings=[
            {
                "severity": "HIGH",
                "location": "src/prod/app.py:1",
                "finding": "missing authz",
                "risk": "privilege escalation",
                "fix": "add role check",
            }
        ],
    )
    bad_verdict["severity_counts"]["high"] = 1
    _write_verdict(gate_repo, "missions/m1/verdicts/prod-src.verdict.md", bad_verdict)
    head = _commit_all(gate_repo, "prod change + invalid HIGH+APPROVE verdict")

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("no covering APPROVE verdict" in reason for reason in payload["reasons"])

    # Sanity: with the HIGH finding explicitly accepted, the SAME shape passes.
    ok_verdict = _valid_verdict(
        covers_paths=["src/prod/**"],
        disposition="APPROVE",
        findings=bad_verdict["findings"],
    )
    ok_verdict["severity_counts"]["high"] = 1
    ok_verdict["accepted_high_findings"] = [
        {"location": "src/prod/app.py:1", "rationale": "Tracked as a fast-follow; feature-flagged off."}
    ]
    _write_verdict(gate_repo, "missions/m1/verdicts/prod-src.verdict.md", ok_verdict)
    head2 = _commit_all(gate_repo, "accept the HIGH finding")
    r2 = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head2, "--json")
    assert r2.returncode == 0, r2.stdout + r2.stderr


# ---------------------------------------------------------------------------
# 4) BLOCKS a schema-invalid contract
# ---------------------------------------------------------------------------

def test_pre_commit_blocks_schema_invalid_staged_brief(gate_repo, run_cli):
    brief_path = gate_repo / "missions" / "m1" / "briefs" / "task1.brief.md"
    brief_path.parent.mkdir(parents=True)
    # Missing several required six-field-contract keys — schema-invalid.
    brief_path.write_text(
        "---\nobjective: Do the thing.\n---\n\nBody.\n", encoding="utf-8"
    )
    _git(gate_repo, "add", "-A")

    r = run_cli(gate_repo, "gate", "pre-commit", "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("missions/m1/briefs/task1.brief.md" in reason for reason in payload["reasons"])


def test_pre_commit_passes_valid_staged_brief(gate_repo, run_cli):
    brief_path = gate_repo / "missions" / "m1" / "briefs" / "task1.brief.md"
    brief_path.parent.mkdir(parents=True)
    brief_path.write_text(
        "---\n"
        "objective: Do the thing.\n"
        "output_contract: /tmp/out.md — sections [A]\n"
        "tools_sources_constraints: Read /tmp/in.md; every number traces to a quoted row.\n"
        "not_responsible_for: The other thing.\n"
        "milestones: []\n"
        "escalation_trigger: If blocked, stop and ask.\n"
        "---\n\nBody.\n",
        encoding="utf-8",
    )
    _git(gate_repo, "add", "-A")

    r = run_cli(gate_repo, "gate", "pre-commit", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is False


def test_ci_blocks_schema_invalid_committed_verdict(gate_repo, run_cli):
    """A schema-invalid verdict landing in the diff is itself a [contract]
    violation, independent of whether it would have covered anything."""
    base = _base_sha(gate_repo)
    v = gate_repo / "missions" / "m1" / "verdicts" / "broken.verdict.json"
    v.parent.mkdir(parents=True)
    v.write_text(json.dumps({"verifier": "Reid"}), encoding="utf-8")  # missing required fields
    head = _commit_all(gate_repo, "add broken verdict")

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert any("[contract]" in reason and "broken.verdict.json" in reason for reason in payload["reasons"])


# ---------------------------------------------------------------------------
# 5) the policy correctly classifies paths
# ---------------------------------------------------------------------------

def test_classify_paths_matches_only_globs_that_apply(engine):
    policy_instance = _TEST_POLICY
    path_matches, hard_floor_matches = engine._gate_classify_paths(
        policy_instance,
        ["src/prod/app.py", "src/other/thing.py", "payments/charge.py", "README.md"],
    )
    assert "src/prod/app.py" in path_matches
    assert "src/other/thing.py" not in path_matches
    assert "README.md" not in path_matches

    assert "payments/charge.py" in hard_floor_matches
    assert "src/prod/app.py" not in hard_floor_matches


def test_classify_paths_a_path_can_match_both_ordinary_and_hard_floor(engine):
    policy_instance = {
        "policy": {
            "version": 1,
            "rules": [{
                "id": "r", "description": "d", "globs": ["payments/**"],
                "classification": ["prod_touching"], "require_verdict": True,
                "allowed_verifiers": ["Reid"],
            }],
            "hard_floor_rules": [{
                "id": "money", "category": "money_movement", "description": "d",
                "globs": ["payments/**"],
            }],
        }
    }
    path_matches, hard_floor_matches = engine._gate_classify_paths(policy_instance, ["payments/charge.py"])
    assert "payments/charge.py" in path_matches
    assert "payments/charge.py" in hard_floor_matches


def test_infer_contract_type_by_convention(engine):
    assert engine._gate_infer_contract_type("missions/m1/briefs/x.md") == "brief"
    assert engine._gate_infer_contract_type("missions/m1/verdicts/x.verdict.md") == "verdict"
    assert engine._gate_infer_contract_type("missions/m1/returns/x.json") == "return-manifest"
    assert engine._gate_infer_contract_type("some/dir/plan.yaml") == "crew-plan"
    assert engine._gate_infer_contract_type("core/policy/policy.yaml") == "policy"
    assert engine._gate_infer_contract_type("src/prod/app.py") is None


# ---------------------------------------------------------------------------
# Hard floor: never satisfiable by a verdict alone; needs a sign-off artifact
# ---------------------------------------------------------------------------

def test_ci_blocks_hard_floor_match_even_with_covering_approve_verdict(gate_repo, run_cli):
    base = _base_sha(gate_repo)
    (gate_repo / "payments").mkdir(parents=True)
    (gate_repo / "payments" / "charge.py").write_text("refund()\n")
    # Even a perfectly valid, covering APPROVE verdict must NOT clear a hard floor.
    _write_verdict(
        gate_repo, "missions/m1/verdicts/payments.verdict.md",
        _valid_verdict(covers_paths=["payments/**"]),
    )
    head = _commit_all(gate_repo, "payments change + APPROVE verdict (should not matter)")

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert any("HARD FLOOR" in reason and "money_movement" in reason for reason in payload["reasons"])


def test_ci_allows_hard_floor_match_with_valid_signoff_artifact(gate_repo, run_cli):
    base = _base_sha(gate_repo)
    (gate_repo / "payments").mkdir(parents=True)
    (gate_repo / "payments" / "charge.py").write_text("refund()\n")
    signoff_dir = gate_repo / ".tess" / "gate" / "signoffs"
    signoff_dir.mkdir(parents=True, exist_ok=True)
    (signoff_dir / "money.signoff.json").write_text(json.dumps({
        "rule_id": "money",
        "category": "money_movement",
        "authorized_by": "Xavier",
        "rationale": "Reviewed refund logic change directly; approved out-of-band.",
        "authorized_at": "2026-07-07T00:00:00Z",
    }), encoding="utf-8")
    head = _commit_all(gate_repo, "payments change + human signoff")

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 0, r.stdout + r.stderr


def test_signoff_rule_id_mismatch_is_rejected(engine, tmp_path):
    signoff = tmp_path / "money.signoff.json"
    signoff.write_text(json.dumps({
        "rule_id": "some-other-rule",
        "category": "money_movement",
        "authorized_by": "Xavier",
        "rationale": "x",
        "authorized_at": "2026-07-07T00:00:00Z",
    }))
    ok, reason = engine._gate_validate_signoff(signoff, "money")
    assert ok is False
    assert "does not match" in reason


def test_signoff_missing_field_is_rejected(engine, tmp_path):
    signoff = tmp_path / "money.signoff.json"
    signoff.write_text(json.dumps({"rule_id": "money", "category": "money_movement"}))
    ok, reason = engine._gate_validate_signoff(signoff, "money")
    assert ok is False
    assert "missing required field" in reason


# ---------------------------------------------------------------------------
# 6) Fail-closed on error
# ---------------------------------------------------------------------------

def test_ci_fails_closed_on_bad_ref(gate_repo, run_cli):
    r = run_cli(gate_repo, "gate", "ci", "--base", "not-a-real-ref", "--head", "HEAD", "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True


def test_ci_fails_closed_when_policy_file_missing(gate_repo, run_cli):
    (gate_repo / "core" / "policy" / "policy.yaml").unlink()
    base = _base_sha(gate_repo)
    (gate_repo / "anything.txt").write_text("x\n")
    head = _commit_all(gate_repo, "no policy file present")

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("no policy instance found" in reason for reason in payload["reasons"])


def test_ci_fails_closed_when_policy_file_is_invalid(gate_repo, run_cli):
    (gate_repo / "core" / "policy" / "policy.yaml").write_text("policy: {not: valid}\n", encoding="utf-8")
    base = _base_sha(gate_repo)
    (gate_repo / "anything.txt").write_text("x\n")
    head = _commit_all(gate_repo, "invalid policy file")

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True


def test_ci_passes_clean_when_nothing_changed_matches_any_rule(gate_repo, run_cli):
    base = _base_sha(gate_repo)
    (gate_repo / "docs").mkdir(parents=True)
    (gate_repo / "docs" / "notes.md").write_text("nothing special\n")
    head = _commit_all(gate_repo, "docs-only change")

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    assert payload["blocked"] is False


def test_pre_push_stdin_protocol_blocks(gate_repo, run_cli):
    """Feeds git's own pre-push stdin protocol format directly (rather than
    via a real push) to prove the stdin-parsing path independently of
    --base/--head."""
    base = _base_sha(gate_repo)
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    head = _commit_all(gate_repo, "prod change")

    stdin = f"refs/heads/main {head} refs/heads/main {'0' * 40}\n"
    r = run_cli(gate_repo, "gate", "pre-push", "--json", input_text=stdin)
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("src/prod/app.py" in reason for reason in payload["reasons"])


def test_pre_push_requires_both_base_and_head_or_neither(gate_repo, run_cli):
    r = run_cli(gate_repo, "gate", "pre-push", "--base", "HEAD~1", "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("--base and --head must both be given" in reason for reason in payload["reasons"])
