# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Twiss
"""GPG operations receipt_emit.py needs to PRODUCE a signature — the
signing-side counterpart to tools/receipt-verify/gpg_verify.py's
verification-side operations.

Deliberately kept separate from gpg_verify.py: that module never signs
anything (a standalone third-party VERIFIER has no reason to hold any
private key), and this module never verifies anything — the finished
receipt's own self-verification is delegated to the real, independent
verifier as a subprocess (see receipt_emit.py's `_self_verify`), never
re-implemented here as a second, possibly-drifting check.

`--gnupg-home` is OPTIONAL here (unlike tools/receipt-verify/gpg_verify.py,
which ALWAYS creates its own fresh, throwaway homedir per check — a
standalone verifier has no reason to touch anyone's real keyring). This
tool's whole job is to sign with a REAL key the operator already holds, so
the ambient/default keyring (no `--homedir` at all) is the normal case;
`--gnupg-home` exists for tests and for an operator who deliberately keeps
signing keys in an isolated homedir.
"""

from __future__ import annotations

import shutil
import subprocess

from errors import EmitRefused


def which_gpg() -> str | None:
    return shutil.which("gpg")


def _cmd(gnupg_home: str | None, *args: str) -> list[str]:
    base = ["gpg", "--homedir", gnupg_home] if gnupg_home else ["gpg"]
    return base + list(args)


def resolve_fingerprint(key_id: str, gnupg_home: str | None) -> str:
    """The full 40-hex fingerprint --key-id resolves to in the given (or
    ambient) keyring. Fails closed — never falls back to a short id, and
    never silently picks one key out of an ambiguous match."""
    try:
        result = subprocess.run(
            _cmd(gnupg_home, "--with-colons", "--list-keys", key_id),
            capture_output=True, text=True,
        )
    except OSError as e:
        raise EmitRefused([f"could not run gpg to resolve --key-id {key_id!r}: {e}"])
    if result.returncode != 0:
        raise EmitRefused([f"gpg could not resolve --key-id {key_id!r}: {result.stderr.strip()}"])
    fingerprints = sorted({
        line.split(":")[9] for line in result.stdout.splitlines() if line.startswith("fpr:")
    })
    if not fingerprints:
        raise EmitRefused([f"no key matching --key-id {key_id!r} was found in the keyring"])
    if len(fingerprints) > 1:
        raise EmitRefused([
            f"--key-id {key_id!r} matches more than one distinct key "
            f"({', '.join(fingerprints)}) — pass a full, unambiguous fingerprint"
        ])
    return fingerprints[0]


def export_public_key_armored(fingerprint: str, gnupg_home: str | None) -> str:
    result = subprocess.run(
        _cmd(gnupg_home, "--export", "--armor", fingerprint),
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise EmitRefused([
            f"gpg could not export the public key for {fingerprint}: {result.stderr.strip()}"
        ])
    return result.stdout


def detached_sign(payload: bytes, key_id: str, gnupg_home: str | None) -> str:
    """ASCII-armored detached signature over `payload`, produced by
    --key-id. Same primitive (`gpg --detach-sign --armor`) every other
    signer in this repository already uses (tessctl `verdict sign`,
    tests/conftest.py's `sign_verdict_for_test`, examples/receipt-demo's
    `sign_with_demo_key`) — nothing new invented here."""
    result = subprocess.run(
        _cmd(gnupg_home, "--batch", "--yes", "--local-user", key_id,
             "--detach-sign", "--armor", "--output", "-"),
        input=payload, capture_output=True,
    )
    if result.returncode != 0:
        raise EmitRefused([
            f"gpg signing failed for --key-id {key_id!r}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        ])
    return result.stdout.decode("utf-8")
