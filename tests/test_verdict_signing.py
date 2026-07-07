"""
Phase 2b — verdict signing (closes the Fable Phase-2 residual: "verdict +
sign-off files are committer-authored with NO signing... a weak/malicious
agent could hand-write a fake disposition: APPROVE verdict to clear its own
gate"). Reuses the repo's existing keystone signed-update primitives
(isolated GNUPGHOME, exact 40-hex fingerprint pinning) — no new signing
scheme invented.

Coverage (per the dispatch brief's explicit test list):
  * a validly-SIGNED verdict from an allowed verifier clears the gate
  * an UNSIGNED verdict is BLOCKED (fail-closed) even though otherwise
    perfectly valid (right glob, right verifier, right artifact_hashes)
  * a HAND-FAKED signature block (garbage armored text) is BLOCKED
  * a WRONG-KEY signature (signed by a real key that is not the one
    registered for the claimed verifier) is BLOCKED
  * a TAMPERED verdict (content edited after signing) is BLOCKED
  * signing ties to allowed_verifiers: a verdict validly signed by a
    verifier who IS registered, but who is NOT in the matched rule's
    allowed_verifiers, still does not clear (covered directly here AND in
    test_gate_spine.py's test_allowed_verifiers_is_enforced_wrong_domain_...)
  * `tessctl verdict sign` + `tessctl verdict verify` CLI round-trip
  * `_lint_policy` rejects a `verifier_keys` entry under an unrecognized name

Unit-level coverage of `_gate_verify_verdict_signature` (no real GPG
subprocess — pure structural/format checks) is separated from the
GPG-backed proofs (which need `verifier_gpg_keys`, session-scoped, real
throwaway keypairs — see conftest.py).
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

from conftest import sign_verdict_for_test

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"

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


def _blob_sha(root, rel_path):
    return _git(root, "hash-object", rel_path).stdout.strip()


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
    p.write_text(
        "---\n" + yaml.safe_dump(verdict_dict) + "---\n\n# Verdict body\n",
        encoding="utf-8",
    )
    return p


def _policy_dict(rule_allowed_verifiers, verifier_keys):
    return {
        "policy": {
            "version": 1,
            "rules": [{
                "id": "prod-src",
                "description": "test-only prod rule",
                "globs": ["src/prod/**"],
                "classification": ["prod_touching"],
                "require_verdict": True,
                "allowed_verifiers": list(rule_allowed_verifiers),
            }],
            "hard_floor_rules": [],
            "verifier_keys": verifier_keys,
        }
    }


def _bundle_key(root, name, key):
    keys_dir = root / ".tess" / "keys" / "verifiers"
    keys_dir.mkdir(parents=True, exist_ok=True)
    (keys_dir / f"{name.lower()}.asc").write_text(key.pubkey_armored, encoding="utf-8")
    return f".tess/keys/verifiers/{name.lower()}.asc"


@pytest.fixture
def signing_repo(project, verifier_gpg_keys):
    """A real git repo with the real schemas, a `prod-src` rule allowing
    Reid, and Reid's + Lysandra's real generated test keys BOTH registered
    in verifier_keys (so tests can prove both 'Reid's signature clears' and
    'Lysandra's signature — validly hers, just not allowed for this rule —
    does not')."""
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)
    verifier_keys = {}
    for name in ("Reid", "Lysandra"):
        key = verifier_gpg_keys[name]
        rel = _bundle_key(root, name, key)
        verifier_keys[name] = {"fingerprint": key.fpr, "public_key_file": rel}
    policy = _policy_dict(["Reid"], verifier_keys)
    (root / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    _init_repo(root)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")
    return root


# ---------------------------------------------------------------------------
# 1) A validly-signed verdict from an allowed verifier clears the gate
# ---------------------------------------------------------------------------

def test_validly_signed_verdict_from_allowed_verifier_clears(signing_repo, run_cli, engine, verifier_gpg_keys):
    base = _base_sha(signing_repo)
    (signing_repo / "src" / "prod").mkdir(parents=True)
    (signing_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(signing_repo, "src/prod/app.py")
    verdict = _base_verdict(["src/prod/**"], {"src/prod/app.py": blob})
    verdict["signature"] = sign_verdict_for_test(engine, verdict, verifier_gpg_keys["Reid"])
    _write_verdict(signing_repo, "missions/m1/verdicts/prod-src.verdict.md", verdict)
    head = _commit_all(signing_repo, "prod change + validly signed Reid verdict")

    r = run_cli(signing_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is False
    assert payload["reasons"] == []


# ---------------------------------------------------------------------------
# 2) An UNSIGNED verdict — otherwise perfect — is BLOCKED (fail-closed)
# ---------------------------------------------------------------------------

def test_unsigned_verdict_is_blocked_even_though_otherwise_perfect(signing_repo, run_cli):
    base = _base_sha(signing_repo)
    (signing_repo / "src" / "prod").mkdir(parents=True)
    (signing_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(signing_repo, "src/prod/app.py")
    # Right glob, right verifier, right artifact_hashes — the ONLY thing
    # missing is a signature.
    verdict = _base_verdict(["src/prod/**"], {"src/prod/app.py": blob})
    _write_verdict(signing_repo, "missions/m1/verdicts/prod-src.verdict.md", verdict)
    head = _commit_all(signing_repo, "prod change + unsigned verdict")

    r = run_cli(signing_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any(
        "src/prod/app.py" in reason and "no signature block present" in reason
        for reason in payload["reasons"]
    )


# ---------------------------------------------------------------------------
# 3) A HAND-FAKED signature block (garbage armored text) is BLOCKED
# ---------------------------------------------------------------------------

def test_hand_faked_signature_is_blocked(signing_repo, run_cli, engine):
    """A weak/malicious agent hand-writing a fake `signature` block (right
    shape, garbage content — exactly the attack this feature exists to
    close) must not clear the gate."""
    base = _base_sha(signing_repo)
    (signing_repo / "src" / "prod").mkdir(parents=True)
    (signing_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(signing_repo, "src/prod/app.py")
    verdict = _base_verdict(["src/prod/**"], {"src/prod/app.py": blob})
    canonical = engine.verdict_canonical_bytes(verdict)
    verdict["signature"] = {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": hashlib.sha256(canonical).hexdigest(),
        "signature_armored": (
            "-----BEGIN PGP SIGNATURE-----\n\n"
            "SGFuZC1mYWtlZCwgbm90IGEgcmVhbCBzaWduYXR1cmUuIFRvdGFsbHkgbGVnaXQu\n"
            "-----END PGP SIGNATURE-----\n"
        ),
    }
    _write_verdict(signing_repo, "missions/m1/verdicts/prod-src.verdict.md", verdict)
    head = _commit_all(signing_repo, "prod change + hand-faked signature")

    r = run_cli(signing_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("src/prod/app.py" in reason for reason in payload["reasons"])


# ---------------------------------------------------------------------------
# 4) A WRONG-KEY signature is BLOCKED
# ---------------------------------------------------------------------------

def test_wrong_key_signature_is_blocked(signing_repo, run_cli, engine, verifier_gpg_keys):
    """Content genuinely, validly signed — but with Lysandra's key, while
    the verdict CLAIMS `verifier: Reid`. Reid's registered key never
    touched this signature, so it must not verify."""
    base = _base_sha(signing_repo)
    (signing_repo / "src" / "prod").mkdir(parents=True)
    (signing_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(signing_repo, "src/prod/app.py")
    verdict = _base_verdict(["src/prod/**"], {"src/prod/app.py": blob}, verifier="Reid")
    # Sign with LYSANDRA's key while claiming to be Reid.
    verdict["signature"] = sign_verdict_for_test(engine, verdict, verifier_gpg_keys["Lysandra"])
    _write_verdict(signing_repo, "missions/m1/verdicts/prod-src.verdict.md", verdict)
    head = _commit_all(signing_repo, "prod change + wrong-key signature")

    r = run_cli(signing_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any(
        "src/prod/app.py" in reason and ("does NOT match" in reason or "verification failed" in reason)
        for reason in payload["reasons"]
    )


def test_unregistered_verifier_signature_is_blocked(project, verifier_gpg_keys, run_cli, engine):
    """A verifier who signs honestly with their own real key, but who was
    never registered in policy.verifier_keys at all, cannot clear the
    gate — there is no key to check the signature against."""
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)
    # verifier_keys deliberately does NOT include Reid.
    policy = _policy_dict(["Reid"], {})
    (root / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    _init_repo(root)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")

    base = _base_sha(root)
    (root / "src" / "prod").mkdir(parents=True)
    (root / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(root, "src/prod/app.py")
    verdict = _base_verdict(["src/prod/**"], {"src/prod/app.py": blob})
    verdict["signature"] = sign_verdict_for_test(engine, verdict, verifier_gpg_keys["Reid"])
    _write_verdict(root, "missions/m1/verdicts/prod-src.verdict.md", verdict)
    head = _commit_all(root, "prod change + unregistered-verifier signature")

    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("no registered public key" in reason for reason in payload["reasons"])


# ---------------------------------------------------------------------------
# 5) A TAMPERED verdict (edited after signing) is BLOCKED
# ---------------------------------------------------------------------------

def test_tampered_verdict_after_signing_is_blocked(signing_repo, run_cli, engine, verifier_gpg_keys):
    """Sign a verdict honestly, THEN mutate a field without re-signing
    (e.g. widening covers_paths, or flipping a finding) — the recorded
    signed_content_sha256 no longer matches, so the tamper is caught
    deterministically, not just by luck of a broken signature."""
    base = _base_sha(signing_repo)
    (signing_repo / "src" / "prod").mkdir(parents=True)
    (signing_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(signing_repo, "src/prod/app.py")
    verdict = _base_verdict(["src/prod/**"], {"src/prod/app.py": blob})
    verdict["signature"] = sign_verdict_for_test(engine, verdict, verifier_gpg_keys["Reid"])

    # Tamper AFTER signing: change the summary line (any field would do).
    verdict["summary_line"] = "Reviewed. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Top priority: none. TAMPERED."

    _write_verdict(signing_repo, "missions/m1/verdicts/prod-src.verdict.md", verdict)
    head = _commit_all(signing_repo, "prod change + tampered-after-signing verdict")

    r = run_cli(signing_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any(
        "src/prod/app.py" in reason and "tampered" in reason
        for reason in payload["reasons"]
    )


# ---------------------------------------------------------------------------
# 6) Signing ties to allowed_verifiers: a validly-signed verdict from a
#    verifier who IS registered but NOT allowed for this rule still blocks.
# ---------------------------------------------------------------------------

def test_validly_signed_but_disallowed_verifier_does_not_clear(signing_repo, run_cli, engine, verifier_gpg_keys):
    """Lysandra's signature is 100% cryptographically genuine — signed with
    HER OWN registered key, verifies cleanly — but the 'prod-src' rule only
    allows Reid. A real signature from the wrong DOMAIN of verifier must
    not clear a rule it has no standing on."""
    base = _base_sha(signing_repo)
    (signing_repo / "src" / "prod").mkdir(parents=True)
    (signing_repo / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _blob_sha(signing_repo, "src/prod/app.py")
    verdict = _base_verdict(["src/prod/**"], {"src/prod/app.py": blob}, verifier="Lysandra")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, verifier_gpg_keys["Lysandra"])
    _write_verdict(signing_repo, "missions/m1/verdicts/prod-src.verdict.md", verdict)
    head = _commit_all(signing_repo, "prod change + validly-signed but disallowed verifier")

    r = run_cli(signing_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any(
        "src/prod/app.py" in reason and "allowed verifier" in reason
        for reason in payload["reasons"]
    )


# ---------------------------------------------------------------------------
# Unit-level: _gate_verify_verdict_signature structural/format checks
# (no real GPG subprocess needed for these — pure Python logic)
# ---------------------------------------------------------------------------

def test_verify_rejects_missing_signature(engine):
    ok, reason = engine._gate_verify_verdict_signature(
        Path("."), {"policy": {"verifier_keys": {}}}, {"verifier": "Reid"},
    )
    assert ok is False
    assert "no signature block present" in reason


def test_verify_rejects_unknown_algorithm(engine):
    instance = {"verifier": "Reid", "signature": {"algorithm": "rot13", "signed_content_sha256": "a" * 64, "signature_armored": "x"}}
    ok, reason = engine._gate_verify_verdict_signature(Path("."), {"policy": {"verifier_keys": {}}}, instance)
    assert ok is False
    assert "not supported" in reason


def test_verify_rejects_malformed_hash(engine):
    instance = {
        "verifier": "Reid",
        "signature": {"algorithm": "gpg-detached-armor", "signed_content_sha256": "not-hex", "signature_armored": "x"},
    }
    ok, reason = engine._gate_verify_verdict_signature(Path("."), {"policy": {"verifier_keys": {}}}, instance)
    assert ok is False
    assert "64-hex-char" in reason


def test_verify_rejects_stale_content_hash(engine):
    instance = {
        "verifier": "Reid", "disposition": "APPROVE",
        "signature": {"algorithm": "gpg-detached-armor", "signed_content_sha256": "0" * 64, "signature_armored": "x"},
    }
    ok, reason = engine._gate_verify_verdict_signature(Path("."), {"policy": {"verifier_keys": {}}}, instance)
    assert ok is False
    assert "tampered" in reason


def test_verify_rejects_malformed_registered_fingerprint(engine):
    instance = {"verifier": "Reid"}
    canonical = engine.verdict_canonical_bytes(instance)
    content_hash = hashlib.sha256(canonical).hexdigest()
    instance["signature"] = {"algorithm": "gpg-detached-armor", "signed_content_sha256": content_hash, "signature_armored": "x"}
    policy_instance = {"policy": {"verifier_keys": {"Reid": {"fingerprint": "not-a-fingerprint", "public_key_file": "x.asc"}}}}
    ok, reason = engine._gate_verify_verdict_signature(Path("."), policy_instance, instance)
    assert ok is False
    assert "40-hex" in reason


def test_verify_rejects_missing_key_file(engine, tmp_path):
    instance = {"verifier": "Reid"}
    canonical = engine.verdict_canonical_bytes(instance)
    content_hash = hashlib.sha256(canonical).hexdigest()
    instance["signature"] = {"algorithm": "gpg-detached-armor", "signed_content_sha256": content_hash, "signature_armored": "x"}
    policy_instance = {
        "policy": {"verifier_keys": {"Reid": {"fingerprint": "A" * 40, "public_key_file": ".tess/keys/verifiers/nope.asc"}}},
    }
    ok, reason = engine._gate_verify_verdict_signature(tmp_path, policy_instance, instance)
    assert ok is False
    assert "not found on disk" in reason


def test_lint_policy_rejects_unrecognized_verifier_key_name(engine):
    instance = {
        "policy": {
            "version": 1, "rules": [], "hard_floor_rules": [],
            "verifier_keys": {"NotARealVerifier": {"fingerprint": "A" * 40, "public_key_file": "x.asc"}},
        }
    }
    errors = engine._lint_policy(instance)
    assert any("NotARealVerifier" in e and "not one of the six named verifiers" in e for e in errors)


def test_lint_policy_accepts_real_verifier_key_names(engine):
    instance = {
        "policy": {
            "version": 1, "rules": [], "hard_floor_rules": [],
            "verifier_keys": {"Reid": {"fingerprint": "A" * 40, "public_key_file": "x.asc"}},
        }
    }
    assert engine._lint_policy(instance) == []


# ---------------------------------------------------------------------------
# `tessctl verdict sign` / `tessctl verdict verify` CLI round-trip
# ---------------------------------------------------------------------------

def test_cli_sign_then_verify_round_trip(project, run_cli, verifier_gpg_keys):
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)
    key = verifier_gpg_keys["Reid"]
    rel = _bundle_key(root, "Reid", key)
    policy = _policy_dict(["Reid"], {"Reid": {"fingerprint": key.fpr, "public_key_file": rel}})
    (root / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")

    verdict_path = root / "missions" / "m1" / "verdicts" / "prod-src.verdict.md"
    verdict_path.parent.mkdir(parents=True)
    verdict_path.write_text(
        "---\n" + yaml.safe_dump(_base_verdict(["src/prod/**"], {})) + "---\n\nBody.\n",
        encoding="utf-8",
    )

    r_sign = run_cli(
        root, "verdict", "sign", str(verdict_path),
        "--verifier", "Reid", "--key-id", key.fpr, "--gnupg-home", str(key.home),
    )
    assert r_sign.returncode == 0, r_sign.stdout + r_sign.stderr
    assert "signed" in r_sign.stdout.lower()

    r_verify = run_cli(root, "verdict", "verify", str(verdict_path), "--json")
    assert r_verify.returncode == 0, r_verify.stdout + r_verify.stderr
    payload = json.loads(r_verify.stdout)
    assert payload["valid"] is True


def test_cli_verify_fails_on_unsigned_verdict(project, run_cli, verifier_gpg_keys):
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)
    key = verifier_gpg_keys["Reid"]
    rel = _bundle_key(root, "Reid", key)
    policy = _policy_dict(["Reid"], {"Reid": {"fingerprint": key.fpr, "public_key_file": rel}})
    (root / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")

    verdict_path = root / "missions" / "m1" / "verdicts" / "prod-src.verdict.md"
    verdict_path.parent.mkdir(parents=True)
    verdict_path.write_text(
        "---\n" + yaml.safe_dump(_base_verdict(["src/prod/**"], {})) + "---\n\nBody.\n",
        encoding="utf-8",
    )

    r_verify = run_cli(root, "verdict", "verify", str(verdict_path), "--json")
    assert r_verify.returncode == 1
    payload = json.loads(r_verify.stdout)
    assert payload["valid"] is False
    assert "no signature block present" in payload["reason"]


def test_cli_sign_rejects_verifier_mismatch(project, run_cli, verifier_gpg_keys):
    """--verifier must agree with the file's own `verifier:` field — a
    Reid-keyed signer cannot casually sign a verdict claiming to be a
    different verifier."""
    root = project.root
    key = verifier_gpg_keys["Reid"]
    verdict_path = root / "prod-src.verdict.json"
    verdict = _base_verdict(["src/prod/**"], {}, verifier="Cyra")
    verdict_path.write_text(json.dumps(verdict), encoding="utf-8")

    r = run_cli(
        root, "verdict", "sign", str(verdict_path),
        "--verifier", "Reid", "--key-id", key.fpr, "--gnupg-home", str(key.home),
    )
    assert r.returncode != 0
    assert "does not match" in (r.stdout + r.stderr)


def test_cli_sign_produces_schema_valid_signature_block(project, run_cli, verifier_gpg_keys):
    """The `signature` block `tessctl verdict sign` writes must itself pass
    core/contracts/verdict.schema.json's $defs.VerdictSignature shape."""
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    key = verifier_gpg_keys["Reid"]
    verdict_path = root / "prod-src.verdict.json"
    verdict_path.write_text(json.dumps(_base_verdict(["src/prod/**"], {})), encoding="utf-8")

    r = run_cli(
        root, "verdict", "sign", str(verdict_path),
        "--verifier", "Reid", "--key-id", key.fpr, "--gnupg-home", str(key.home),
    )
    assert r.returncode == 0, r.stdout + r.stderr

    signed = json.loads(verdict_path.read_text())
    sig = signed["signature"]
    assert sig["algorithm"] == "gpg-detached-armor"
    assert len(sig["signed_content_sha256"]) == 64
    assert "BEGIN PGP SIGNATURE" in sig["signature_armored"]
