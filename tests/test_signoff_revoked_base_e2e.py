"""Real-GPG P0 proof for immutable-BASE revocation enforcement.

The verdict and schema-v2 sign-off are both signed while the throwaway key is
still valid.  The key is then revoked, the revoked public export is committed
at BASE, and candidate bytes roll the files back to the earlier unrevoked
export.  Both verifiers must import the revoked BASE bytes and reject the old
signatures as REVOKED. Every GPG operation uses a fresh OS-managed temporary
home; the user's keyring is never read or modified.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest


IS_CI = os.environ.get("GITHUB_ACTIONS", "").lower() == "true" or bool(os.environ.get("CI"))


def _isolated_gpg(home: Path, *args: str, input_bytes: bytes | None = None):
    env = {**os.environ, "GNUPGHOME": str(home)}
    return subprocess.run(
        [
            "gpg", "--homedir", str(home), "--batch", "--yes",
            "--pinentry-mode", "loopback", "--passphrase", "", *args,
        ],
        input=input_bytes, capture_output=True, env=env,
    )


def _agent_unavailable(result) -> bool:
    text = result.stderr.decode("utf-8", errors="replace").lower()
    return any(token in text for token in (
        "no agent running", "can't connect to the gpg-agent", "ipc connect",
        "failed to start agent", "no pinentry",
    ))


def _new_ephemeral_identity() -> SimpleNamespace:
    if shutil.which("gpg") is None or shutil.which("gpgconf") is None:
        if IS_CI:
            pytest.fail("CI must provide gpg + gpgconf for mandatory revocation E2E")
        pytest.skip("local environment has no gpg/gpgconf")
    home = Path(tempfile.mkdtemp(prefix="tess-signoff-v2-gpg-"))
    home.chmod(0o700)
    uid = "Tess Signoff V2 Ephemeral <signoff-v2@tess.invalid>"
    result = None
    for attempt in range(2):
        result = _isolated_gpg(home, "--quick-generate-key", uid, "ed25519", "sign", "0")
        if result.returncode == 0:
            break
        if attempt == 0 and _agent_unavailable(result):
            subprocess.run(
                ["gpgconf", "--homedir", str(home), "--launch", "gpg-agent"],
                capture_output=True, env={**os.environ, "GNUPGHOME": str(home)},
            )
    if result is None or result.returncode != 0:
        if not IS_CI and result is not None and _agent_unavailable(result):
            shutil.rmtree(home, ignore_errors=True)
            pytest.skip("LOCAL_ENV_GPG_AGENT_UNAVAILABLE: isolated temporary agent could not start")
        detail = result.stderr.decode("utf-8", errors="replace") if result is not None else "no result"
        shutil.rmtree(home, ignore_errors=True)
        pytest.fail(f"ephemeral GPG key generation failed: {detail}")

    listed = _isolated_gpg(home, "--with-colons", "--list-keys", uid)
    assert listed.returncode == 0, listed.stderr.decode("utf-8", errors="replace")
    fingerprint = ""
    for line in listed.stdout.decode("utf-8", errors="replace").splitlines():
        fields = line.split(":")
        if fields[0] == "fpr":
            fingerprint = fields[9]
            break
    assert len(fingerprint) == 40
    exported = _isolated_gpg(home, "--armor", "--export", fingerprint)
    assert exported.returncode == 0
    return SimpleNamespace(
        home=home, fingerprint=fingerprint, unrevoked_public=exported.stdout,
    )


def _sign(engine, data: dict, identity, *, signoff: bool) -> dict:
    canonical = (
        engine.signoff_canonical_bytes(data)
        if signoff else engine.verdict_canonical_bytes(data)
    )
    result = _isolated_gpg(
        identity.home, "--local-user", identity.fingerprint,
        "--detach-sign", "--armor", "--output", "-", input_bytes=canonical,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    return {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": hashlib.sha256(canonical).hexdigest(),
        "signature_armored": result.stdout.decode("utf-8"),
    }


def _revoke_after_signing(identity) -> bytes:
    revocations = list((identity.home / "openpgp-revocs.d").glob("*.rev"))
    assert len(revocations) == 1
    clean = revocations[0].read_text(encoding="utf-8").replace(
        ":-----BEGIN", "-----BEGIN",
    )
    revocation_path = identity.home / "revocation-to-publish.asc"
    revocation_path.write_text(clean, encoding="utf-8")
    imported = _isolated_gpg(identity.home, "--import", str(revocation_path))
    assert imported.returncode == 0, imported.stderr.decode("utf-8", errors="replace")
    exported = _isolated_gpg(identity.home, "--armor", "--export", identity.fingerprint)
    assert exported.returncode == 0
    return exported.stdout


def _git(root: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@tess.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@tess.invalid",
    }
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def test_pre_revocation_verdict_and_signoff_fail_against_revoked_base_bytes(
    engine, tmp_path,
):
    identity = _new_ephemeral_identity()
    try:
        verdict = {
            "verifier": "Reid",
            "output_domain": "Code diff / PR",
            "primary_artifacts_read": ["payments/charge.py"],
            "findings": [],
            "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "summary_line": "Reviewed. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Top priority: none.",
            "disposition": "APPROVE",
            "covers_paths": ["payments/charge.py"],
            "artifact_hashes": {"payments/charge.py": "1" * 40},
        }
        verdict["signature"] = _sign(engine, verdict, identity, signoff=False)

        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        signoff = {
            "schema_version": 2,
            "repository_id": "test/tess-os",
            "rule_id": "money",
            "category": "money_movement",
            "effective_rule_sha256": "a" * 64,
            "base_sha": "2" * 40,
            "payload_head_sha": "3" * 40,
            "artifact_hashes": {"payments/charge.py": "1" * 40},
            "authorized_by": "Xavier",
            "rationale": "Signed while the ephemeral key was still valid.",
            "authorized_at": now.isoformat().replace("+00:00", "Z"),
            "expires_at": (now + datetime.timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        }
        signoff["signature"] = _sign(engine, signoff, identity, signoff=True)

        # Revocation is applied only after both detached signatures exist.
        revoked_public = _revoke_after_signing(identity)
        assert revoked_public != identity.unrevoked_public

        root = tmp_path / "repo"
        root.mkdir()
        _git(root, "init", "-q")
        _git(root, "config", "user.name", "Test")
        _git(root, "config", "user.email", "test@tess.invalid")
        verifier_path = root / ".tess/keys/verifiers/reid.asc"
        signoff_path = root / ".tess/keys/signoffs/xavier.asc"
        verifier_path.parent.mkdir(parents=True)
        signoff_path.parent.mkdir(parents=True)
        verifier_path.write_bytes(revoked_public)
        signoff_path.write_bytes(revoked_public)
        base = _commit(root, "BASE publishes revoked public key bytes")

        policy = {
            "policy": {
                "verifier_keys": {
                    "Reid": {
                        "fingerprint": identity.fingerprint,
                        "public_key_file": ".tess/keys/verifiers/reid.asc",
                    },
                },
                "signoff_keys": {
                    "Xavier": {
                        "fingerprint": identity.fingerprint,
                        "public_key_file": ".tess/keys/signoffs/xavier.asc",
                    },
                },
            },
        }

        # Candidate rollback: both committed candidate paths now omit the
        # revocation, but the loaders below must still return BASE bytes.
        verifier_path.write_bytes(identity.unrevoked_public)
        signoff_path.write_bytes(identity.unrevoked_public)
        _commit(root, "candidate rolls public key bytes back before revocation")

        verifier_blobs, verifier_errors = engine._gate_load_baseline_verifier_key_blobs(
            root, policy, base,
        )
        signoff_blobs, signoff_errors = engine._gate_load_baseline_signoff_key_blobs(
            root, policy, base,
        )
        assert verifier_errors == signoff_errors == {}
        assert verifier_blobs["Reid"] == revoked_public
        assert signoff_blobs["Xavier"] == revoked_public
        assert verifier_blobs["Reid"] != verifier_path.read_bytes()
        assert signoff_blobs["Xavier"] != signoff_path.read_bytes()

        verdict_ok, verdict_reason = engine._gate_verify_verdict_signature(
            root, policy, verdict,
            trusted_verifier_key_blobs=verifier_blobs,
            trusted_verifier_key_errors=verifier_errors,
        )
        signoff_ok, signoff_reason = engine._gate_verify_signoff_signature(
            root, policy, signoff,
            trusted_signoff_key_blobs=signoff_blobs,
            trusted_signoff_key_errors=signoff_errors,
        )
        assert verdict_ok is False and "REVOKED" in verdict_reason
        assert signoff_ok is False and "REVOKED" in signoff_reason
    finally:
        subprocess.run(
            ["gpgconf", "--homedir", str(identity.home), "--kill", "gpg-agent"],
            capture_output=True, env={**os.environ, "GNUPGHOME": str(identity.home)},
        )
        shutil.rmtree(identity.home, ignore_errors=True)
