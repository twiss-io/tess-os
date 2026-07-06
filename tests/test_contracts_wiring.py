"""
Phase 1 item 1 — wire the deferred Phase 0 contracts into the managed set.

Phase 0 shipped `core/contracts/*.schema.json` + `tessctl validate` but left
the subtree explicitly UNTRACKED (see the pre-Phase-1 `core/contracts/README.md`:
"core/contracts/** is not added to tess.manifest.json's owned_globs or to
.tess/tess.lock in this phase"). This suite proves the wiring: the contracts
are now a genuine part of the rendered/tracked framework, not orphaned.

Coverage:
  * "core/contracts/**" is in the REAL tess.manifest.json owned_globs.
  * The REAL .tess/tess.lock has a core-managed entry for each of the 6
    contract files (Phase 0/1's original 5 + Phase 2's policy.schema.json),
    with the correct live_path, and base_sha that matches both the committed
    .tess/core/contracts/<f> bytes AND the live core/contracts/<f> bytes
    (round-trip — proves the mirror and the live tree are byte-identical,
    i.e. genuinely wired, not just declared).
  * brief.schema.json + verdict.schema.json + policy.schema.json carry
    tier: security (the documented Phase 1/2 choice — they encode
    conductor/dispatch-brief.md, conductor/verification-routing.md, and
    conductor/guardrails.md Rule 18, all already tier: security).
  * End-to-end against a full copy of the shipped repo tree: `tessctl
    doctor`, `tessctl verify`, and `tessctl lock --check` all exit 0.
  * `tessctl lock --regen --yes` against the shipped tree is a no-op for the
    5 new entries (proves they are ALREADY correctly pinned, not merely
    present).
  * Tamper detection now actually fires: editing
    .tess/core/contracts/brief.schema.json is caught as a [SECURITY] CORE
    TAMPER by doctor/verify; editing the live core/contracts/crew-plan.schema.json
    copy directly is caught as normal-tier UNCAPTURED DRIFT. Neither was
    possible before this wiring (the files were invisible to doctor/verify).
  * `tessctl validate` (Phase 0's CLI) still reads schemas from the LIVE
    core/contracts/ path exactly as before — the new .tess/core mirror is an
    integrity/tracking addition, not a relocation of where the validator
    reads from.
"""

from __future__ import annotations

import json
import shutil

import pytest

from conftest import REPO_ROOT, MANIFEST_SRC

_CONTRACT_FILES = {
    "README.md": "normal",
    "brief.schema.json": "security",
    "crew-plan.schema.json": "normal",
    "verdict.schema.json": "security",
    "return-manifest.schema.json": "normal",
    "policy.schema.json": "security",  # Phase 2 — encodes verification-routing.md + guardrails.md Rule 18
}

_COPY_IGNORE = shutil.ignore_patterns(
    ".git", "tests", ".pytest_cache", "__pycache__", ".github"
)


@pytest.fixture
def real_root(tmp_path):
    """A fresh, isolated copy of the real Tess OS root (same pattern as
    test_m4_m6_remediation.py's real_root) — proves the wiring on the
    actually-shipped tree, not a synthetic stand-in."""
    dst = tmp_path / "os"
    shutil.copytree(REPO_ROOT, dst, ignore=_COPY_IGNORE)
    return dst


# ---------------------------------------------------------------------------
# Manifest + lock static wiring
# ---------------------------------------------------------------------------

def test_manifest_owns_contracts_glob():
    manifest = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))
    assert "core/contracts/**" in manifest["owned_globs"]


def test_lock_has_entry_per_contract_file(engine):
    lock = engine.load_lock(REPO_ROOT)
    files = lock["files"]
    for fname, expected_tier in _CONTRACT_FILES.items():
        core_key = f".tess/core/contracts/{fname}"
        assert core_key in files, f"{core_key} missing from tess.lock"
        attrs = files[core_key]
        assert attrs["status"] == "core-managed"
        assert attrs["live_path"] == f"core/contracts/{fname}"
        assert attrs["tier"] == expected_tier, (
            f"{fname}: expected tier {expected_tier!r}, got {attrs['tier']!r}"
        )


def test_lock_base_sha_matches_committed_core_and_live_bytes(engine):
    """Round-trip: base_sha pins the .tess/core mirror, AND the live copy is
    byte-identical to it (render_core_to_live is an identity copy for these
    plain JSON/markdown files — no {{TESS_ROOT}} tokens, no .local.md shadow)."""
    lock = engine.load_lock(REPO_ROOT)
    files = lock["files"]
    for fname in _CONTRACT_FILES:
        core_key = f".tess/core/contracts/{fname}"
        attrs = files[core_key]
        core_path = REPO_ROOT / core_key
        live_path = REPO_ROOT / attrs["live_path"]
        assert core_path.exists(), core_key
        assert live_path.exists(), attrs["live_path"]
        assert engine.sha256_file(core_path) == attrs["base_sha"], (
            f"{core_key}: base_sha does not match committed core bytes"
        )
        assert core_path.read_bytes() == live_path.read_bytes(), (
            f"{fname}: .tess/core mirror and live core/contracts/ copy are not byte-identical"
        )


def test_security_tier_matches_doctrine_precedent(engine):
    """brief.schema.json / verdict.schema.json are the machine-checkable form
    of conductor/dispatch-brief.md / conductor/verification-routing.md — both
    already tier: security. Weakening the schema should be treated with the
    same severity as editing the prose doctrine."""
    lock = engine.load_lock(REPO_ROOT)
    files = lock["files"]
    assert files[".tess/core/contracts/brief.schema.json"]["tier"] == "security"
    assert files[".tess/core/contracts/verdict.schema.json"]["tier"] == "security"
    assert files[".tess/core/contracts/policy.schema.json"]["tier"] == "security"
    # Sanity: the doctrine files this mirrors are themselves security-tier.
    assert files[".tess/core/conductor/dispatch-brief.md"]["tier"] == "security"
    assert files[".tess/core/conductor/verification-routing.md"]["tier"] == "security"
    assert files[".tess/core/conductor/guardrails.md"]["tier"] == "security"


# ---------------------------------------------------------------------------
# End-to-end against the real, shipped tree
# ---------------------------------------------------------------------------

def test_doctor_verify_lock_check_clean_on_real_tree(real_root, run_cli):
    d = run_cli(real_root, "doctor")
    assert d.returncode == 0, f"doctor not clean:\n{d.stdout}\n{d.stderr}"
    assert "core/contracts/brief.schema.json" in d.stdout
    assert "core/contracts/verdict.schema.json" in d.stdout
    assert "core/contracts/policy.schema.json" in d.stdout
    assert "core/policy/policy.yaml" in d.stdout

    v = run_cli(real_root, "verify")
    assert v.returncode == 0, f"verify not clean:\n{v.stdout}\n{v.stderr}"
    assert "verify: OK" in v.stdout

    lc = run_cli(real_root, "lock", "--check")
    assert lc.returncode == 0, f"lock --check not clean:\n{lc.stdout}\n{lc.stderr}"


def test_regen_is_noop_for_already_pinned_contracts(real_root, run_cli):
    """--regen re-pins base_sha to CURRENT core bytes; on the shipped tree the
    5 contract entries are already correctly pinned, so --regen must not
    change their base_sha (proves the wiring pinned the RIGHT bytes, not
    just SOME bytes)."""
    lock_path = real_root / ".tess" / "tess.lock"
    before = lock_path.read_text(encoding="utf-8")

    r = run_cli(real_root, "lock", "--regen", "--yes")
    assert r.returncode == 0, r.stderr

    after = lock_path.read_text(encoding="utf-8")
    # last_updated (framework-level) is allowed to change; per-file base_sha
    # for the contracts entries must not.
    import yaml
    before_files = yaml.safe_load(before)["files"]
    after_files = yaml.safe_load(after)["files"]
    for fname in _CONTRACT_FILES:
        core_key = f".tess/core/contracts/{fname}"
        assert before_files[core_key]["base_sha"] == after_files[core_key]["base_sha"], (
            f"{core_key}: base_sha changed on --regen — it was not correctly pinned before"
        )


def test_tamper_on_security_tier_contract_schema_is_caught(real_root, run_cli):
    core_file = real_root / ".tess" / "core" / "contracts" / "brief.schema.json"
    core_file.write_bytes(core_file.read_bytes() + b"\n// tampered\n")

    d = run_cli(real_root, "doctor")
    assert d.returncode == 1
    assert "CORE-TAMPER" in d.stdout
    assert "core/contracts/brief.schema.json" in d.stdout
    assert "[SECURITY]" in d.stdout

    v = run_cli(real_root, "verify")
    assert v.returncode == 1
    assert "CORE TAMPER" in v.stdout


def test_live_drift_on_normal_tier_contract_schema_is_caught(real_root, run_cli):
    live_file = real_root / "core" / "contracts" / "crew-plan.schema.json"
    live_file.write_text(live_file.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    d = run_cli(real_root, "doctor")
    assert d.returncode == 1
    assert "DRIFT       core/contracts/crew-plan.schema.json" in d.stdout
    assert "tessctl capture core/contracts/crew-plan.schema.json" in d.stdout
    # normal tier — no [SECURITY] badge on this line (unlike the brief/verdict schemas)
    assert "core/contracts/crew-plan.schema.json [SECURITY]" not in d.stdout

    v = run_cli(real_root, "verify")
    assert v.returncode == 1
    assert "LIVE DRIFT" in v.stdout
    assert "core/contracts/crew-plan.schema.json" in v.stdout


# ---------------------------------------------------------------------------
# Phase 2 — core/policy/** wiring (the policy INSTANCE, sibling to the
# core/contracts/policy.schema.json tested above). Same pristine-mirror
# pattern, tier: security (it is "the machine-readable half of guardrails" —
# ULTIMATE_FRAMEWORK_PLAN.md §C5 — same weight as the doctrine prose it
# encodes).
# ---------------------------------------------------------------------------

def test_manifest_owns_policy_glob():
    manifest = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))
    assert "core/policy/**" in manifest["owned_globs"]


def test_lock_has_entry_for_policy_yaml(engine):
    lock = engine.load_lock(REPO_ROOT)
    files = lock["files"]
    core_key = ".tess/core/policy/policy.yaml"
    assert core_key in files, f"{core_key} missing from tess.lock"
    attrs = files[core_key]
    assert attrs["status"] == "core-managed"
    assert attrs["live_path"] == "core/policy/policy.yaml"
    assert attrs["tier"] == "security"


def test_policy_yaml_base_sha_matches_committed_core_and_live_bytes(engine):
    lock = engine.load_lock(REPO_ROOT)
    attrs = lock["files"][".tess/core/policy/policy.yaml"]
    core_path = REPO_ROOT / ".tess/core/policy/policy.yaml"
    live_path = REPO_ROOT / attrs["live_path"]
    assert core_path.exists() and live_path.exists()
    assert engine.sha256_file(core_path) == attrs["base_sha"]
    assert core_path.read_bytes() == live_path.read_bytes()


def test_policy_yaml_is_valid_against_its_own_schema(engine):
    """core/policy/policy.yaml (the shipped default instance) must itself
    validate against core/contracts/policy.schema.json + its lint checks —
    the framework does not ship a policy file that would fail its own gate."""
    schema = engine.load_contract_schema(REPO_ROOT, "policy")
    instance = engine.load_contract_instance(REPO_ROOT / "core" / "policy" / "policy.yaml")
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(instance, schema, schema, base_dir)
    violations += engine._lint_contract("policy", instance)
    assert violations == [], violations


def test_tamper_on_policy_yaml_is_caught(real_root, run_cli):
    core_file = real_root / ".tess" / "core" / "policy" / "policy.yaml"
    core_file.write_text(core_file.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")

    d = run_cli(real_root, "doctor")
    assert d.returncode == 1
    assert "CORE-TAMPER" in d.stdout
    assert "core/policy/policy.yaml" in d.stdout
    assert "[SECURITY]" in d.stdout

    v = run_cli(real_root, "verify")
    assert v.returncode == 1
    assert "CORE TAMPER" in v.stdout


# ---------------------------------------------------------------------------
# No regression to Phase 0's `tessctl validate` (still reads the LIVE path)
# ---------------------------------------------------------------------------

def test_validate_still_reads_live_contracts_path_unaffected_by_wiring(real_root, run_cli):
    """The .tess/core mirror is an integrity/tracking addition, not a
    relocation of where cmd_validate loads schemas from — `tessctl validate`
    must still resolve `core/contracts/<type>.schema.json` at the live path."""
    instance = {
        "objective": "Confirm contracts wiring does not break Phase 0 validate.",
        "output_contract": "/tmp/x.md — sections [A]",
        "tools_sources_constraints": "Read /tmp/x.csv; every number traces to a quoted row.",
        "not_responsible_for": "Nothing else.",
        "milestones": [],
        "escalation_trigger": "If blocked, stop and ask.",
        "estimated_minutes": 5,
        "prod_touching": False,
    }
    instance_path = real_root / "brief-instance.json"
    instance_path.write_text(json.dumps(instance), encoding="utf-8")

    r = run_cli(real_root, "validate", "brief", str(instance_path))
    assert r.returncode == 0, f"validate failed unexpectedly:\n{r.stdout}\n{r.stderr}"
