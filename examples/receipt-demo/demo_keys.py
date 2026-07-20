# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Twiss
"""Ephemeral, demo-only GPG identities for the Agent Receipt walkthrough.

Every key this module generates is:
  * created fresh in a throwaway GNUPGHOME under /tmp, never under this repo;
  * NEVER registered in core/policy/policy.yaml's `verifier_keys`/`signoff_keys`
    (those remain exactly as shipped — see conductor/verdict-signing.md);
  * destroyed (private material deleted, gpg-agent killed) when the demo exits.

This mirrors the exact test-key pattern tests/conftest.py already uses for
`verifier_gpg_keys` (real, ephemeral, isolated-homedir GPG identities) — no
new key-generation trick invented here, and no real verifier or operator key
is ever touched, read, or impersonated.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DemoKey:
    name: str
    home: Path
    fingerprint: str
    public_key_armored: str


def generate_demo_key(name: str, email: str) -> DemoKey:
    """Generate one throwaway ed25519 GPG identity. Homedir lives directly
    under /tmp with a short prefix — gpg-agent's UNIX socket path has a
    ~104-char limit that a deep tmp path can exceed (same reason
    tests/conftest.py's own key fixtures use `dir="/tmp"`)."""
    home = Path(tempfile.mkdtemp(prefix=f"receiptdemo{name.lower()[:6]}", dir="/tmp"))
    os.chmod(home, 0o700)
    params = home / "keyparams"
    params.write_text(
        "%no-protection\n"
        "Key-Type: eddsa\n"
        "Key-Curve: ed25519\n"
        "Key-Usage: sign\n"
        f"Name-Real: {name} (Agent Receipt DEMO key — never registered, test-only)\n"
        f"Name-Email: {email}\n"
        "Expire-Date: 0\n"
        "%commit\n"
    )
    env = {**os.environ, "GNUPGHOME": str(home)}
    result = subprocess.run(["gpg", "--batch", "--gen-key", str(params)], capture_output=True, text=True, env=env)
    if result.returncode != 0:
        shutil.rmtree(home, ignore_errors=True)
        raise RuntimeError(f"demo key generation failed for {name!r}: {result.stderr}")

    listing = subprocess.run(
        ["gpg", "--with-colons", "--list-keys", email], capture_output=True, text=True, env=env,
    )
    fingerprint = ""
    for line in listing.stdout.splitlines():
        if line.startswith("fpr:"):
            fingerprint = line.split(":")[9]
            break
    if not fingerprint:
        shutil.rmtree(home, ignore_errors=True)
        raise RuntimeError(f"could not read the generated fingerprint for {name!r}")

    export = subprocess.run(
        ["gpg", "--homedir", str(home), "--export", "--armor", fingerprint],
        capture_output=True, text=True, env=env,
    )
    return DemoKey(name=name, home=home, fingerprint=fingerprint, public_key_armored=export.stdout)


def sign_with_demo_key(canonical_bytes: bytes, key: DemoKey) -> str:
    env = {**os.environ, "GNUPGHOME": str(key.home)}
    result = subprocess.run(
        ["gpg", "--homedir", str(key.home), "--batch", "--yes", "--local-user", key.fingerprint,
         "--detach-sign", "--armor", "--output", "-"],
        input=canonical_bytes, capture_output=True, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"demo signing failed for {key.name!r}: {result.stderr.decode('utf-8', errors='replace')}")
    return result.stdout.decode("utf-8")


def destroy_demo_key(key: DemoKey) -> None:
    """Kill the throwaway agent and delete the homedir — the private key
    never persists past this process."""
    subprocess.run(
        ["gpgconf", "--homedir", str(key.home), "--kill", "gpg-agent"],
        capture_output=True, env={**os.environ, "GNUPGHOME": str(key.home)},
    )
    shutil.rmtree(str(key.home), ignore_errors=True)
