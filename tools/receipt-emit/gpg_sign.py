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
    """The full 40-hex PRIMARY-key fingerprint --key-id resolves to in the
    given (or ambient) keyring.

    ★ CRITICAL FIX (Reid, PR #135 review — reproduced end-to-end): GPG's
    `--with-colons --list-keys` output emits one `fpr:` record per key
    COMPONENT, not one per matched CERTIFICATE — a `pub:` (primary) record
    is immediately followed by its own `fpr:` line, and each `sub:`
    (subkey) record is likewise immediately followed by ITS OWN `fpr:`
    line. Any normal key with a default encryption subkey (the standard
    `gpg --quick-generate-key` / `--full-generate-key` shape — primary key
    signs/certifies, a separate subkey encrypts) therefore emits AT LEAST
    TWO `fpr:` lines for ONE certificate. The original version of this
    function collected every `fpr:` line unconditionally, so a normal,
    real operator key was refused as "matches more than one distinct key"
    before it was ever used to sign — fail-closed in the wrong direction,
    against essentially every real key a human operator actually holds.

    Fixed by tracking which record kind (`pub:` or `sub:`) each `fpr:`
    line belongs to and keeping ONLY the ones that follow a `pub:` record
    — the certificate's PRIMARY fingerprint, exactly what
    `gpg --local-user <key-id> --detach-sign` actually signs with for a
    normal key (the primary key itself carries the 's' usage flag; the
    subkey here is encrypt-only and is never selected for signing).
    Deliberately NOT the `tools/receipt-verify/gpg_verify.py` VALIDSIG-
    parsing pattern: VALIDSIG only exists in the status-fd output of an
    actual `--verify` run against an ALREADY-PRODUCED signature — this
    function has to answer "which key will --local-user resolve to" from
    `--list-keys` alone, BEFORE any signature exists (its caller needs the
    fingerprint to export the public key and build the self-verify trust
    entry ahead of signing). Restructuring the emit pipeline to sign
    first and resolve the fingerprint from the signature's own VALIDSIG
    afterward would work too, but it is a materially larger change to an
    already Cyra-reviewed/approved atomicity/fail-closed flow for no
    correctness gain on the "normal subkey-bearing key" case this bug
    report is scoped to — see this PR's own report for the full
    trade-off.

    Fails closed — never falls back to a short id, and never silently
    picks one key out of a GENUINE multi-certificate match (`key_id`
    matching more than one distinct person's primary key)."""
    try:
        result = subprocess.run(
            _cmd(gnupg_home, "--with-colons", "--list-keys", key_id),
            capture_output=True, text=True,
        )
    except OSError as e:
        raise EmitRefused([f"could not run gpg to resolve --key-id {key_id!r}: {e}"])
    if result.returncode != 0:
        raise EmitRefused([f"gpg could not resolve --key-id {key_id!r}: {result.stderr.strip()}"])

    primary_fingerprints = []
    current_record = None  # tracks the most recently seen "pub" or "sub" line
    for line in result.stdout.splitlines():
        fields = line.split(":")
        record_type = fields[0]
        if record_type in ("pub", "sub"):
            current_record = record_type
        elif record_type == "fpr" and current_record == "pub" and len(fields) > 9:
            primary_fingerprints.append(fields[9])

    fingerprints = sorted(set(primary_fingerprints))
    if not fingerprints:
        raise EmitRefused([f"no key matching --key-id {key_id!r} was found in the keyring"])
    if len(fingerprints) > 1:
        raise EmitRefused([
            f"--key-id {key_id!r} matches more than one distinct PRIMARY key "
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
