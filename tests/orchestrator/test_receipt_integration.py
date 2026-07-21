"""Integration proof: orchestrator.pipeline.run_pipeline()'s Agent Receipt
hook (Hop 7 -- see that module's own docstring, and
`orchestrator/mission_receipt.py`) emits a genuinely verifiable,
`decision_kind: "local_approval"` Agent Receipt at the exact right
lifecycle point -- ONLY when a caller supplies `receipt_path`, and NEVER
on a rejection. Uses the REAL run_pipeline() end to end -- real
LocalIdentityApprovalGate, the real example intent-router routing table,
real spec-engine codegen -- the same fixtures
tests/orchestrator/test_orchestrator_pipeline.py and
test_telemetry_integration.py already use for their own positive-path
proofs.

The receipt this hop produces is independently re-verified here with
`tools/receipt-verify/checks.py` -- the SAME standalone verifier a real
third party would run -- not just asserted to be "some dict with the
right keys." This is the "propose -> approve -> app-boots -> show me the
receipt" loop becoming something you can actually run.
"""

from __future__ import annotations

import json
import sys

import _orchestrator_paths  # noqa: F401 -- sys.path bootstrap
from _orchestrator_paths import EXAMPLE_ROUTING_TABLE, REPO_ROOT

from orchestrator.adapters.local_identity import LocalIdentityApprovalGate
from orchestrator.pipeline import run_pipeline

# tess-os #162 (Reid MEDIUM): `orchestrator/__init__.py` no longer puts
# `tools/receipt-verify/` on `sys.path` as a side effect of `import
# orchestrator` (see that module's own docstring — the process-wide
# insertion of a flat, generically-named module directory was itself the
# bug this issue fixed). This test wants the real, standalone `checks.py`
# to independently re-verify a receipt, so it does its own narrow,
# explicit, test-scoped sys.path insertion here instead — mirroring
# `examples/receipt-demo/demo_receipts.py`'s own established pattern for
# this exact directory.
sys.path.insert(0, str(REPO_ROOT / "tools" / "receipt-verify"))
import checks  # noqa: E402

CONFIDENT_INPUT = (
    "I'm seriously considering opening up in a completely new country next year, "
    "is that a smart expansion move for us right now?"
)


def _gate(tmp_path, *, approved=True):
    return LocalIdentityApprovalGate(
        identity_dir=tmp_path / "identity",
        confirm_fn=lambda plan, identity: (approved, ""),
    )


def _real_trust_for(gate: LocalIdentityApprovalGate, identity_str: str) -> dict:
    """{approved_by: {"fingerprint", "key_bytes"}} built from the REAL
    local approval-identity key this gate actually signed with -- the
    same key material `checks.py`'s `local_approval` verification path
    requires (see tools/receipt-verify/hmac_verify.py's own trust-level
    disclosure: this is the SECRET key, not a public one)."""
    key_bytes = gate.identity.key_path.read_bytes()
    return {identity_str: {"fingerprint": gate.identity.fingerprint, "key_bytes": key_bytes}}


def test_receipt_path_not_given_run_pipeline_emits_no_receipt(tmp_path):
    result = run_pipeline(
        CONFIDENT_INPUT, EXAMPLE_ROUTING_TABLE, _gate(tmp_path),
        target_dir=tmp_path / "generated-app",
        route_log_path=False, spec_log_path=False,
    )
    assert result.status == "generated"
    assert result.receipt is None
    assert not (tmp_path / "receipt.json").exists()


def test_receipt_path_given_run_pipeline_emits_a_verifiable_local_approval_receipt(tmp_path):
    gate = _gate(tmp_path)
    receipt_path = tmp_path / "receipt.json"
    result = run_pipeline(
        CONFIDENT_INPUT, EXAMPLE_ROUTING_TABLE, gate,
        target_dir=tmp_path / "generated-app",
        route_log_path=False, spec_log_path=False,
        receipt_path=receipt_path,
    )
    assert result.status == "generated"
    assert result.receipt is not None
    assert result.receipt["decision_kind"] == "local_approval"
    assert result.receipt["receipt_signature"]["algorithm"] == "local-hmac-sha256-v1"
    assert result.receipt["decision"]["approval_id"] == result.approval.approval_id
    assert result.receipt["policy_decision"]["rule_kind"] == "pipeline_approval_gate"

    # Really written to disk, not just returned in memory.
    on_disk = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert on_disk == result.receipt

    # Independently, genuinely re-verifiable -- the real standalone
    # verifier, the real local key this gate signed with, zero errors.
    trust = _real_trust_for(gate, result.approval.approved_by)
    assert checks.verify_receipt(result.receipt, trust) == []


def test_wrong_key_receipt_fails_independent_verification(tmp_path):
    """A receipt genuinely emitted by one install must NOT verify against
    an unrelated local key -- proves the receipt is bound to THIS
    install's real key material, not merely well-formed."""
    gate = _gate(tmp_path)
    receipt_path = tmp_path / "receipt.json"
    result = run_pipeline(
        CONFIDENT_INPUT, EXAMPLE_ROUTING_TABLE, gate,
        target_dir=tmp_path / "generated-app",
        route_log_path=False, spec_log_path=False,
        receipt_path=receipt_path,
    )
    assert result.status == "generated"

    other_gate = LocalIdentityApprovalGate(identity_dir=tmp_path / "other-identity")
    wrong_trust = {
        result.approval.approved_by: {
            "fingerprint": gate.identity.fingerprint,
            "key_bytes": other_gate.identity.key_path.read_bytes(),
        },
    }
    errors = checks.verify_receipt(result.receipt, wrong_trust)
    assert errors, "a receipt must never verify against a different install's key"


def test_rejected_mission_never_emits_a_receipt_even_when_receipt_path_given(tmp_path):
    result = run_pipeline(
        CONFIDENT_INPUT, EXAMPLE_ROUTING_TABLE, _gate(tmp_path, approved=False),
        target_dir=tmp_path / "generated-app",
        route_log_path=False, spec_log_path=False,
        receipt_path=tmp_path / "receipt.json",
    )
    assert result.status == "rejected"
    # receipt is populated ONLY on "generated" -- a rejection never built
    # a spec or ran codegen, so there is nothing this hop could honestly
    # attach a "generated a running app" receipt to.
    assert result.receipt is None
    assert not (tmp_path / "receipt.json").exists()


def test_receipt_emission_failure_never_un_completes_a_finished_mission(tmp_path, capsys):
    """An optional receipt failing must NEVER un-complete a finished
    mission (Rule Zero of this hop, mirroring Hop 6's own precedent) --
    point `receipt_path` at a location that cannot possibly be created
    (a path through an existing regular file) and prove the mission
    itself still completes end to end, with the failure downgraded to a
    non-fatal warning."""
    unwritable_parent = tmp_path / "not-a-directory"
    unwritable_parent.write_text("i am a file, not a directory", encoding="utf-8")
    bogus_receipt_path = unwritable_parent / "receipt.json"

    result = run_pipeline(
        CONFIDENT_INPUT, EXAMPLE_ROUTING_TABLE, _gate(tmp_path),
        target_dir=tmp_path / "generated-app",
        route_log_path=False, spec_log_path=False,
        receipt_path=bogus_receipt_path,
    )

    # The governed mission itself -- approval, finalized spec, generated
    # app -- is completely unaffected by the receipt-emission failure.
    assert result.status == "generated"
    assert result.codegen is not None
    assert (tmp_path / "generated-app").exists()

    assert result.receipt is None
    captured = capsys.readouterr()
    assert "WARNING: agent receipt not emitted (non-fatal)" in captured.err
