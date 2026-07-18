"""End-to-end tests for orchestrator.pipeline.run_pipeline() -- the wired
spine: intent-router -> spec-engine intake/plan -> authenticated approval
gate -> spec-engine finalize -> codegen. Uses the real example routing
table (this repo's own 26 commands + 6 orchestrators), a real
LocalIdentityApprovalGate (scoped to tmp_path), and asserts on real files
written by spec_engine.codegen.generate_app()."""

from __future__ import annotations

import json

import pytest

import _orchestrator_paths  # noqa: F401 -- sys.path bootstrap
from _orchestrator_paths import EXAMPLE_ROUTING_TABLE

from orchestrator.adapters.local_identity import LocalIdentityApprovalGate
from orchestrator.pipeline import run_pipeline

CONFIDENT_INPUT = (
    "I'm seriously considering opening up in a completely new country next year, "
    "is that a smart expansion move for us right now?"
)
AMBIGUOUS_INPUT = "hello"


def _gate(tmp_path, *, approved=True):
    return LocalIdentityApprovalGate(
        identity_dir=tmp_path / "identity",
        confirm_fn=lambda plan, identity: (approved, ""),
    )


def test_run_pipeline_generates_a_real_app_end_to_end(tmp_path):
    target_dir = tmp_path / "generated-app"
    result = run_pipeline(
        CONFIDENT_INPUT,
        EXAMPLE_ROUTING_TABLE,
        _gate(tmp_path),
        target_dir=target_dir,
        route_log_path=False,
        spec_log_path=False,
    )

    assert result.status == "generated"
    assert result.decision is not None and result.decision.ambiguous is False
    assert result.plan is not None
    assert result.approval is not None and result.approval.approved is True
    assert result.spec is not None
    assert result.spec.provenance.approved_by.startswith("local:")
    assert result.spec.provenance.routing_decision_id == result.decision.decision_id
    assert result.codegen is not None

    # Real files, not just a claim -- mirrors the discipline
    # tests/spec_engine/test_codegen_app_boots.py already applies to
    # spec_engine.codegen itself.
    assert (target_dir / "SPEC.md").is_file()
    assert (target_dir / "src" / "server.js").is_file()
    manifest_path = target_dir / ".spec-engine" / "codegen-manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["spec_id"] == result.spec.spec_id
    assert manifest["codegen_status"] == "generated"


def test_run_pipeline_carries_routing_provenance_through_to_the_spec(tmp_path):
    result = run_pipeline(
        "We need a small internal tool that tracks vendor invoices and flags overdue ones.",
        EXAMPLE_ROUTING_TABLE,
        _gate(tmp_path),
        target_dir=tmp_path / "generated-app",
        route_log_path=False,
        spec_log_path=False,
    )
    assert result.status == "generated"
    assert result.spec.provenance.entry_command == result.decision.entry_command
    assert result.spec.provenance.orchestrator == result.decision.orchestrator


def test_run_pipeline_stops_honestly_on_ambiguous_input_with_no_clarification(tmp_path):
    result = run_pipeline(
        AMBIGUOUS_INPUT,
        EXAMPLE_ROUTING_TABLE,
        _gate(tmp_path),
        target_dir=tmp_path / "generated-app",
        route_log_path=False,
        spec_log_path=False,
    )
    assert result.status == "needs_clarification"
    assert result.clarifying_question is not None
    assert result.plan is None
    assert result.spec is None
    assert not (tmp_path / "generated-app").exists()


def test_run_pipeline_resolves_ambiguity_when_a_clarification_is_supplied(tmp_path):
    result = run_pipeline(
        AMBIGUOUS_INPUT,
        EXAMPLE_ROUTING_TABLE,
        _gate(tmp_path),
        target_dir=tmp_path / "generated-app",
        clarification_answer="I want to build a small internal tool for tracking tasks.",
        route_log_path=False,
        spec_log_path=False,
    )
    assert result.status in ("generated", "rejected")
    assert result.decision.ambiguous is False


def test_run_pipeline_on_rejection_builds_no_spec_and_runs_no_codegen(tmp_path):
    target_dir = tmp_path / "generated-app"
    result = run_pipeline(
        CONFIDENT_INPUT,
        EXAMPLE_ROUTING_TABLE,
        _gate(tmp_path, approved=False),
        target_dir=target_dir,
        route_log_path=False,
        spec_log_path=False,
    )
    assert result.status == "rejected"
    assert result.spec is None
    assert result.codegen is None
    assert not target_dir.exists()


def test_run_pipeline_force_route_never_asks_a_clarifying_question(tmp_path):
    result = run_pipeline(
        AMBIGUOUS_INPUT,
        EXAMPLE_ROUTING_TABLE,
        _gate(tmp_path),
        target_dir=tmp_path / "generated-app",
        force_route=True,
        route_log_path=False,
        spec_log_path=False,
    )
    assert result.status != "needs_clarification"
    assert result.decision.ambiguous is False
