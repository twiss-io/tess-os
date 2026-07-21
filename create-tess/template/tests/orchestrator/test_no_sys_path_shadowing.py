"""tess-os #162 (Reid MEDIUM, PRIORITY) -- regression proof that `import
orchestrator` no longer shadows a sibling `checks.py`/`canonical.py`
process-wide.

`orchestrator/__init__.py` used to insert `tools/receipt-verify/` -- a
flat, unpackaged directory of genuinely-generic top-level module names
(`checks.py`, `canonical.py`, `gpg_verify.py`, `hmac_verify.py`,
`receipt_verify.py`) -- at `sys.path[0]` (highest priority) as a side
effect of `import orchestrator`. That would silently shadow ANY OTHER
`checks.py`/`canonical.py` resolvable from `sys.path` for the rest of
that process (an "orchestrator reused as an embedded library" footgun),
with no error ever raised. `orchestrator/mission_receipt.py`'s own real
need for `tools/receipt-verify/canonical.py` is now met by an
`importlib.util`-based load under a private, namespaced module name (see
that module's own `_load_receipt_canonical()`), with ZERO `sys.path`
mutation -- see `orchestrator/__init__.py`'s own module docstring for the
removed loop entry.

The proof runs in TWO parts:

  1. A FRESH CHILD SUBPROCESS (never in-process -- so no earlier test
     file's `import orchestrator` in this same pytest session can already
     have touched this process's own `sys.path`/`sys.modules` before the
     import under test runs) plants a DECOY `checks.py`/`canonical.py` on
     `sys.path` BEFORE importing `orchestrator` -- simulating a host
     process that already has its own, unrelated modules resolvable
     under these exact generic names -- then proves: `tools/receipt-verify/`
     is never inserted onto `sys.path` (and nothing already on it is
     removed/replaced -- only the pre-existing, legitimate intent-router/
     spec-engine additions are allowed to be new); the decoy is never
     shadowed (`import
     checks`/`import canonical` still resolve to it, before AND after);
     and Hop 7's own receipt emission (`orchestrator.mission_receipt.
     build_local_approval_receipt`) still SUCCEEDS despite the decoy
     being present -- both decoy functions are rigged to raise on any
     call, so a regression that made Hop 7 resolve the shadowed bare
     names instead of its own private import fails this subprocess loud
     (non-zero exit), not silently.
  2. Back in THIS (parent) process -- which never touches the decoy at
     all -- the receipt the child subprocess wrote to disk is
     independently re-verified with the REAL, standalone
     `tools/receipt-verify/checks.py`, proving Hop 7 used the REAL
     canonicalization the whole time (a receipt actually built against
     the decoy's fake byte functions could never independently verify).
"""

from __future__ import annotations

import json
import subprocess
import sys

import _orchestrator_paths  # noqa: F401 -- sys.path bootstrap
from _orchestrator_paths import REPO_ROOT

import orchestrator  # noqa: F401 -- also puts intent-router/, spec-engine/ onto
# sys.path (NOT tools/receipt-verify/ -- tess-os #162's own fix, proven
# below) for this test's own independent post-hoc verification step.

# Rigged to raise (never to just silently produce a wrong value) so that
# if a future regression ever made orchestrator's Hop 7 resolve the
# process-wide bare `canonical`/`checks` names instead of its own private
# load, the CHILD subprocess below fails loud -- a raised AssertionError,
# not a quietly-wrong signature that might coincidentally still verify.
_DECOY_CANONICAL_PY = '''
IS_DECOY = True


def _boom(name):
    raise AssertionError(
        f"DECOY canonical.{name}() was called -- orchestrator's Hop 7 must "
        "never resolve the process-wide bare 'canonical' module name; it "
        "must load tools/receipt-verify/canonical.py privately (tess-os #162)"
    )


def receipt_signing_bytes(receipt):
    _boom("receipt_signing_bytes")


def decision_signing_bytes(decision):
    _boom("decision_signing_bytes")


def sha256_hex(data):
    _boom("sha256_hex")


def receipt_content_hash(receipt):
    _boom("receipt_content_hash")
'''

_DECOY_CHECKS_PY = '''
IS_DECOY = True


def verify_receipt(*args, **kwargs):
    raise AssertionError("DECOY checks.verify_receipt() was called (tess-os #162)")
'''

_CHILD_SCRIPT = r'''
import json
import sys

decoy_dir = sys.argv[1]
repo_root = sys.argv[2]
output_dir = sys.argv[3]

# A decoy checks.py / canonical.py, planted on sys.path BEFORE orchestrator
# is ever imported -- simulating a host process that already has its own,
# unrelated modules resolvable under these exact generic names.
sys.path.insert(0, decoy_dir)
sys.path.insert(0, repo_root)

path_before_import = list(sys.path)
import orchestrator  # noqa: F401 -- the import under test
path_after_import = list(sys.path)

# `import orchestrator` legitimately still adds intent-router/ and
# spec-engine/ (distinctively-named packages, not part of this bug) --
# the invariant under test is narrower and more precise: NOTHING new on
# sys.path after the import ever mentions receipt-verify/, and every
# entry present before the import is still present, untouched, after it.
newly_added = [p for p in path_after_import if p not in path_before_import]
result = {
    "prior_entries_all_preserved": all(p in path_after_import for p in path_before_import),
    "receipt_verify_dir_on_path": any("receipt-verify" in p for p in path_after_import),
    "newly_added_mentions_receipt_verify": any("receipt-verify" in p for p in newly_added),
}

import checks  # must resolve to the DECOY -- never the real tool
import canonical  # must resolve to the DECOY -- never the real tool
result["checks_is_decoy"] = getattr(checks, "IS_DECOY", False) is True
result["canonical_is_decoy"] = getattr(canonical, "IS_DECOY", False) is True

# Hop 7 must still work correctly, using the REAL canonicalization
# internally -- if it ever accidentally resolved the decoy above instead
# of its own private importlib load, this call raises AssertionError and
# the whole subprocess exits non-zero.
from spec_engine.content import DataModel, HowItLooks, HowItWorks, WhatItDoes, utc_now_iso
from spec_engine.gate_approval import sign_local_approval
from spec_engine.types import Plan, Provenance, SpecDocument
from orchestrator import mission_receipt

identity_dir = output_dir + "/identity"
plan = Plan(
    plan_id="plan-test001", mission_id=None, created_at=utc_now_iso(),
    source_type="fragment", input_excerpt="A test app.",
    what_it_does=WhatItDoes(summary="does stuff"), how_it_looks=HowItLooks(),
    how_it_works=HowItWorks(), data_model=DataModel(),
)
approval = sign_local_approval(plan, approved_by="local:tester#x", approved=True, identity_dir=identity_dir)
spec = SpecDocument(
    spec_id="spec-test001", title="Test App", spec_version=1, status="active",
    provenance=Provenance(
        source_type="fragment", input_excerpt="x", approved_by=approval.approved_by,
        approved_at=utc_now_iso(), generated_at=utc_now_iso(), plan_id=plan.plan_id,
    ),
    what_it_does=plan.what_it_does, how_it_looks=plan.how_it_looks,
    how_it_works=plan.how_it_works, data_model=plan.data_model,
)
receipt = mission_receipt.build_local_approval_receipt(
    plan=plan, approval=approval, spec=spec, target_dir=output_dir + "/generated-app",
    identity_dir=identity_dir,
)
result["receipt_decision_kind"] = receipt["decision_kind"]
result["receipt_signature_algorithm"] = receipt["receipt_signature"]["algorithm"]
result["approved_by"] = approval.approved_by

with open(output_dir + "/receipt.json", "w") as f:
    json.dump(receipt, f)

# The decoy must STILL never have been touched by any of the above.
result["checks_still_decoy_after_hop7"] = getattr(sys.modules["checks"], "IS_DECOY", False) is True
result["canonical_still_decoy_after_hop7"] = getattr(sys.modules["canonical"], "IS_DECOY", False) is True

print(json.dumps(result))
'''


def test_import_orchestrator_does_not_shadow_sibling_checks_and_canonical(tmp_path):
    decoy_dir = tmp_path / "decoy"
    decoy_dir.mkdir()
    (decoy_dir / "canonical.py").write_text(_DECOY_CANONICAL_PY, encoding="utf-8")
    (decoy_dir / "checks.py").write_text(_DECOY_CHECKS_PY, encoding="utf-8")

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    script_path = tmp_path / "_shadow_regression_child.py"
    script_path.write_text(_CHILD_SCRIPT, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(script_path), str(decoy_dir), str(REPO_ROOT), str(output_dir)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        f"child subprocess failed (see stderr for exactly what regressed):\n{proc.stderr}"
    )
    result = json.loads(proc.stdout.strip().splitlines()[-1])

    assert result["prior_entries_all_preserved"] is True, (
        "import orchestrator must never remove/replace an entry already on sys.path"
    )
    assert result["receipt_verify_dir_on_path"] is False, (
        "tools/receipt-verify/ must never be inserted onto sys.path by import orchestrator"
    )
    assert result["newly_added_mentions_receipt_verify"] is False
    assert result["checks_is_decoy"] is True, "a pre-existing sibling checks.py must never be shadowed"
    assert result["canonical_is_decoy"] is True, "a pre-existing sibling canonical.py must never be shadowed"

    # Hop 7 succeeded (a regression resolving the decoy would have raised
    # AssertionError inside the subprocess, caught by the returncode
    # assertion above) and reports the expected local_approval shape.
    assert result["receipt_decision_kind"] == "local_approval"
    assert result["receipt_signature_algorithm"] == "local-hmac-sha256-v1"

    # The decoy is still exactly what it was -- Hop 7's own private load
    # never touched the process-wide bare names either.
    assert result["checks_still_decoy_after_hop7"] is True
    assert result["canonical_still_decoy_after_hop7"] is True

    # Part 2: back in THIS process (no decoy anywhere on its sys.path),
    # independently re-verify the receipt the child subprocess built,
    # with the REAL standalone verifier -- proving Hop 7 genuinely used
    # the real canonicalization/HMAC math the whole time.
    sys.path.insert(0, str(REPO_ROOT / "tools" / "receipt-verify"))
    import checks as real_checks
    from spec_engine.gate_identity import load_or_create_local_identity, read_current_key

    receipt = json.loads((output_dir / "receipt.json").read_text(encoding="utf-8"))
    identity = load_or_create_local_identity(str(output_dir / "identity"))
    key_bytes = read_current_key(identity.key_path)
    trust = {result["approved_by"]: {"fingerprint": identity.fingerprint, "key_bytes": key_bytes}}
    errors = real_checks.verify_receipt(receipt, trust)
    assert errors == [], errors
