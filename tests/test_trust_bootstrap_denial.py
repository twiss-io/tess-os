"""Symbolic coverage for verifier-bootstrap denial.

These tests deliberately do not generate keys, invoke GPG, sign content, or
modify a verifier registration. They exercise only the gate's trust-boundary
decision and the disabled CLI path.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


def _policy(verifier_keys: dict) -> dict:
    return {"policy": {"verifier_keys": verifier_keys}}


def _signoff_policy(signoff_keys: dict) -> dict:
    return {"policy": {"signoff_keys": signoff_keys}}


def _symbolic_verdict(engine, verifier: str) -> dict:
    verdict = {
        "verifier": verifier,
        "signature": {
            "algorithm": engine.VERDICT_SIGNATURE_ALGORITHM,
            "signature_armored": "symbolic-signature-not-for-crypto",
            "signed_content_sha256": "",
        },
    }
    verdict["signature"]["signed_content_sha256"] = hashlib.sha256(
        engine.verdict_canonical_bytes(verdict)
    ).hexdigest()
    return verdict


def _symbolic_signoff(engine, authorized_by: str) -> dict:
    signoff = {
        "rule_id": "credentials",
        "category": "credentials",
        "authorized_by": authorized_by,
        "rationale": "symbolic boundary test only",
        "authorized_at": "2026-07-16T00:00:00Z",
        "signature": {
            "algorithm": engine.SIGNOFF_SIGNATURE_ALGORITHM,
            "signature_armored": "symbolic-signature-not-for-crypto",
            "signed_content_sha256": "",
        },
    }
    signoff["signature"]["signed_content_sha256"] = hashlib.sha256(
        engine.signoff_canonical_bytes(signoff)
    ).hexdigest()
    return signoff


def _tree_snapshot(root, paths: tuple[str, ...]) -> dict:
    snapshot = {}
    for rel in paths:
        path = root / rel
        if not path.exists():
            snapshot[rel] = None
        elif path.is_file():
            snapshot[rel] = ("file", path.read_bytes())
        else:
            snapshot[rel] = (
                "dir",
                tuple(
                    (str(child.relative_to(path)), child.read_bytes())
                    for child in sorted(path.rglob("*"))
                    if child.is_file()
                ),
            )
    return snapshot


def test_engine_contains_no_turnkey_verifier_bootstrap_implementation(engine):
    source = Path(engine.__file__).read_text(encoding="utf-8")

    for forbidden in (
        "%no-protection",
        "_policy_yaml_upsert_verifier_key",
        "verdict keygen: generated a new sign-only GPG identity",
    ):
        assert forbidden not in source


def test_candidate_key_and_symbolic_verdict_are_denied_when_baseline_is_empty(engine, tmp_path):
    candidate = _policy(
        {
            "Quinn": {
                "fingerprint": "B" * 40,
                "public_key_file": ".tess/keys/verifiers/quinn.asc",
            }
        }
    )
    effective = engine._gate_verifier_keys_from_trusted_baseline(
        candidate, _policy({})
    )

    assert effective["policy"]["verifier_keys"] == {}
    assert candidate["policy"]["verifier_keys"]["Quinn"]["fingerprint"] == "B" * 40

    valid, reason = engine._gate_verify_verdict_signature(
        tmp_path, effective, _symbolic_verdict(engine, "Quinn")
    )
    assert valid is False
    assert "no registered public key for verifier 'Quinn'" in reason


@pytest.mark.parametrize(
    "colon_output",
    (
        b"pub:::::::::\nsec:::::::::\n",
        b"pub:::::::::\nssb:::::::::\n",
        b"uid:::::::::\n",
        b"gpg: malformed OpenPGP packet\n",
    ),
)
def test_base_certificate_helper_rejects_secret_or_nonpublic_gpg_output(
    engine, tmp_path, monkeypatch, colon_output
):
    """BASE bytes must be public-only before either caller can import them."""
    calls = []

    def fake_subprocess_run(command, *_args, **_kwargs):
        calls.append((command, _kwargs))
        return SimpleNamespace(returncode=0, stderr=b"", stdout=colon_output)

    monkeypatch.setattr(engine.subprocess, "run", fake_subprocess_run)

    assert engine._gpg_public_certificate_from_bytes_is_safe(b"candidate", tmp_path) is False
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert "--import-options" in command and "show-only" in command
    assert "--dry-run" in command and "--import" in command
    assert kwargs["input"] == b"candidate"


def test_rejected_base_certificate_never_reaches_verifier_or_signoff_import(
    engine, tmp_path, monkeypatch
):
    """Reverse direction: a rejected BASE blob stops before every real import."""
    verifier_policy = _policy({
        "Reid": {
            "fingerprint": "A" * 40,
            "public_key_file": ".tess/keys/verifiers/reid.asc",
        }
    })
    signoff_policy = _signoff_policy({
        "Xavier": {
            "fingerprint": "A" * 40,
            "public_key_file": ".tess/keys/signoffs/xavier.asc",
        }
    })

    monkeypatch.setattr(engine, "_gpg_public_certificate_from_bytes_is_safe", lambda *_args: False)

    def import_must_not_run(*_args, **_kwargs):
        raise AssertionError("a rejected BASE certificate must never reach gpg import")

    monkeypatch.setattr(engine.subprocess, "run", import_must_not_run)

    verdict_ok, verdict_reason = engine._gate_verify_verdict_signature(
        tmp_path,
        verifier_policy,
        _symbolic_verdict(engine, "Reid"),
        trusted_verifier_key_blobs={"Reid": b"rejected-base-certificate"},
        trusted_verifier_key_errors={},
    )
    signoff_ok, signoff_reason = engine._gate_verify_signoff_signature(
        tmp_path,
        signoff_policy,
        _symbolic_signoff(engine, "Xavier"),
        trusted_signoff_key_blobs={"Xavier": b"rejected-base-certificate"},
        trusted_signoff_key_errors={},
    )

    assert verdict_ok is False
    assert "immutable BASE verifier certificate" in verdict_reason
    assert signoff_ok is False
    assert "immutable BASE sign-off certificate" in signoff_reason


def test_missing_baseline_also_denies_candidate_verifier(engine):
    candidate = _policy(
        {
            "Reid": {
                "fingerprint": "C" * 40,
                "public_key_file": ".tess/keys/verifiers/reid.asc",
            }
        }
    )

    effective = engine._gate_verifier_keys_from_trusted_baseline(candidate, None)

    assert effective["policy"]["verifier_keys"] == {}
    assert candidate["policy"]["verifier_keys"]["Reid"]["fingerprint"] == "C" * 40


def test_existing_baseline_verifier_remains_usable_symbolically(engine, tmp_path, monkeypatch):
    baseline_key = {
        "fingerprint": "A" * 40,
        "public_key_file": ".tess/keys/verifiers/reid.asc",
    }
    candidate = _policy(
        {
            "Reid": {
                "fingerprint": "B" * 40,
                "public_key_file": ".tess/keys/verifiers/reid-new.asc",
            },
            "Quinn": {
                "fingerprint": "C" * 40,
                "public_key_file": ".tess/keys/verifiers/quinn.asc",
            },
        }
    )
    effective = engine._gate_verifier_keys_from_trusted_baseline(
        candidate, _policy({"Reid": baseline_key})
    )

    assert effective["policy"]["verifier_keys"] == {"Reid": baseline_key}
    assert candidate["policy"]["verifier_keys"]["Reid"]["fingerprint"] == "B" * 40

    imported = {}

    def fake_subprocess_run(command, *_args, **_kwargs):
        if "--import" in command:
            imported["bytes"] = _kwargs["input"]
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"pub:::::::::\n")

    monkeypatch.setattr(engine.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(
        engine,
        "_gpg_verify_detached_signature",
        lambda *_args: (True, "A" * 40, None),
    )

    valid, reason = engine._gate_verify_verdict_signature(
        tmp_path, effective, _symbolic_verdict(engine, "Reid"),
        trusted_verifier_key_blobs={"Reid": b"baseline-public-key"},
        trusted_verifier_key_errors={},
    )
    assert valid is True
    assert reason is None
    assert imported["bytes"] == b"baseline-public-key"


def test_candidate_key_rollback_cannot_bypass_base_key_bytes_or_revocation(engine, tmp_path, monkeypatch):
    """The P0 reverse direction: candidate key bytes never reach GPG.

    This creates a tiny Git history only; it does not create a key, invoke
    GPG, or sign a verdict. The mock verification result models a baseline
    public key whose revocation was removed from the candidate file: the gate
    still imports the BASE blob and rejects the (symbolically) revoked key.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        result = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    git("init")
    key_path = repo / ".tess" / "keys" / "verifiers" / "reid.asc"
    key_path.parent.mkdir(parents=True)
    baseline_bytes = b"BASE public key with revocation material\n"
    key_path.write_bytes(baseline_bytes)
    git("add", ".tess/keys/verifiers/reid.asc")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "base key")
    base = git("rev-parse", "HEAD")

    # Candidate rollback/replacement with the same registered fingerprint.
    key_path.write_bytes(b"candidate key with revocation removed\n")
    policy = _policy({
        "Reid": {
            "fingerprint": "A" * 40,
            "public_key_file": ".tess/keys/verifiers/reid.asc",
        }
    })
    trusted_blobs, trusted_errors = engine._gate_load_baseline_verifier_key_blobs(
        repo, policy, base,
    )
    assert trusted_errors == {}
    assert trusted_blobs == {"Reid": baseline_bytes}

    imported = {}

    def fake_subprocess_run(command, *_args, **_kwargs):
        if "--import" in command:
            imported["bytes"] = _kwargs["input"]
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"pub:::::::::\n")

    monkeypatch.setattr(engine.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(
        engine,
        "_gpg_verify_detached_signature",
        lambda *_args: (True, "A" * 40, "revoked"),
    )

    valid, reason = engine._gate_verify_verdict_signature(
        repo, policy, _symbolic_verdict(engine, "Reid"),
        trusted_verifier_key_blobs=trusted_blobs,
        trusted_verifier_key_errors=trusted_errors,
    )
    assert valid is False
    assert "REVOKED" in reason
    assert imported["bytes"] == baseline_bytes
    assert imported["bytes"] != key_path.read_bytes()


def test_baseline_key_loader_rejects_traversal_and_symlink_entries(engine, tmp_path):
    """BASE key paths are containment-checked and must be regular blobs."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        result = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    git("init")
    target = repo / "trusted.asc"
    target.write_bytes(b"not a key; no crypto is exercised\n")
    key_path = repo / ".tess" / "keys" / "verifiers" / "reid.asc"
    key_path.parent.mkdir(parents=True)
    key_path.symlink_to("../../../trusted.asc")
    git("add", ".tess/keys/verifiers/reid.asc", "trusted.asc")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "symlink key")
    base = git("rev-parse", "HEAD")

    symlink_policy = _policy({
        "Reid": {
            "fingerprint": "A" * 40,
            "public_key_file": ".tess/keys/verifiers/reid.asc",
        }
    })
    blobs, errors = engine._gate_load_baseline_verifier_key_blobs(repo, symlink_policy, base)
    assert blobs == {}
    assert "not a regular blob" in errors["Reid"]

    traversal_policy = _policy({
        "Reid": {
            "fingerprint": "A" * 40,
            "public_key_file": "../outside.asc",
        }
    })
    blobs, errors = engine._gate_load_baseline_verifier_key_blobs(repo, traversal_policy, base)
    assert blobs == {}
    assert "contains '..' traversal" in errors["Reid"]


def test_existing_baseline_signoff_key_remains_usable_symbolically(engine, tmp_path, monkeypatch):
    policy = _signoff_policy({
        "Xavier": {
            "fingerprint": "A" * 40,
            "public_key_file": ".tess/keys/signoffs/xavier.asc",
        }
    })
    imported = {}

    def fake_subprocess_run(command, *_args, **_kwargs):
        if "--import" in command:
            imported["bytes"] = _kwargs["input"]
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"pub:::::::::\n")

    monkeypatch.setattr(engine.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(
        engine,
        "_gpg_verify_detached_signature",
        lambda *_args: (True, "A" * 40, None),
    )

    valid, reason = engine._gate_verify_signoff_signature(
        tmp_path, policy, _symbolic_signoff(engine, "Xavier"),
        trusted_signoff_key_blobs={"Xavier": b"baseline-signoff-public-key"},
        trusted_signoff_key_errors={},
    )
    assert valid is True
    assert reason is None
    assert imported["bytes"] == b"baseline-signoff-public-key"


def test_candidate_signoff_key_rollback_cannot_bypass_base_bytes_or_revocation(engine, tmp_path, monkeypatch):
    """A candidate cannot remove a baseline signoff-key revocation by bytes swap."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        result = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    git("init")
    key_path = repo / ".tess" / "keys" / "signoffs" / "xavier.asc"
    key_path.parent.mkdir(parents=True)
    baseline_bytes = b"BASE signoff public key with revocation material\n"
    key_path.write_bytes(baseline_bytes)
    git("add", ".tess/keys/signoffs/xavier.asc")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "base signoff key")
    base = git("rev-parse", "HEAD")

    # Same registered name/fingerprint, but candidate tries to replace its
    # key material with bytes that omit the revocation.
    key_path.write_bytes(b"candidate signoff key with revocation removed\n")
    policy = _signoff_policy({
        "Xavier": {
            "fingerprint": "A" * 40,
            "public_key_file": ".tess/keys/signoffs/xavier.asc",
        }
    })
    trusted_blobs, trusted_errors = engine._gate_load_baseline_signoff_key_blobs(
        repo, policy, base,
    )
    assert trusted_errors == {}
    assert trusted_blobs == {"Xavier": baseline_bytes}

    imported = {}

    def fake_subprocess_run(command, *_args, **_kwargs):
        if "--import" in command:
            imported["bytes"] = _kwargs["input"]
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"pub:::::::::\n")

    monkeypatch.setattr(engine.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(
        engine,
        "_gpg_verify_detached_signature",
        lambda *_args: (True, "A" * 40, "revoked"),
    )

    valid, reason = engine._gate_verify_signoff_signature(
        repo, policy, _symbolic_signoff(engine, "Xavier"),
        trusted_signoff_key_blobs=trusted_blobs,
        trusted_signoff_key_errors=trusted_errors,
    )
    assert valid is False
    assert "REVOKED" in reason
    assert imported["bytes"] == baseline_bytes
    assert imported["bytes"] != key_path.read_bytes()


def test_signoff_key_loader_rejects_missing_base_blob(engine, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        result = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    git("init")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-m", "empty base")
    base = git("rev-parse", "HEAD")
    policy = _signoff_policy({
        "Xavier": {
            "fingerprint": "A" * 40,
            "public_key_file": ".tess/keys/signoffs/xavier.asc",
        }
    })
    blobs, errors = engine._gate_load_baseline_signoff_key_blobs(repo, policy, base)
    assert blobs == {}
    assert "missing or ambiguous" in errors["Xavier"]


def test_keygen_refusal_makes_zero_policy_key_or_lock_mutations(project, run_cli):
    policy = "policy:\n  verifier_keys: {}\n"
    project.add(
        "core/policy/policy.yaml",
        policy,
        core_key=".tess/core/policy/policy.yaml",
    )
    project.write()
    watched = (
        "core/policy/policy.yaml",
        ".tess/core/policy/policy.yaml",
        ".tess/tess.lock",
        ".tess/keys",
    )
    before = _tree_snapshot(project.root, watched)

    result = run_cli(
        project.root,
        "verdict",
        "keygen",
        "--verifier",
        "Reid",
        extra_env={"PATH": ""},
    )

    assert result.returncode != 0
    assert "TRUST_BOOTSTRAP_REQUIRED" in (result.stdout + result.stderr)
    assert _tree_snapshot(project.root, watched) == before

    no_arg_result = run_cli(
        project.root,
        "verdict",
        "keygen",
        extra_env={"PATH": ""},
    )
    assert no_arg_result.returncode != 0
    assert "TRUST_BOOTSTRAP_REQUIRED" in (no_arg_result.stdout + no_arg_result.stderr)
    assert _tree_snapshot(project.root, watched) == before


def test_keygen_refusal_precedes_gpg_or_policy_access(engine, tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("disabled keygen must not reach this dependency")

    monkeypatch.setattr(engine.shutil, "which", forbidden)
    monkeypatch.setattr(engine, "_gate_find_policy_instance_path", forbidden)

    with pytest.raises(SystemExit, match="TRUST_BOOTSTRAP_REQUIRED"):
        engine._cmd_verdict_keygen(SimpleNamespace(verifier="Reid"), tmp_path)
