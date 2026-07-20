"""Shared builders for the tools/receipt-emit test suite.

Reuses `tests/_agent_receipt_fixtures.py`'s `base_verdict` / `base_signoff` /
`write_key` helpers — the SAME signed-decision building blocks the
`tools/receipt-verify` suite already uses — rather than a second,
independent set. Adds only what `tools/receipt-emit` specifically needs:
its own module path, a minimal test `policy.yaml` fixture, and a subprocess
runner for its CLI.

`tools/receipt-emit`'s own modules (`assemble.py`, `chain_atomic.py`,
`gpg_sign.py`, `policy_lookup.py`) internally `import canonical` /
`import checks` as top-level module names — the same convention
`tools/receipt-verify/receipt_verify.py` itself uses — so
`tools/receipt-verify/` must be on `sys.path` BEFORE they are imported here.
`tests/_agent_receipt_fixtures.py` already does this for its own purposes;
this file does it again explicitly (order-independent — `sys.path.insert`
of the same directory twice is harmless) so this module never depends on
import order across test files.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RECEIPT_VERIFY_DIR = REPO_ROOT / "tools" / "receipt-verify"
EMIT_DIR = REPO_ROOT / "tools" / "receipt-emit"
RECEIPT_EMIT_CLI = EMIT_DIR / "receipt_emit.py"

sys.path.insert(0, str(RECEIPT_VERIFY_DIR))
sys.path.insert(0, str(EMIT_DIR))

import canonical  # noqa: E402,F401  (tools/receipt-verify/canonical.py)
import checks  # noqa: E402,F401  (tools/receipt-verify/checks.py)

import assemble  # noqa: E402,F401
import chain_atomic  # noqa: E402,F401
import gpg_sign  # noqa: E402,F401
import policy_lookup  # noqa: E402,F401
from errors import EmitRefused  # noqa: E402,F401

TEST_POLICY_YAML = """\
policy:
  version: 1
  rules:
    - id: demo-docs-review
      description: "Doc change requires review."
      globs: ["docs/**"]
      classification: [prod_touching]
      require_verdict: true
      allowed_verifiers: [Reid]
  hard_floor_rules:
    - id: money-movement
      category: money_movement
      description: "Hard floor: money movement requires sign-off."
      globs: []
"""


def write_test_policy(tmp_path: Path, yaml_text: str = TEST_POLICY_YAML) -> Path:
    p = tmp_path / "policy.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    return p


def write_decision(tmp_path: Path, filename: str, decision: dict) -> Path:
    p = tmp_path / filename
    p.write_text(json.dumps(decision), encoding="utf-8")
    return p


def export_public_key(key, tmp_path: Path, filename: str) -> Path:
    p = tmp_path / filename
    p.write_text(key.pubkey_armored, encoding="utf-8")
    return p


def run_emit_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RECEIPT_EMIT_CLI), "emit", *args],
        capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# REALISTIC (subkey-bearing) GPG identity — PR #135 review regression fixture
#
# Every OTHER GPG identity in this test suite (`tests/conftest.py`'s
# `verifier_gpg_keys`/`gpg_key`, `examples/receipt-demo/demo_keys.py`) is
# generated SIGN-ONLY, with no subkey at all (`Key-Usage: sign` and no
# `Subkey-Type` in the batch keygen params) — a single-component key that
# emits exactly ONE `fpr:` line from `gpg --with-colons --list-keys`. That
# is precisely why `gpg_sign.resolve_fingerprint`'s original "collect every
# fpr: line" bug (Reid CRITICAL, PR #135 review) was never caught: no
# existing test key ever gave it a SECOND `fpr:` line to trip over. A
# REALISTIC operator key — the actual `gpg --quick-generate-key` /
# `--full-generate-key` default shape, primary key signs+certifies, a
# separate subkey encrypts — always has at least two, and the original bug
# refused to sign with one at all.
# ---------------------------------------------------------------------------


def _primary_fingerprint_from_list_keys_output(list_keys_stdout: str) -> str | None:
    """An INDEPENDENT ground-truth extraction of the primary fingerprint,
    deliberately written separately from (never calling into)
    `gpg_sign.resolve_fingerprint` — the function under test — so this
    fixture's own correctness does not depend on the very code the
    regression test exists to check."""
    primary_fpr = None
    current_record = None
    for line in list_keys_stdout.splitlines():
        fields = line.split(":")
        if fields[0] in ("pub", "sub"):
            current_record = fields[0]
        elif fields[0] == "fpr" and current_record == "pub" and len(fields) > 9:
            primary_fpr = fields[9]
    return primary_fpr


def generate_subkey_bearing_key(name: str, email: str) -> types.SimpleNamespace:
    """A throwaway ed25519 GPG identity WITH a default ECDH encryption
    subkey, in its own isolated GNUPGHOME under /tmp (short prefix — see
    `demo_keys.py`'s own comment on gpg-agent's ~104-char UNIX socket path
    limit). Returns `types.SimpleNamespace(name, home, fpr,
    pubkey_armored, email)` — the SAME shape `tests/conftest.py`'s own key
    fixtures use, so it drops into `write_key`/`export_public_key`/
    `sign_verdict_for_test`-style helpers unmodified. Caller must tear
    down via `destroy_subkey_bearing_key`."""
    home = Path(tempfile.mkdtemp(prefix=f"subkey{name.lower()[:6]}", dir="/tmp"))
    os.chmod(home, 0o700)
    params = home / "keyparams"
    params.write_text(
        "%no-protection\n"
        "Key-Type: eddsa\n"
        "Key-Curve: ed25519\n"
        "Key-Usage: sign\n"
        "Subkey-Type: ecdh\n"
        "Subkey-Curve: cv25519\n"
        "Subkey-Usage: encrypt\n"
        f"Name-Real: {name}\n"
        f"Name-Email: {email}\n"
        "Expire-Date: 0\n"
        "%commit\n"
    )
    env = {**os.environ, "GNUPGHOME": str(home)}
    result = subprocess.run(["gpg", "--batch", "--gen-key", str(params)], capture_output=True, text=True, env=env)
    if result.returncode != 0:
        shutil.rmtree(home, ignore_errors=True)
        pytest.skip(f"gpg subkey-bearing key generation failed: {result.stderr}")

    listing = subprocess.run(
        ["gpg", "--homedir", str(home), "--with-colons", "--list-keys", email],
        capture_output=True, text=True,
    )
    fpr_line_count = sum(1 for line in listing.stdout.splitlines() if line.startswith("fpr:"))
    if fpr_line_count < 2:
        shutil.rmtree(home, ignore_errors=True)
        pytest.skip(
            f"test setup did not actually produce a subkey-bearing key "
            f"({fpr_line_count} fpr: line(s)) — this fixture is meaningless "
            f"without a real subkey present"
        )

    primary_fpr = _primary_fingerprint_from_list_keys_output(listing.stdout)
    if not primary_fpr:
        shutil.rmtree(home, ignore_errors=True)
        pytest.skip("could not extract the generated subkey-bearing key's primary fingerprint")

    export = subprocess.run(
        ["gpg", "--homedir", str(home), "--export", "--armor", primary_fpr],
        capture_output=True, text=True,
    )
    return types.SimpleNamespace(name=name, home=home, fpr=primary_fpr, pubkey_armored=export.stdout, email=email)


def destroy_subkey_bearing_key(key: types.SimpleNamespace) -> None:
    subprocess.run(
        ["gpgconf", "--homedir", str(key.home), "--kill", "gpg-agent"],
        capture_output=True, env={**os.environ, "GNUPGHOME": str(key.home)},
    )
    shutil.rmtree(str(key.home), ignore_errors=True)


@pytest.fixture
def subkey_bearing_gpg_key():
    """pytest fixture wrapping `generate_subkey_bearing_key` /
    `destroy_subkey_bearing_key` — function-scoped (this key is not reused
    across the whole session the way `verifier_gpg_keys` is; only one or
    two tests need it)."""
    key = generate_subkey_bearing_key("Realistic", "realistic@receipt-emit.test")
    yield key
    destroy_subkey_bearing_key(key)
