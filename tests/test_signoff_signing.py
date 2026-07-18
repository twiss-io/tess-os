"""
honesty-capstone-audit-2026-07-08 §3-d — hard-floor sign-off signing.

Before this fix, `.tess/gate/signoffs/<rule-id>.signoff.json` was validated
by JSON SHAPE ALONE (five non-empty fields: rule_id, category,
authorized_by, rationale, authorized_at) — no signature, no authentication
of `authorized_by` at all, and the directory itself was not policy-covered.
Any agent able to write a file could forge a hard-floor clearance for
credentials/money-movement/destructive-prod-data changes, mechanically
contradicting docs (AGENTS.md — see the audit's R11) claiming "the gate
treats [a .tess/gate/signoffs/ edit] as tamper and fails closed": writing a
sign-off CLEARED the floor, it did not trip anything.

This file covers what tests/test_gate_spine.py's end-to-end
gate_repo/run_cli "HARD FLOOR" tests do not already cover directly:
  * unit-level `_gate_verify_signoff_signature` structural/format checks
    (no real GPG subprocess needed — pure Python logic), mirroring
    tests/test_verdict_signing.py's equivalent coverage for verdicts
  * `public_key_file` C1 containment (absolute path / '..' traversal /
    symlink escape) — the SAME LOW-1 discipline verdict-signature
    verification already applies, mirrored here for signoff_keys
  * `tessctl gate signoff sign` / `tessctl gate signoff verify` CLI
    round-trip
  * policy-coverage of `.tess/gate/signoffs/**` itself under
    tess-os-security-tier-doctrine (static + end-to-end, same pattern
    tests/test_gate_own_workflow_coverage.py already applies to
    `.github/workflows/**`)

The full attack-scenario proofs (unsigned/forged does NOT clear; a properly
signed one DOES; hand-faked/wrong-key/tampered/unregistered-authorizer all
blocked) live in tests/test_gate_spine.py's "Hard floor" section, run
through the real `tessctl gate ci` CLI end-to-end against `gate_repo`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import sign_signoff_for_test

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"
REAL_POLICY_PATH = REPO_ROOT / "core" / "policy" / "policy.yaml"
SIGNOFFS_GLOB_REL = ".tess/gate/signoffs/dummy.signoff.json"

HAS_GIT = shutil.which("git") is not None
HAS_GPG = shutil.which("gpg") is not None
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


def _init_repo(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@tess.test")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")


def _base_sha(root):
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _commit_all(root, message):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _base_signoff(rule_id="money", category="money_movement", authorized_by="Xavier"):
    return {
        "rule_id": rule_id,
        "category": category,
        "authorized_by": authorized_by,
        "rationale": "Reviewed out-of-band; approved.",
        "authorized_at": "2026-07-08T00:00:00Z",
    }


def _policy_dict(hard_floor_globs, signoff_keys):
    return {
        "policy": {
            "version": 1,
            "rules": [],
            "hard_floor_rules": [{
                "id": "money",
                "category": "money_movement",
                "description": "test-only hard floor",
                "globs": list(hard_floor_globs),
            }],
            "signoff_keys": signoff_keys,
        }
    }


def _bundle_signoff_key(root, name, key):
    keys_dir = root / ".tess" / "keys" / "signoffs"
    keys_dir.mkdir(parents=True, exist_ok=True)
    (keys_dir / f"{name.lower()}.asc").write_text(key.pubkey_armored, encoding="utf-8")
    return f".tess/keys/signoffs/{name.lower()}.asc"


# ---------------------------------------------------------------------------
# Policy coverage: `.tess/gate/signoffs/**` is now itself governed
# ---------------------------------------------------------------------------

def _load_real_rule(policy_path: Path) -> dict:
    instance = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    rules = instance["policy"]["rules"]
    return next(r for r in rules if r["id"] == "tess-os-security-tier-doctrine")


def test_real_policy_yaml_covers_signoffs_dir_and_engine():
    rule = _load_real_rule(REAL_POLICY_PATH)
    assert ".tess/gate/signoffs/**" in rule["globs"]
    assert ".tess/bin/**" in rule["globs"]
    assert "tessctl" in rule["globs"]


def test_glob_match_proves_signoffs_coverage_is_real(engine):
    rule = _load_real_rule(REAL_POLICY_PATH)
    assert engine.path_matches_globs(SIGNOFFS_GLOB_REL, rule["globs"]) is True
    pre_fix_globs = [g for g in rule["globs"] if g not in (".tess/bin/**", "tessctl", ".tess/gate/signoffs/**")]
    assert engine.path_matches_globs(SIGNOFFS_GLOB_REL, pre_fix_globs) is False


def test_glob_match_proves_engine_coverage_is_real(engine):
    rule = _load_real_rule(REAL_POLICY_PATH)
    assert engine.path_matches_globs(".tess/bin/tessctl", rule["globs"]) is True
    assert engine.path_matches_globs("tessctl", rule["globs"]) is True
    pre_fix_globs = [g for g in rule["globs"] if g not in (".tess/bin/**", "tessctl", ".tess/gate/signoffs/**")]
    assert engine.path_matches_globs(".tess/bin/tessctl", pre_fix_globs) is False
    assert engine.path_matches_globs("tessctl", pre_fix_globs) is False


def test_core_and_mirror_policy_yaml_still_byte_identical():
    mirror_path = REPO_ROOT / ".tess" / "core" / "policy" / "policy.yaml"
    assert mirror_path.read_bytes() == REAL_POLICY_PATH.read_bytes()


def test_policy_yaml_still_schema_valid(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "policy")
    instance = engine.load_contract_instance(REAL_POLICY_PATH)
    base_dir = REPO_ROOT / "core" / "contracts"
    violations = engine.schema_validate(instance, schema, schema, base_dir)
    violations += engine._lint_contract("policy", instance)
    assert violations == [], violations


@pytest.fixture
def signoffs_dir_repo(tmp_path):
    """A fresh, isolated copy of the real Tess OS root, turned into a real
    git repo — so `tessctl gate ci` can diff a real base/head pair against
    the actually-shipped policy.yaml (unconditional today: signoff_keys and
    verifier_keys both ship empty by design)."""
    dst = tmp_path / "os"
    ignore = shutil.ignore_patterns(".git", "tests", ".pytest_cache", "__pycache__")
    shutil.copytree(REPO_ROOT, dst, ignore=ignore)
    _init_repo(dst)
    _git(dst, "add", "-A")
    _git(dst, "commit", "-q", "-m", "initial (real shipped tree)")
    return dst


def test_adding_a_signoff_file_with_no_verdict_is_blocked_on_real_shipped_policy(signoffs_dir_repo, run_cli):
    """The real, unmodified shipped policy.yaml ships signoff_keys: {} and
    verifier_keys: {} — introducing ANY file under .tess/gate/signoffs/**
    with no covering verdict is unconditionally blocked today."""
    root = signoffs_dir_repo
    base = _base_sha(root)
    signoffs_dir = root / ".tess" / "gate" / "signoffs"
    signoffs_dir.mkdir(parents=True, exist_ok=True)
    (signoffs_dir / "money.signoff.json").write_text(
        json.dumps(_base_signoff()), encoding="utf-8",
    )
    head = _commit_all(root, "add a sign-off with no covering verdict")

    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert payload["reasons"] == [
        "COVERING_APPROVAL_MISSING: no covering APPROVE verdict found"
    ]


def test_editing_the_engine_with_no_verdict_is_blocked_on_real_shipped_policy(signoffs_dir_repo, run_cli):
    """§3-c's policy-coverage half: an edit to `.tess/bin/tessctl` itself,
    with no covering verdict, is now `prod_touching` and blocked."""
    root = signoffs_dir_repo
    base = _base_sha(root)
    engine_path = root / ".tess" / "bin" / "tessctl"
    text = engine_path.read_text(encoding="utf-8")
    engine_path.write_text(text + "\n# innocuous same-push comment\n", encoding="utf-8")
    head = _commit_all(root, "chore: tiny comment tweak to the engine")

    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert payload["reasons"] == [
        "ADMISSION_EVENT_SOURCE_REQUIRED: an authoritative admission event source is required",
        "COVERING_APPROVAL_MISSING: no covering APPROVE verdict found"
    ]


# ---------------------------------------------------------------------------
# CLI round-trip: `tessctl gate signoff sign` / `tessctl gate signoff verify`
# ---------------------------------------------------------------------------

def test_cli_sign_then_verify_round_trip(project, run_cli, verifier_gpg_keys):
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)
    key = verifier_gpg_keys["Reid"]
    rel = _bundle_signoff_key(root, "Xavier", key)
    policy = _policy_dict(["payments/**"], {"Xavier": {"fingerprint": key.fpr, "public_key_file": rel}})
    (root / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")

    signoff_path = root / ".tess" / "gate" / "signoffs" / "money.signoff.json"
    signoff_path.parent.mkdir(parents=True)
    signoff_path.write_text(json.dumps(_base_signoff()), encoding="utf-8")

    r_sign = run_cli(
        root, "gate", "signoff", "sign", str(signoff_path),
        "--key-id", key.fpr, "--gnupg-home", str(key.home),
    )
    assert r_sign.returncode == 0, r_sign.stdout + r_sign.stderr
    assert "signed" in r_sign.stdout.lower()

    r_verify = run_cli(root, "gate", "signoff", "verify", str(signoff_path), "--rule-id", "money", "--json")
    assert r_verify.returncode == 0, r_verify.stdout + r_verify.stderr
    payload = json.loads(r_verify.stdout)
    assert payload["valid"] is True


def test_immutable_base_signoff_import_uses_stdin_without_certificate_tempfile(
    engine, verifier_gpg_keys, tmp_path, monkeypatch,
):
    key = verifier_gpg_keys["Reid"]
    signoff = _base_signoff()
    signoff["signature"] = sign_signoff_for_test(engine, signoff, key)
    policy = _policy_dict(["payments/**"], {
        "Xavier": {"fingerprint": key.fpr, "public_key_file": ".tess/keys/signoffs/xavier.asc"},
    })
    original_write_bytes = Path.write_bytes

    def deny_trusted_certificate_tempfile(path, data):
        if path.name == "trusted-signoff-key.asc":
            raise AssertionError("immutable BASE sign-off certificate must never be written to disk")
        return original_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", deny_trusted_certificate_tempfile)
    ok, reason = engine._gate_verify_signoff_signature(
        tmp_path, policy, signoff,
        trusted_signoff_key_blobs={"Xavier": key.pubkey_armored.encode("utf-8")},
    )
    assert ok is True, reason


def test_cli_verify_fails_on_unsigned_signoff(project, run_cli, verifier_gpg_keys):
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)
    key = verifier_gpg_keys["Reid"]
    rel = _bundle_signoff_key(root, "Xavier", key)
    policy = _policy_dict(["payments/**"], {"Xavier": {"fingerprint": key.fpr, "public_key_file": rel}})
    (root / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")

    signoff_path = root / ".tess" / "gate" / "signoffs" / "money.signoff.json"
    signoff_path.parent.mkdir(parents=True)
    signoff_path.write_text(json.dumps(_base_signoff()), encoding="utf-8")

    r_verify = run_cli(root, "gate", "signoff", "verify", str(signoff_path), "--rule-id", "money", "--json")
    assert r_verify.returncode == 1
    payload = json.loads(r_verify.stdout)
    assert payload["valid"] is False
    assert payload["reason"] == "HARD_FLOOR_UNSATISFIED: a required hard-floor sign-off is not valid"


def test_cli_sign_rejects_missing_authorized_by(project, run_cli, verifier_gpg_keys):
    root = project.root
    key = verifier_gpg_keys["Reid"]
    signoff_path = root / "money.signoff.json"
    signoff_path.write_text(json.dumps({
        "rule_id": "money", "category": "money_movement",
        "rationale": "x", "authorized_at": "2026-07-08T00:00:00Z",
    }), encoding="utf-8")

    r = run_cli(
        root, "gate", "signoff", "sign", str(signoff_path),
        "--key-id", key.fpr, "--gnupg-home", str(key.home),
    )
    assert r.returncode != 0
    assert "authorized_by" in (r.stdout + r.stderr)


def test_cli_sign_produces_valid_signature_block(project, run_cli, verifier_gpg_keys):
    root = project.root
    key = verifier_gpg_keys["Reid"]
    signoff_path = root / "money.signoff.json"
    signoff_path.write_text(json.dumps(_base_signoff()), encoding="utf-8")

    r = run_cli(
        root, "gate", "signoff", "sign", str(signoff_path),
        "--key-id", key.fpr, "--gnupg-home", str(key.home),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(signoff_path.read_text(encoding="utf-8"))
    sig = data["signature"]
    assert sig["algorithm"] == "gpg-detached-armor"
    assert len(sig["signed_content_sha256"]) == 64
    assert "BEGIN PGP SIGNATURE" in sig["signature_armored"]


# ---------------------------------------------------------------------------
# Unit-level: _gate_verify_signoff_signature structural/format checks
# (no real GPG subprocess needed for these — pure Python logic)
# ---------------------------------------------------------------------------

def test_verify_rejects_missing_signature(engine):
    ok, reason = engine._gate_verify_signoff_signature(
        Path("."), {"policy": {"signoff_keys": {}}}, {"authorized_by": "Xavier"},
    )
    assert ok is False
    assert "no signature block present" in reason


def test_verify_rejects_unknown_algorithm(engine):
    data = {"authorized_by": "Xavier", "signature": {"algorithm": "rot13", "signed_content_sha256": "a" * 64, "signature_armored": "x"}}
    ok, reason = engine._gate_verify_signoff_signature(Path("."), {"policy": {"signoff_keys": {}}}, data)
    assert ok is False
    assert "not supported" in reason


def test_verify_rejects_malformed_hash(engine):
    data = {"authorized_by": "Xavier", "signature": {"algorithm": "gpg-detached-armor", "signed_content_sha256": "not-a-hash", "signature_armored": "x"}}
    ok, reason = engine._gate_verify_signoff_signature(Path("."), {"policy": {"signoff_keys": {}}}, data)
    assert ok is False
    assert "64-hex-char sha256" in reason


def test_verify_rejects_stale_content_hash(engine):
    data = {"rule_id": "money", "authorized_by": "Xavier"}
    data["signature"] = {"algorithm": "gpg-detached-armor", "signed_content_sha256": "a" * 64, "signature_armored": "x"}
    ok, reason = engine._gate_verify_signoff_signature(Path("."), {"policy": {"signoff_keys": {}}}, data)
    assert ok is False
    assert "tampered" in reason


def test_verify_rejects_malformed_registered_fingerprint(engine):
    data = _base_signoff()
    canonical = engine.signoff_canonical_bytes(data)
    data["signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": hashlib.sha256(canonical).hexdigest(),
        "signature_armored": "x",
    }
    policy_instance = {"policy": {"signoff_keys": {"Xavier": {"fingerprint": "not-a-fingerprint", "public_key_file": "x.asc"}}}}
    ok, reason = engine._gate_verify_signoff_signature(Path("."), policy_instance, data)
    assert ok is False
    assert "40-hex-char" in reason


def test_verify_rejects_missing_key_file(engine, tmp_path):
    data = _base_signoff()
    canonical = engine.signoff_canonical_bytes(data)
    data["signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": hashlib.sha256(canonical).hexdigest(),
        "signature_armored": "x",
    }
    policy_instance = {
        "policy": {"signoff_keys": {"Xavier": {"fingerprint": "A" * 40, "public_key_file": ".tess/keys/signoffs/nope.asc"}}},
    }
    ok, reason = engine._gate_verify_signoff_signature(tmp_path, policy_instance, data)
    assert ok is False
    assert "not found on disk" in reason


def test_verify_rejects_unregistered_authorizer(engine):
    data = _base_signoff()
    canonical = engine.signoff_canonical_bytes(data)
    data["signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": hashlib.sha256(canonical).hexdigest(),
        "signature_armored": "x",
    }
    ok, reason = engine._gate_verify_signoff_signature(Path("."), {"policy": {"signoff_keys": {}}}, data)
    assert ok is False
    assert "no registered public key" in reason


# ---------------------------------------------------------------------------
# C1 containment (mirrors LOW-1's verdict-signing coverage exactly, applied
# to signoff_keys' public_key_file)
# ---------------------------------------------------------------------------

def test_verify_rejects_absolute_public_key_file(engine, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    decoy = tmp_path / "outside-root" / "decoy.asc"
    decoy.parent.mkdir(parents=True)
    decoy.write_text("decoy key material\n", encoding="utf-8")

    data = _base_signoff()
    canonical = engine.signoff_canonical_bytes(data)
    data["signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": hashlib.sha256(canonical).hexdigest(),
        "signature_armored": "x",
    }
    policy_instance = {"policy": {"signoff_keys": {"Xavier": {"fingerprint": "A" * 40, "public_key_file": str(decoy)}}}}
    ok, reason = engine._gate_verify_signoff_signature(root, policy_instance, data)
    assert ok is False
    assert "absolute path" in reason
    assert "C1 containment" in reason
    assert "not found on disk" not in reason


def test_verify_rejects_traversal_public_key_file(engine, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    decoy = tmp_path / "decoy.asc"
    decoy.write_text("decoy key material\n", encoding="utf-8")

    data = _base_signoff()
    canonical = engine.signoff_canonical_bytes(data)
    data["signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": hashlib.sha256(canonical).hexdigest(),
        "signature_armored": "x",
    }
    policy_instance = {"policy": {"signoff_keys": {"Xavier": {"fingerprint": "A" * 40, "public_key_file": "../decoy.asc"}}}}
    ok, reason = engine._gate_verify_signoff_signature(root, policy_instance, data)
    assert ok is False
    assert "traversal" in reason
    assert "C1 containment" in reason
    assert "not found on disk" not in reason


def test_verify_rejects_symlink_escape_public_key_file(engine, tmp_path):
    """Standalone sign-off diagnostics reject a checkout symlink explicitly.

    Ship-gate verification instead requires a regular public-key blob from
    the immutable BASE tree and never follows this candidate path.
    """
    if os.name == "nt":
        pytest.skip("symlinks require elevated privileges on Windows")
    root = tmp_path / "repo"
    (root / ".tess" / "keys" / "signoffs").mkdir(parents=True)
    decoy = tmp_path / "outside-root-decoy.asc"
    decoy.write_text("decoy key material\n", encoding="utf-8")
    link = root / ".tess" / "keys" / "signoffs" / "xavier.asc"
    link.symlink_to(decoy)

    data = _base_signoff()
    canonical = engine.signoff_canonical_bytes(data)
    data["signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": hashlib.sha256(canonical).hexdigest(),
        "signature_armored": "x",
    }
    policy_instance = {
        "policy": {"signoff_keys": {"Xavier": {"fingerprint": "A" * 40, "public_key_file": ".tess/keys/signoffs/xavier.asc"}}},
    }
    ok, reason = engine._gate_verify_signoff_signature(root, policy_instance, data)
    assert ok is False
    assert "is a symlink" in reason
    assert "C1 containment" in reason
