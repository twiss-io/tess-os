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
import subprocess
import sys
from pathlib import Path

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
