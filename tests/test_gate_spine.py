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

from conftest import sign_verdict_for_test

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"

HAS_GIT = shutil.which("git") is not None
HAS_GPG = shutil.which("gpg") is not None
# Phase 2b: a covering verdict now MUST carry a valid signature to clear the
# gate, so this whole module's real-CLI ("gate_repo"/run_cli) tests require
# gpg, not just git (the pure-classification unit tests below that take only
# `engine` don't touch signing at all and would run fine without gpg, but
# gating the whole module is simpler and matches `_TOOL_REQUIREMENTS["gate"]`
# — the gate CLI itself now hard-requires gpg too).
pytestmark = pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")


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


def _policy_with_verifier_keys(root, keys):
    """A deep copy of _TEST_POLICY plus a `verifier_keys` map registering
    every generated test identity's REAL fingerprint + bundled public-key
    file (written under .tess/keys/verifiers/<name>.asc, mirroring
    core/policy/policy.yaml's own onboarding convention) — Phase 2b. Without
    this, no verdict signed by any of these throwaway test keys could ever
    verify, since `tessctl gate` only trusts fingerprints registered here."""
    keys_dir = root / ".tess" / "keys" / "verifiers"
    keys_dir.mkdir(parents=True, exist_ok=True)
    verifier_keys = {}
    for name, key in keys.items():
        asc_path = keys_dir / f"{name.lower()}.asc"
        asc_path.write_text(key.pubkey_armored, encoding="utf-8")
        verifier_keys[name] = {
            "fingerprint": key.fpr,
            "public_key_file": f".tess/keys/verifiers/{name.lower()}.asc",
        }
    policy = json.loads(json.dumps(_TEST_POLICY))  # cheap deep copy
    policy["policy"]["verifier_keys"] = verifier_keys
    return policy


@pytest.fixture
def gate_repo(project, verifier_gpg_keys):
    """A real git repo with the real core/contracts/*.schema.json + a
    test-scoped core/policy/policy.yaml (Phase 2b: registering every
    generated test verifier identity's key, so signed test verdicts can
    actually verify), one initial commit."""
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)
    policy = _policy_with_verifier_keys(root, verifier_gpg_keys)
    (root / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")

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


def _blob_sha(root, rel_path):
    """The git blob SHA-1 a file's CURRENT on-disk content would get once
    committed — `git hash-object` is a pure function of content, so this is
    valid to call BEFORE the commit that will actually introduce the blob
    (the exact sequence every HIGH-1 'covering verdict' test below uses: hash
    the file, embed the hash in the verdict, THEN commit both together)."""
    return _git(root, "hash-object", rel_path).stdout.strip()


def _valid_verdict(covers_paths, disposition="APPROVE", verifier="Reid", findings=None, artifact_hashes=None,
                    engine=None, keys=None):
    """Builds a schema-valid verdict dict. Phase 2b: when `engine` (the
    loaded tessctl module) and `keys` (a verifier_gpg_keys dict) are BOTH
    given, the verdict is also cryptographically SIGNED as `verifier` — a
    real, working signature any test wanting the gate to actually COVER a
    path must provide (an unsigned verdict, however otherwise valid, can
    never cover anything post-Phase-2b). Tests that only need a verdict to
    exist/be schema-checked (or that expect it to be rejected for an
    unrelated reason regardless of signing) can omit engine/keys and get
    the pre-Phase-2b unsigned shape."""
    verdict = {
        "verifier": verifier,
        "output_domain": "Code diff / PR",
        "primary_artifacts_read": list(covers_paths),
        "findings": findings or [],
        "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "summary_line": "Reviewed. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Top priority: none.",
        "disposition": disposition,
        "covers_paths": list(covers_paths),
    }
    if artifact_hashes is not None:
        verdict["artifact_hashes"] = dict(artifact_hashes)
    if engine is not None and keys is not None and verifier in keys:
        verdict["signature"] = sign_verdict_for_test(engine, verdict, keys[verifier])
    return verdict


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

def test_ci_allows_prod_touching_change_with_covering_approve_verdict(gate_repo, run_cli, engine, verifier_gpg_keys):
    base = _base_sha(gate_repo)
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(gate_repo, "src/prod/app.py")
    _write_verdict(
        gate_repo, "missions/m1/verdicts/prod-src.verdict.md",
        _valid_verdict(
            covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob},
            engine=engine, keys=verifier_gpg_keys,
        ),
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


def test_ci_blocks_when_covering_verdict_has_unaccepted_high_finding(gate_repo, run_cli, engine, verifier_gpg_keys):
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
    blob = _blob_sha(gate_repo, "src/prod/app.py")
    ok_verdict = _valid_verdict(
        covers_paths=["src/prod/**"],
        disposition="APPROVE",
        findings=bad_verdict["findings"],
        artifact_hashes={"src/prod/app.py": blob},
    )
    ok_verdict["severity_counts"]["high"] = 1
    ok_verdict["accepted_high_findings"] = [
        {"location": "src/prod/app.py:1", "rationale": "Tracked as a fast-follow; feature-flagged off."}
    ]
    # Sign AFTER every field is final — a signature covers the verdict's
    # FULL canonical content, so mutating severity_counts/accepted_high_findings
    # post-construction (as above) would otherwise sign stale content.
    ok_verdict["signature"] = sign_verdict_for_test(engine, ok_verdict, verifier_gpg_keys["Reid"])
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


def test_pre_push_stdin_protocol_allows_with_covering_verdict(gate_repo, run_cli, engine, verifier_gpg_keys):
    """The stdin-protocol path threads `head_shas` through to the covering-
    verdict check exactly like explicit --base/--head does — proven
    independently since _gate_changed_paths_from_stdin's return shape
    changed (HIGH-1(c)) to also surface the pushed head sha(s)."""
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(gate_repo, "src/prod/app.py")
    _write_verdict(
        gate_repo, "missions/m1/verdicts/prod-src.verdict.md",
        _valid_verdict(
            covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob},
            engine=engine, keys=verifier_gpg_keys,
        ),
    )
    head = _commit_all(gate_repo, "prod change + covering verdict")

    stdin = f"refs/heads/main {head} refs/heads/main {'0' * 40}\n"
    r = run_cli(gate_repo, "gate", "pre-push", "--json", input_text=stdin)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is False


def test_pre_push_requires_both_base_and_head_or_neither(gate_repo, run_cli):
    r = run_cli(gate_repo, "gate", "pre-push", "--base", "HEAD~1", "--json")
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("--base and --head must both be given" in reason for reason in payload["reasons"])


# ---------------------------------------------------------------------------
# Fable Phase-2 adversarial review fixes: HIGH-1 (bind coverage to the diff),
# M1 (allowed_verifiers enforced), M2 (glob semantics). Five proofs, per the
# dispatch brief:
#   (i)   a verdict clears ONLY the exact reviewed change — a subsequent edit
#         to the same path is BLOCKED again (per-change verification)
#   (ii)  a '**'/blanket verdict is REJECTED (no master key)
#   (iii) allowed_verifiers is enforced (wrong-domain APPROVE doesn't clear)
#   (iv)  the glob fixes (root .env gated; src/* doesn't span deep)
#   (v)   an uncommitted pre-push verdict doesn't clear
# ---------------------------------------------------------------------------

# (i) per-change verification -------------------------------------------------

def test_covering_verdict_only_clears_its_reviewed_content_not_a_later_edit(gate_repo, run_cli, engine, verifier_gpg_keys):
    """HIGH-1(a): a covering verdict binds to the CONTENT it reviewed (via
    artifact_hashes), not just the path glob. Re-editing the SAME path after
    the verdict was written must re-trigger the ship-gate — verification is
    per-change, not a permanent toll paid once per glob."""
    base = _base_sha(gate_repo)
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod v1')\n")
    blob_v1 = _blob_sha(gate_repo, "src/prod/app.py")
    _write_verdict(
        gate_repo, "missions/m1/verdicts/prod-src.verdict.md",
        _valid_verdict(
            covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob_v1},
            engine=engine, keys=verifier_gpg_keys,
        ),
    )
    head1 = _commit_all(gate_repo, "v1 + covering verdict")

    r1 = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head1, "--json")
    assert r1.returncode == 0, r1.stdout + r1.stderr  # v1 genuinely covered

    # Re-edit the SAME file — content changes, verdict is left untouched.
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod v2 -- different content')\n")
    head2 = _commit_all(gate_repo, "v2 -- re-edit, verdict now stale")

    r2 = run_cli(gate_repo, "gate", "ci", "--base", head1, "--head", head2, "--json")
    assert r2.returncode == 1, r2.stdout + r2.stderr
    payload = json.loads(r2.stdout)
    assert payload["blocked"] is True
    assert any(
        "src/prod/app.py" in reason and "does not record THIS path's CURRENT content" in reason
        for reason in payload["reasons"]
    )


def test_covering_verdict_does_not_cover_a_brand_new_file_under_the_same_glob(gate_repo, run_cli, engine, verifier_gpg_keys):
    """HIGH-1(a), companion case: artifact_hashes only vouches for the files
    it actually names. A brand-new file added later under the SAME
    covers_paths glob — one the verdict never reviewed — is not covered
    just because an old sibling file under that glob was."""
    base = _base_sha(gate_repo)
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(gate_repo, "src/prod/app.py")
    _write_verdict(
        gate_repo, "missions/m1/verdicts/prod-src.verdict.md",
        _valid_verdict(
            covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob},
            engine=engine, keys=verifier_gpg_keys,
        ),
    )
    head1 = _commit_all(gate_repo, "app.py + covering verdict")
    r1 = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head1, "--json")
    assert r1.returncode == 0, r1.stdout + r1.stderr

    (gate_repo / "src" / "prod" / "new_module.py").write_text("print('new')\n")
    head2 = _commit_all(gate_repo, "add new_module.py under src/prod/**")

    r2 = run_cli(gate_repo, "gate", "ci", "--base", head1, "--head", head2, "--json")
    assert r2.returncode == 1, r2.stdout + r2.stderr
    payload = json.loads(r2.stdout)
    assert payload["blocked"] is True
    assert any("src/prod/new_module.py" in reason for reason in payload["reasons"])


# (ii) master-key rejection ----------------------------------------------------

def test_blanket_covers_paths_glob_is_rejected_as_master_key(gate_repo, run_cli):
    """HIGH-1(b): a verdict may never declare '**' (or an equivalent
    blanket shape) in covers_paths to clear every future prod change in one
    review. Such a verdict is schema/lint-invalid as a whole and can never
    satisfy the ship-gate for ANY path."""
    base = _base_sha(gate_repo)
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(gate_repo, "src/prod/app.py")
    _write_verdict(
        gate_repo, "missions/m1/verdicts/master-key.verdict.md",
        _valid_verdict(covers_paths=["**"], artifact_hashes={"src/prod/app.py": blob}),
    )
    head = _commit_all(gate_repo, "prod change + '**' master-key verdict")

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("no covering APPROVE verdict" in reason for reason in payload["reasons"])


def test_validate_rejects_blanket_covers_paths_glob(engine):
    """Direct schema/lint proof, independent of the gate CLI: `tessctl
    validate verdict`'s lint pass flags every '**'-shaped covers_paths entry,
    and does NOT flag a properly-scoped glob."""
    for blanket in ("**", "*", "**/*", "**/**"):
        errors = engine._lint_verdict(_valid_verdict(covers_paths=[blanket], artifact_hashes={}))
        assert any("master key" in e for e in errors), f"{blanket!r} should be rejected"

    ok_errors = engine._lint_verdict(_valid_verdict(covers_paths=["src/prod/**"], artifact_hashes={}))
    assert ok_errors == []


# (iii) allowed_verifiers enforced ---------------------------------------------

def test_allowed_verifiers_is_enforced_wrong_domain_verifier_does_not_clear(gate_repo, run_cli, engine, verifier_gpg_keys):
    """M1 fix: allowed_verifiers is no longer advisory. The test policy's
    'prod-src' rule only allows Reid — a schema-valid, covers_paths-matching,
    content-bound, VALIDLY-SIGNED APPROVE from a DIFFERENT verifier
    (Lysandra — a creative-taste reviewer with no standing on a prod-src
    rule, signed with Lysandra's OWN real key so the failure below is
    genuinely 'wrong verifier', not merely 'unsigned') must not clear it —
    Phase 2b: signing ties allowed_verifiers to the cryptographic signer
    identity, not just an unauthenticated string field."""
    base = _base_sha(gate_repo)
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(gate_repo, "src/prod/app.py")
    _write_verdict(
        gate_repo, "missions/m1/verdicts/wrong-verifier.verdict.md",
        _valid_verdict(
            covers_paths=["src/prod/**"], verifier="Lysandra",
            artifact_hashes={"src/prod/app.py": blob},
            engine=engine, keys=verifier_gpg_keys,
        ),
    )
    head = _commit_all(gate_repo, "prod change + wrong-verifier APPROVE")

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any(
        "src/prod/app.py" in reason and "allowed verifier" in reason
        for reason in payload["reasons"]
    )

    # Sanity: the identical change, reviewed by the rule's ACTUAL allowed
    # verifier (Reid), signed with Reid's own key, clears it.
    _write_verdict(
        gate_repo, "missions/m1/verdicts/wrong-verifier.verdict.md",
        _valid_verdict(
            covers_paths=["src/prod/**"], verifier="Reid",
            artifact_hashes={"src/prod/app.py": blob},
            engine=engine, keys=verifier_gpg_keys,
        ),
    )
    head2 = _commit_all(gate_repo, "swap to the rule's allowed verifier")
    r2 = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head2, "--json")
    assert r2.returncode == 0, r2.stdout + r2.stderr


# (iv) glob semantics fixes -----------------------------------------------------

def test_glob_fix_double_star_matches_root_level_file(engine):
    """M2 fix: '**/x' must ALSO match a root-level 'x' — e.g. a credentials
    rule glob '**/*.env' must gate a top-level '.env', not just a nested
    'config/.env' (previously it required at least one directory component)."""
    assert engine.path_matches_globs(".env", ["**/*.env"]) is True
    assert engine.path_matches_globs("config/.env", ["**/*.env"]) is True


def test_glob_fix_single_star_does_not_span_directories(engine):
    """M2 fix: a bare '*' inside a glob segment must not span '/' — 'src/*'
    covers direct children of src/ only, not arbitrarily-deep prod paths
    underneath it (previously 'src/*' behaved identically to 'src/**')."""
    assert engine.path_matches_globs("src/app.py", ["src/*"]) is True
    assert engine.path_matches_globs("src/prod/deep/app.py", ["src/*"]) is False


def test_glob_fix_gates_a_real_root_level_env_file(gate_repo, run_cli):
    """End-to-end proof against the real policy.yaml shape (a '**/*.env'
    hard-floor glob, same convention core/policy/policy.yaml ships): a
    root-level '.env' is now genuinely gated, not silently missed."""
    policy = {
        "policy": {
            "version": 1,
            "rules": [],
            "hard_floor_rules": [{
                "id": "credentials",
                "category": "credentials",
                "description": "d",
                "globs": ["**/*.env"],
            }],
        }
    }
    (gate_repo / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    _git(gate_repo, "add", "-A")
    _git(gate_repo, "commit", "-q", "-m", "policy: real-shaped credentials glob")
    base = _base_sha(gate_repo)

    (gate_repo / ".env").write_text("SECRET=1\n")
    head = _commit_all(gate_repo, "add root .env")

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("HARD FLOOR" in reason and "credentials" in reason for reason in payload["reasons"])


# (v) uncommitted pre-push verdict does not clear ------------------------------

def test_uncommitted_verdict_on_disk_does_not_clear_the_ship_gate(gate_repo, run_cli):
    """HIGH-1(c): a verdict-shaped file sitting on disk — even `git add`-
    staged — but NOT committed (not part of the pushed ref) must never
    satisfy the ship-gate. Coverage is resolved against the COMMITTED tree
    at the pushed head via `git ls-tree`, never an rglob over the working
    tree."""
    base = _base_sha(gate_repo)
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    head = _commit_all(gate_repo, "prod change, no verdict yet")

    blob = _blob_sha(gate_repo, "src/prod/app.py")
    _write_verdict(
        gate_repo, "missions/m1/verdicts/prod-src.verdict.md",
        _valid_verdict(covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob}),
    )
    _git(gate_repo, "add", "missions/m1/verdicts/prod-src.verdict.md")  # staged, never committed

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("no covering APPROVE verdict" in reason for reason in payload["reasons"])


def test_verdict_committed_on_a_different_branch_does_not_clear_the_pushed_head(gate_repo, run_cli):
    """HIGH-1(c), companion case: a verdict committed on some OTHER branch
    (fully committed, just not reachable from the ref actually being pushed)
    must not clear the ship-gate for the ref that IS being pushed."""
    base = _base_sha(gate_repo)
    original_branch = _git(gate_repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(gate_repo, "src/prod/app.py")
    head = _commit_all(gate_repo, "prod change, no verdict on this branch")

    _git(gate_repo, "checkout", "-q", "-b", "side-branch-with-verdict")
    _write_verdict(
        gate_repo, "missions/m1/verdicts/prod-src.verdict.md",
        _valid_verdict(covers_paths=["src/prod/**"], artifact_hashes={"src/prod/app.py": blob}),
    )
    _commit_all(gate_repo, "verdict lives only on this side branch")
    _git(gate_repo, "checkout", "-q", original_branch)

    r = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("no covering APPROVE verdict" in reason for reason in payload["reasons"])
