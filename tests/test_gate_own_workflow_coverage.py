"""
MEDIUM-1 (Fable Phase-2b follow-up review) — gate the gate's OWN CI
workflow. Before this fix, `.github/workflows/tess-gate.yml` (the required
check's own definition) was not covered by any `require_verdict` glob in
`core/policy/policy.yaml`'s `tess-os-security-tier-doctrine` rule — once
branch protection names "tessctl gate ci" as a required check, a malicious
PR could keep that exact check name intact while neutering its step (e.g.
swap the real run for `exit 0`) in the SAME PR: the universal GitHub
self-gating trap (a required check can never fully protect its own
definition through the required-check-by-name mechanism alone).

Coverage:
  * static: `.github/workflows/**` is now in `tess-os-security-tier-doctrine`'s
    globs in BOTH the real, shipped `core/policy/policy.yaml` and its
    `.tess/core` mirror (byte-identical, same round-trip discipline
    test_contracts_wiring.py already applies to this file)
  * static: `path_matches_globs` matches `.github/workflows/tess-gate.yml`
    against the NEW glob list but would NOT have matched it against the OLD
    (pre-fix) glob list — proves the fix actually closes the gap, not just
    adds an inert glob
  * end-to-end, against a full copy of the REAL shipped repo tree (including
    `.github/`, unlike test_contracts_wiring.py's `real_root` which excludes
    it): editing `.github/workflows/tess-gate.yml` with no covering verdict
    is BLOCKED by `tessctl gate ci` — using the real, unmodified shipped
    policy.yaml, whose `verifier_keys` ships deliberately empty, so this is
    unconditional (no verdict, however honestly authored, could ever clear
    it today)
  * end-to-end, with a synthetic policy scoped to `.github/workflows/**` and
    a real registered verifier key: a validly SIGNED, covering APPROVE
    verdict from an allowed verifier DOES clear the gate — proving the new
    rule is a normal, satisfiable `require_verdict` rule, not an accidental
    permanent block
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT, sign_verdict_for_test

CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"
REAL_POLICY_PATH = REPO_ROOT / "core" / "policy" / "policy.yaml"
WORKFLOW_REL = ".github/workflows/tess-gate.yml"
POST_MERGE_WORKFLOW_REL = ".github/workflows/tess-post-merge-audit.yml"

HAS_GIT = shutil.which("git") is not None
HAS_GPG = shutil.which("gpg") is not None

# Same shape as .github/**-excluding _COPY_IGNORE in test_contracts_wiring.py,
# deliberately WITHOUT ".github" — this suite needs the real workflow file
# present in the copied tree.
_COPY_IGNORE = shutil.ignore_patterns(".git", "tests", ".pytest_cache", "__pycache__")

# The rule's glob list BEFORE this fix (reconstructed here, not re-read from
# git history, so the "did not used to match" assertion is self-contained
# and doesn't depend on git log against this checkout).
_PRE_FIX_GLOBS = [
    "conductor/guardrails.md",
    "conductor/verification-routing.md",
    "conductor/channel-guardrails.md",
    "conductor/dispatch-brief.md",
    "core/contracts/brief.schema.json",
    "core/contracts/verdict.schema.json",
    "core/contracts/policy.schema.json",
    "core/policy/**",
    ".tess/keys/verifiers/**",
]


# ---------------------------------------------------------------------------
# Static: the real shipped policy.yaml now covers .github/workflows/**
# ---------------------------------------------------------------------------

def _load_real_rule(policy_path: Path) -> dict:
    instance = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    rules = instance["policy"]["rules"]
    rule = next(r for r in rules if r["id"] == "tess-os-security-tier-doctrine")
    return rule


def test_real_policy_yaml_globs_include_github_workflows():
    rule = _load_real_rule(REAL_POLICY_PATH)
    assert ".github/workflows/**" in rule["globs"]
    assert rule["require_verdict"] is True
    assert set(rule["allowed_verifiers"]) == {"Reid", "Cyra"}


def test_core_and_mirror_policy_yaml_still_byte_identical_after_fix():
    """Round-trip discipline (same as test_contracts_wiring.py's coverage for
    this file): the .tess/core mirror and the live core/policy/policy.yaml
    copy must stay byte-identical after the MEDIUM-1 edit."""
    mirror_path = REPO_ROOT / ".tess" / "core" / "policy" / "policy.yaml"
    assert mirror_path.read_bytes() == REAL_POLICY_PATH.read_bytes()


def test_policy_yaml_still_schema_valid_after_fix(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "policy")
    instance = engine.load_contract_instance(REAL_POLICY_PATH)
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(instance, schema, schema, base_dir)
    violations += engine._lint_contract("policy", instance)
    assert violations == [], violations


def test_lock_base_sha_matches_committed_core_and_live_bytes_after_regen(engine):
    """The re-pin (`tessctl lock --regen`) this fix required must have
    actually landed — base_sha in tess.lock matches the CURRENT (post-fix)
    .tess/core/policy/policy.yaml bytes, and the live copy is still
    byte-identical to it."""
    lock = engine.load_lock(REPO_ROOT)
    attrs = lock["files"][".tess/core/policy/policy.yaml"]
    assert attrs["tier"] == "security"
    core_path = REPO_ROOT / ".tess/core/policy/policy.yaml"
    live_path = REPO_ROOT / attrs["live_path"]
    assert engine.sha256_file(core_path) == attrs["base_sha"]
    assert core_path.read_bytes() == live_path.read_bytes()


def test_glob_match_proves_the_gap_is_actually_closed(engine):
    """The new glob list matches the gate's own workflow file; the OLD
    (pre-fix) glob list did not — this is the concrete before/after proof
    that MEDIUM-1 closes a real gap, not a no-op."""
    rule = _load_real_rule(REAL_POLICY_PATH)
    for workflow_path in (WORKFLOW_REL, POST_MERGE_WORKFLOW_REL):
        assert engine.path_matches_globs(workflow_path, rule["globs"]) is True
        assert engine.path_matches_globs(workflow_path, _PRE_FIX_GLOBS) is False


# ---------------------------------------------------------------------------
# End-to-end against the REAL, shipped tree (including .github/)
# ---------------------------------------------------------------------------

pytestmark_git = pytest.mark.skipif(not HAS_GIT, reason="git required")


@pytest.fixture
def real_workflow_root(tmp_path):
    """A fresh, isolated copy of the real Tess OS root — WITH `.github/`
    included (unlike test_contracts_wiring.py's `real_root`), turned into a
    real git repo with one initial commit, so `tessctl gate ci` can diff a
    real base/head pair against the actually-shipped tree."""
    dst = tmp_path / "os"
    shutil.copytree(REPO_ROOT, dst, ignore=_COPY_IGNORE)
    assert (dst / WORKFLOW_REL).exists(), "fixture must include the real workflow file"
    assert (dst / POST_MERGE_WORKFLOW_REL).exists(), (
        "fixture must include the real post-merge audit workflow"
    )

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@tess.test",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@tess.test",
    }

    def git(*args, check=True):
        r = subprocess.run(["git", "-C", str(dst), *args], capture_output=True, text=True, env=env)
        if check and r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}\n{r.stdout}")
        return r

    git("init", "-q")
    git("config", "user.email", "test@tess.test")
    git("config", "user.name", "Test")
    git("config", "commit.gpgsign", "false")
    git("add", "-A")
    git("commit", "-q", "-m", "initial (real shipped tree, incl. .github/)")
    return dst, git


@pytestmark_git
def test_editing_gate_workflow_with_no_verdict_is_blocked_on_real_shipped_policy(real_workflow_root, run_cli):
    """The REAL, unmodified shipped policy.yaml ships `verifier_keys: {}`
    (deliberately empty — see the file's own header comment), so this
    assertion is unconditional today: no verdict, however honestly authored,
    can ever satisfy `tess-os-security-tier-doctrine` yet. Editing the
    gate's own CI entrypoint with no verdict at all must therefore BLOCK."""
    root, git = real_workflow_root
    base = git("rev-parse", "HEAD").stdout.strip()

    workflow = root / WORKFLOW_REL
    # Simulate exactly the attack MEDIUM-1 closes: neuter the ship-gate step
    # while keeping everything else (job name, trigger config) intact. v3
    # (honesty-capstone-audit-2026-07-08 §3-c) renamed the final step from
    # bare "tessctl gate ci" to "tessctl gate ci (trusted base-ref engine;
    # untrusted pushed tree)" — target that exact current step name so this
    # still exercises a real content change, not a silent no-op replace.
    text = workflow.read_text(encoding="utf-8")
    final_step_marker = "      - name: tessctl gate ci (trusted base-ref engine; untrusted pushed tree)\n"
    assert final_step_marker in text, "fixture workflow must contain the current v3 final step name"
    text = text.replace(
        final_step_marker,
        "      - name: tessctl gate ci (neutered)\n        run: exit 0\n" + final_step_marker,
        1,
    )
    workflow.write_text(text, encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "neuter the ship-gate step")
    head = git("rev-parse", "HEAD").stdout.strip()

    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert "COVERING_APPROVAL_MISSING: no covering APPROVE verdict found" in payload["reasons"]
    assert WORKFLOW_REL not in json.dumps(payload)


@pytestmark_git
def test_unrelated_change_outside_workflows_is_unaffected(real_workflow_root, run_cli):
    """Sanity / no-regression: a change to an ordinary, non-doctrine file
    (not matched by any rule) is NOT blocked by this fix — MEDIUM-1 only
    adds one glob, it does not tighten the gate globally."""
    root, git = real_workflow_root
    base = git("rev-parse", "HEAD").stdout.strip()

    scratch = root / "docs" / "scratch-note.md"
    scratch.parent.mkdir(parents=True, exist_ok=True)
    scratch.write_text("an ordinary docs note, not doctrine\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "unrelated docs change")
    head = git("rev-parse", "HEAD").stdout.strip()

    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is False


# ---------------------------------------------------------------------------
# End-to-end: the new rule is satisfiable — a validly signed, covering
# APPROVE verdict from an allowed verifier DOES clear a .github/workflows/**
# change (synthetic policy + real generated test verifier keys, same
# pattern as test_gate_spine.py's gate_repo — NOT the real shipped
# empty-verifier_keys policy, which is unconditional by design).
# ---------------------------------------------------------------------------

pytestmark_gpg = pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")

_WORKFLOW_TEST_POLICY = {
    "policy": {
        "version": 1,
        "rules": [
            {
                "id": "gate-own-workflow",
                "description": "test-only rule mirroring the real tess-os-security-tier-doctrine's .github/workflows/** glob",
                "globs": [".github/workflows/**"],
                "classification": ["prod_touching"],
                "require_verdict": True,
                "allowed_verifiers": ["Reid"],
            },
        ],
        "hard_floor_rules": [],
    },
}


def _bundle_key(root, name, key):
    keys_dir = root / ".tess" / "keys" / "verifiers"
    keys_dir.mkdir(parents=True, exist_ok=True)
    (keys_dir / f"{name.lower()}.asc").write_text(key.pubkey_armored, encoding="utf-8")
    return f".tess/keys/verifiers/{name.lower()}.asc"


def _base_verdict(covers_paths, artifact_hashes, verifier="Reid"):
    return {
        "verifier": verifier,
        "output_domain": "Code diff / PR",
        "primary_artifacts_read": list(covers_paths),
        "findings": [],
        "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "summary_line": "Reviewed. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Top priority: none.",
        "disposition": "APPROVE",
        "covers_paths": list(covers_paths),
        "artifact_hashes": dict(artifact_hashes),
    }


def _write_verdict(root, rel_path, verdict_dict):
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\n" + yaml.safe_dump(verdict_dict) + "---\n\n# Verdict body\n", encoding="utf-8")
    return p


@pytestmark_gpg
def test_workflow_rule_is_satisfiable_with_a_valid_covering_signed_verdict(project, verifier_gpg_keys, run_cli, engine):
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)
    key = verifier_gpg_keys["Reid"]
    rel = _bundle_key(root, "Reid", key)
    policy = dict(_WORKFLOW_TEST_POLICY)
    policy["policy"] = {**policy["policy"], "verifier_keys": {"Reid": {"fingerprint": key.fpr, "public_key_file": rel}}}
    (root / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@tess.test",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@tess.test",
    }

    def git(*args, check=True):
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=env)
        if check and r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}\n{r.stdout}")
        return r

    git("init", "-q")
    git("config", "user.email", "test@tess.test")
    git("config", "user.name", "Test")
    git("config", "commit.gpgsign", "false")
    git("add", "-A")
    git("commit", "-q", "-m", "initial")
    base = git("rev-parse", "HEAD").stdout.strip()

    workflow = root / ".github" / "workflows" / "tess-gate.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text("name: Tess OS ship-gate\non: [push]\njobs: {}\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "add workflow (uncovered)")
    head_uncovered = git("rev-parse", "HEAD").stdout.strip()

    r_blocked = run_cli(root, "gate", "ci", "--base", base, "--head", head_uncovered, "--json")
    assert r_blocked.returncode == 1, r_blocked.stdout + r_blocked.stderr
    assert json.loads(r_blocked.stdout)["blocked"] is True

    blob = git("hash-object", ".github/workflows/tess-gate.yml").stdout.strip()
    verdict = _base_verdict([".github/workflows/**"], {".github/workflows/tess-gate.yml": blob})
    verdict["signature"] = sign_verdict_for_test(engine, verdict, key)
    _write_verdict(root, "missions/m1/verdicts/gate-workflow.verdict.md", verdict)
    git("add", "-A")
    git("commit", "-q", "-m", "add covering signed verdict")
    head_covered = git("rev-parse", "HEAD").stdout.strip()

    # Diff the CUMULATIVE range (original base -> head_covered), not just the
    # last commit — this is the range that actually contains the .github/
    # workflows/tess-gate.yml change together with its covering verdict, the
    # same shape a real PR's base...head diff would show.
    r_ok = run_cli(root, "gate", "ci", "--base", base, "--head", head_covered, "--json")
    assert r_ok.returncode == 0, r_ok.stdout + r_ok.stderr
    payload = json.loads(r_ok.stdout)
    assert payload["blocked"] is False
    assert payload["reasons"] == []
