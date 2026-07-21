"""REQUIRED adversarial proof: an unauthenticated / forged approval is
REJECTED by orchestrator.pipeline.run_pipeline() -- codegen does NOT run
-- not merely that a genuine, authenticated approval passes (see
test_pipeline.py for the positive path). Tests both:

  1. A gate whose request_approval() hands back a forged Approval (built
     the exact way the epic names -- a bare spec_engine.approval.
     record_approval(approved_by="Xavier") call, no signature at all).
     Its verify() is the REAL LocalIdentityApprovalGate.verify(), so this
     also proves the real verification logic, not a test double, is what
     catches it.

  2. A gate whose request_approval() returns a genuinely-signed approval
     that gets tampered with in transit (simulating a compromised
     adapter/transport) before the pipeline's own independent verify()
     call sees it.

In every case: run_pipeline() raises ApprovalAuthenticationError,
spec_engine.pipeline.finalize_spec_with_approval() is never called,
spec_engine.codegen.generate_app() is never called, and target_dir is
never created. (This is the orchestrator SEAM's own proof; see
tests/spec_engine/test_spec_builder.py and test_gate_approval.py for the
SAME proof one layer down, at spec_engine.spec_builder.build_spec() --
the actual codegen boundary -- which does not depend on any particular
ApprovalGate having caught the forgery first.)
"""

from __future__ import annotations

import dataclasses

import pytest

import _orchestrator_paths  # noqa: F401 -- sys.path bootstrap
from _orchestrator_paths import EXAMPLE_ROUTING_TABLE

from spec_engine.approval import record_approval
from spec_engine.types import Plan

from orchestrator.adapters.local_identity import LocalIdentityApprovalGate
from orchestrator.approval_gate import ApprovalAuthenticationError, ApprovalGate
import orchestrator.pipeline as pipeline_module

CONFIDENT_INPUT = (
    "I'm seriously considering opening up in a completely new country next year, "
    "is that a smart expansion move for us right now?"
)


class _ForgedApprovalGate(ApprovalGate):
    """Simulates the exact forgery the epic names: request_approval()
    returns an Approval built by directly calling spec_engine.approval.
    record_approval() with an arbitrary approved_by string -- no gate
    authentication happened at all. verify() delegates to a REAL
    LocalIdentityApprovalGate, so a real (not stubbed) verification path
    is what rejects it."""

    def __init__(self, tmp_path):
        self._real_gate = LocalIdentityApprovalGate(identity_dir=tmp_path / "identity")

    def request_approval(self, plan: Plan):
        return record_approval(plan, approved_by="Xavier", approved=True)

    def verify(self, approval, plan) -> bool:
        return self._real_gate.verify(approval, plan)


class _TamperedInTransitGate(ApprovalGate):
    """Simulates a compromised adapter/transport: request_approval()
    genuinely signs a real approval, but something changes approved_by
    before the pipeline's own verify() call ever sees it -- proving
    verify() is checked against what the pipeline ACTUALLY has, not
    trusted as "already checked by request_approval()"."""

    def __init__(self, tmp_path):
        self._real_gate = LocalIdentityApprovalGate(
            identity_dir=tmp_path / "identity",
            confirm_fn=lambda plan, identity: (True, ""),
        )

    def request_approval(self, plan: Plan):
        genuine = self._real_gate.request_approval(plan)
        return dataclasses.replace(genuine, approved_by="Xavier")

    def verify(self, approval, plan) -> bool:
        return self._real_gate.verify(approval, plan)


@pytest.mark.parametrize("gate_cls", [_ForgedApprovalGate, _TamperedInTransitGate])
def test_forged_approval_is_rejected_and_codegen_never_runs(tmp_path, monkeypatch, gate_cls):
    target_dir = tmp_path / "generated-app"
    generate_app_calls = []
    finalize_spec_calls = []

    def _spy_generate_app(*args, **kwargs):
        generate_app_calls.append((args, kwargs))

    def _spy_finalize_spec(*args, **kwargs):
        finalize_spec_calls.append((args, kwargs))

    monkeypatch.setattr(pipeline_module, "generate_app", _spy_generate_app)
    monkeypatch.setattr(pipeline_module, "finalize_spec_with_approval", _spy_finalize_spec)

    gate = gate_cls(tmp_path)
    with pytest.raises(ApprovalAuthenticationError):
        pipeline_module.run_pipeline(
            CONFIDENT_INPUT,
            EXAMPLE_ROUTING_TABLE,
            gate,
            target_dir=target_dir,
            route_log_path=False,
            spec_log_path=False,
        )

    assert generate_app_calls == []
    assert finalize_spec_calls == []
    assert not target_dir.exists()


def test_forged_approval_rejection_is_independent_of_the_forged_approved_flag(tmp_path):
    """A forged approval claiming approved=False must be rejected exactly
    the same way as one claiming approved=True -- verification happens
    BEFORE the approved/rejected branch is even inspected, so a forger
    cannot dodge the check by picking either value."""
    plan_holder = {}

    class _CapturingForgedGate(_ForgedApprovalGate):
        def request_approval(self, plan: Plan):
            plan_holder["plan"] = plan
            return record_approval(plan, approved_by="Xavier", approved=False)

    gate = _CapturingForgedGate(tmp_path)
    with pytest.raises(ApprovalAuthenticationError):
        pipeline_module.run_pipeline(
            CONFIDENT_INPUT,
            EXAMPLE_ROUTING_TABLE,
            gate,
            target_dir=tmp_path / "generated-app",
            route_log_path=False,
            spec_log_path=False,
        )
    assert not (tmp_path / "generated-app").exists()


def test_a_genuinely_authenticated_approval_from_a_different_local_identity_scope_is_still_rejected(tmp_path):
    """Sanity check that verify() scoping (identity_dir) actually matters:
    an approval signed by one LocalIdentityApprovalGate instance must not
    verify against a DIFFERENT instance's key (simulating a gate
    misconfiguration where request_approval and verify silently point at
    different identities)."""

    class _MismatchedScopeGate(ApprovalGate):
        def __init__(self, tmp_path):
            self._signer = LocalIdentityApprovalGate(
                identity_dir=tmp_path / "signer-identity",
                confirm_fn=lambda plan, identity: (True, ""),
            )
            self._verifier = LocalIdentityApprovalGate(identity_dir=tmp_path / "verifier-identity")

        def request_approval(self, plan: Plan):
            return self._signer.request_approval(plan)

        def verify(self, approval, plan) -> bool:
            return self._verifier.verify(approval, plan)

    target_dir = tmp_path / "generated-app"
    with pytest.raises(ApprovalAuthenticationError):
        pipeline_module.run_pipeline(
            CONFIDENT_INPUT,
            EXAMPLE_ROUTING_TABLE,
            _MismatchedScopeGate(tmp_path),
            target_dir=target_dir,
            route_log_path=False,
            spec_log_path=False,
        )
    assert not target_dir.exists()
