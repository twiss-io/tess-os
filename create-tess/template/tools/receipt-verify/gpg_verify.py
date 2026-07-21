# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Twiss
"""Minimal, isolated GPG detached-signature verification.

A deliberately small, independent re-implementation of the same fail-closed
GPG verification discipline `.tess/bin/tessctl` already ships and tests for
verdict/sign-off signing (`_gate_verify_verdict_signature`,
`_gpg_verify_detached_signature`, `_gpg_signing_key_validity_reason`,
`_parse_gpg_fingerprint`):

  * the caller's supplied public-key bytes are imported into a fresh,
    throwaway GNUPGHOME for every check — never the ambient/system keyring;
  * the signing key's fingerprint must match the caller-pinned fingerprint
    EXACTLY (C3 exact match — no short-ID or proximity matching);
  * a signature made by a key gpg currently reports EXPIRED or REVOKED is
    rejected even if the cryptographic math checks out (checked at
    verification time, not signing time).

This module never imports `.tess/bin/tessctl` and has no third-party
dependency — only the stdlib and the system `gpg` binary. See
tools/receipt-verify/README.md "Why standalone".
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

FULL_FINGERPRINT_RE = re.compile(r"^[0-9A-Fa-f]{40}$")


def parse_gpg_fingerprint(raw_output: str) -> str:
    """Extract the signing key's fingerprint from gpg's status-fd output.
    Mirrors `_parse_gpg_fingerprint` in .tess/bin/tessctl exactly."""
    for line in raw_output.splitlines():
        parts = line.strip().split()
        if len(parts) >= 3 and parts[0] == "[GNUPG:]" and parts[1] == "VALIDSIG":
            return parts[2].upper()
        m = re.search(r"using\s+\S+\s+key\s+([0-9A-Fa-f]{16,})", line)
        if m:
            return m.group(1).upper()
    return ""


def gpg_signing_key_validity_reason(raw_status_output: str) -> str | None:
    """'revoked' | 'expired' | None — mirrors
    `_gpg_signing_key_validity_reason` in .tess/bin/tessctl exactly."""
    for line in raw_status_output.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == "[GNUPG:]":
            if parts[1] == "REVKEYSIG":
                return "revoked"
            if parts[1] == "EXPKEYSIG":
                return "expired"
    return None


def public_key_bytes_are_safe(key_bytes: bytes, homedir: Path) -> bool:
    """A non-empty PUBLIC-only OpenPGP certificate (no secret-key packets),
    checked WITHOUT creating a keyring entry (`--dry-run`). Mirrors
    `_gpg_public_certificate_from_bytes_is_safe` in .tess/bin/tessctl."""
    if not isinstance(key_bytes, bytes) or not key_bytes or len(key_bytes) > 1024 * 1024:
        return False
    try:
        inspected = subprocess.run(
            [
                "gpg", "--batch", "--no-options", "--homedir", str(homedir),
                "--with-colons", "--fixed-list-mode", "--import-options", "show-only",
                "--dry-run", "--import",
            ],
            input=key_bytes, capture_output=True,
        )
    except OSError:
        return False
    if inspected.returncode != 0:
        return False
    record_types = {
        line.split(":", 1)[0]
        for line in inspected.stdout.decode("utf-8", errors="replace").splitlines()
        if line
    }
    return "pub" in record_types and not bool(record_types & {"sec", "ssb"})


def verify_detached_signature(
    payload: bytes, sig_armored: str, pubkey_bytes: bytes, expected_fingerprint: str,
) -> tuple[bool, str]:
    """Verify `sig_armored` over `payload`, trusting ONLY `pubkey_bytes`
    (imported into a fresh, throwaway GNUPGHOME — never the ambient
    keyring), and require the signing key's fingerprint to equal
    `expected_fingerprint` EXACTLY (uppercase, no spaces, 40 hex chars).

    Returns (ok, reason). reason is '' when ok is True; otherwise a
    human-readable explanation of exactly which check failed."""
    fingerprint = expected_fingerprint.replace(" ", "").upper()
    if not FULL_FINGERPRINT_RE.match(fingerprint):
        return False, f"expected_fingerprint {expected_fingerprint!r} is not a valid 40-hex-char fingerprint"
    if shutil.which("gpg") is None:
        return False, "the 'gpg' binary is not installed or not on PATH"

    homedir = Path(tempfile.mkdtemp(prefix="receipt_verify_gpg_"))
    try:
        try:
            homedir.chmod(0o700)
        except OSError:
            pass
        if not public_key_bytes_are_safe(pubkey_bytes, homedir):
            return False, "supplied public key bytes are not a public-only OpenPGP certificate"

        import_r = subprocess.run(
            ["gpg", "--homedir", str(homedir), "--import"],
            input=pubkey_bytes, capture_output=True,
        )
        if import_r.returncode != 0:
            return False, f"gpg could not import the supplied public key: {import_r.stderr.decode('utf-8', errors='replace').strip()}"

        subprocess.run(
            ["gpg", "--homedir", str(homedir), "--import-ownertrust"],
            input=f"{fingerprint}:6:\n".encode(), capture_output=True,
        )

        payload_path = homedir / "payload.bin"
        payload_path.write_bytes(payload)
        sig_path = homedir / "sig.asc"
        sig_path.write_text(sig_armored, encoding="utf-8")
        env = {**os.environ, "GNUPGHOME": str(homedir)}
        verify_r = subprocess.run(
            ["gpg", "--homedir", str(homedir), "--status-fd", "1",
             "--verify", str(sig_path), str(payload_path)],
            capture_output=True, env=env,
        )
        raw = (
            verify_r.stdout.decode("utf-8", errors="replace")
            + verify_r.stderr.decode("utf-8", errors="replace")
        )
        signing_fp = parse_gpg_fingerprint(raw)
        if not (verify_r.returncode == 0 and signing_fp):
            return False, "gpg signature verification failed (bad signature, or it does not match this content)"
        if signing_fp != fingerprint:
            return False, (
                f"signature was made by key {signing_fp or 'unknown'}, which does NOT match "
                f"the expected fingerprint {fingerprint} — wrong key, fail-closed "
                f"(exact match required, no short-ID/proximity matching)"
            )
        validity_reason = gpg_signing_key_validity_reason(raw)
        if validity_reason is not None:
            return False, (
                f"the signature is cryptographically valid and made by the exact expected key, "
                f"but gpg reports that key is {validity_reason.upper()} as of right now "
                f"(checked at verification time, not signing time)"
            )
        return True, ""
    finally:
        shutil.rmtree(str(homedir), ignore_errors=True)
