"""Tests for orchestrator.approval_gate.ApprovalGate -- the abstract
contract every adapter (local, future Telegram/web/CLI) implements."""

from __future__ import annotations

import pytest

import _orchestrator_paths  # noqa: F401 -- sys.path bootstrap

from orchestrator.approval_gate import ApprovalAuthenticationError, ApprovalGate


def test_approval_gate_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        ApprovalGate()  # type: ignore[abstract]


def test_a_subclass_missing_verify_cannot_be_instantiated():
    class _MissingVerify(ApprovalGate):
        def request_approval(self, plan):
            raise NotImplementedError

    with pytest.raises(TypeError):
        _MissingVerify()  # type: ignore[abstract]


def test_a_subclass_missing_request_approval_cannot_be_instantiated():
    class _MissingRequestApproval(ApprovalGate):
        def verify(self, approval, plan):
            return False

    with pytest.raises(TypeError):
        _MissingRequestApproval()  # type: ignore[abstract]


def test_a_complete_subclass_can_be_instantiated_and_used():
    class _StubGate(ApprovalGate):
        def request_approval(self, plan):
            return "not-a-real-approval-object-just-checking-the-interface"

        def verify(self, approval, plan):
            return approval == "not-a-real-approval-object-just-checking-the-interface"

    gate = _StubGate()
    approval = gate.request_approval(plan=None)
    assert gate.verify(approval, plan=None) is True


def test_approval_authentication_error_is_a_value_error():
    assert issubclass(ApprovalAuthenticationError, ValueError)
