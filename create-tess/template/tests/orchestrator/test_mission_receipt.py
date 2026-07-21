"""orchestrator/mission_receipt.py — direct, low-level unit coverage of
Hop 7's build/write functions in isolation (not through the full
`run_pipeline()` -- that positive-path + lifecycle proof lives in
`tests/orchestrator/test_receipt_integration.py`). Covers the narrow,
typed `MissionReceiptError` failure surface `_emit_governed_mission_receipt()`
relies on to downgrade a receipt failure to a non-fatal warning."""

from __future__ import annotations

import json
import os
import stat
import sys

import _orchestrator_paths  # noqa: F401 -- sys.path bootstrap
from _orchestrator_paths import REPO_ROOT

from orchestrator import mission_receipt
from spec_engine.content import DataModel, HowItLooks, HowItWorks, WhatItDoes, utc_now_iso
from spec_engine.gate_approval import sign_local_approval
from spec_engine.gate_identity import load_or_create_local_identity, read_current_key
from spec_engine.types import Plan, Provenance, SpecDocument

# tess-os #162 (Reid MEDIUM): `orchestrator/__init__.py` no longer puts
# `tools/receipt-verify/` on `sys.path` as a side effect of `import
# orchestrator` (that process-wide insertion of a flat, generically-named
# module directory was itself the bug — see that module's own docstring).
# `mission_receipt.py`'s own `canonical.py` need is now met by a private,
# namespaced `importlib` load instead. This test module still wants the
# real, standalone `checks.py` (to independently re-verify a built
# receipt against the SAME standalone verifier a real third party would
# run), so it does its own narrow, explicit, test-scoped sys.path
# insertion here — mirroring `examples/receipt-demo/demo_receipts.py`'s
# own established pattern for the exact same directory.
sys.path.insert(0, str(REPO_ROOT / "tools" / "receipt-verify"))
import checks  # noqa: E402


def _plan(tmp_path) -> Plan:
    return Plan(
        plan_id="plan-test001",
        mission_id=None,
        created_at=utc_now_iso(),
        source_type="fragment",
        input_excerpt="A test app.",
        what_it_does=WhatItDoes(summary="does stuff"),
        how_it_looks=HowItLooks(),
        how_it_works=HowItWorks(),
        data_model=DataModel(),
    )


def _spec(plan: Plan, approved_by: str) -> SpecDocument:
    return SpecDocument(
        spec_id="spec-test001", title="Test App", spec_version=1, status="active",
        provenance=Provenance(
            source_type="fragment", input_excerpt="x", approved_by=approved_by,
            approved_at=utc_now_iso(), generated_at=utc_now_iso(), plan_id=plan.plan_id,
        ),
        what_it_does=plan.what_it_does, how_it_looks=plan.how_it_looks,
        how_it_works=plan.how_it_works, data_model=plan.data_model,
    )


def test_build_local_approval_receipt_is_independently_verifiable(tmp_path):
    identity_dir = tmp_path / "identity"
    plan = _plan(tmp_path)
    approval = sign_local_approval(plan, approved_by="local:tester#x", approved=True, identity_dir=identity_dir)
    spec = _spec(plan, approval.approved_by)

    receipt = mission_receipt.build_local_approval_receipt(
        plan=plan, approval=approval, spec=spec, target_dir=tmp_path / "generated-app",
        identity_dir=identity_dir,
    )

    assert receipt["receipt_schema"] == "tess-os.agent-receipt/1"
    assert receipt["decision_kind"] == "local_approval"
    assert receipt["decision"] == {
        "approval_id": approval.approval_id, "plan_id": approval.plan_id,
        "approved": approval.approved, "approved_by": approval.approved_by,
        "approved_at": approval.approved_at, "notes": approval.notes,
    }
    assert receipt["policy_decision"]["rule_kind"] == "pipeline_approval_gate"
    assert receipt["chain"] == {"sequence": 0, "prev_receipt_hash": "GENESIS"}
    assert receipt["receipt_signature"]["algorithm"] == "local-hmac-sha256-v1"
    assert receipt["receipt_signature"]["signed_by"] == approval.approved_by

    identity = load_or_create_local_identity(identity_dir)
    key_bytes = read_current_key(identity.key_path)
    trust = {approval.approved_by: {"fingerprint": identity.fingerprint, "key_bytes": key_bytes}}
    assert checks.verify_receipt(receipt, trust) == []


def test_build_local_approval_receipt_raises_on_group_readable_key(tmp_path):
    """gate_identity._enforce_key_permissions refuses a group/world
    readable key file -- build_local_approval_receipt must surface that
    as the narrow, typed MissionReceiptError, not an unhandled
    IdentityError."""
    identity_dir = tmp_path / "identity"
    plan = _plan(tmp_path)
    approval = sign_local_approval(plan, approved_by="local:tester#x", approved=True, identity_dir=identity_dir)
    spec = _spec(plan, approval.approved_by)

    identity = load_or_create_local_identity(identity_dir)
    os.chmod(identity.key_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)  # group-readable, on purpose

    try:
        raised = False
        try:
            mission_receipt.build_local_approval_receipt(
                plan=plan, approval=approval, spec=spec, target_dir=tmp_path / "generated-app",
                identity_dir=identity_dir,
            )
        except mission_receipt.MissionReceiptError:
            raised = True
        assert raised
    finally:
        os.chmod(identity.key_path, stat.S_IRUSR | stat.S_IWUSR)  # restore for cleanup


def test_write_receipt_writes_valid_json_to_disk(tmp_path):
    receipt = {"a": 1, "b": {"c": 2}}
    path = tmp_path / "nested" / "receipt.json"
    result_path = mission_receipt.write_receipt(receipt, path)
    assert result_path == path
    assert json.loads(path.read_text(encoding="utf-8")) == receipt


def test_write_receipt_raises_mission_receipt_error_on_oserror(tmp_path):
    blocking_file = tmp_path / "not-a-dir"
    blocking_file.write_text("x", encoding="utf-8")
    bogus_path = blocking_file / "receipt.json"

    raised = False
    try:
        mission_receipt.write_receipt({"a": 1}, bogus_path)
    except mission_receipt.MissionReceiptError:
        raised = True
    assert raised
