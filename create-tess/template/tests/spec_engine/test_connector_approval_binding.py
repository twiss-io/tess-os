"""MANDATORY adversarial/repro test (c): approval-hash binding for the
resolved connector surface.

  "after a spec's integrations resolve, mutating the resolved connector
  surface (swap connector, bump version, change side-effect class)
  changes plan_content_hash so a prior approval is REJECTED at
  build_spec — prove codegen does not run under a stale approval."

Same pattern `tests/spec_engine/test_spec_builder.py::
test_content_mutated_in_place_after_approval_is_rejected` already proves
for `plan.what_it_does` — applied here to `plan.resolved_connectors`,
because Connectors v1 binds THAT dimension into
`content.plan_content_hash()` with the exact same mechanism (PR #82's
existing HMAC-signed, content-hash-bound approval gate — no new trust
machinery). Every test here also asserts `spec_engine.codegen.
generate_app()` is never reached and no target directory is ever created,
matching that file's own "prove the rejection happens AT THE CODEGEN
BOUNDARY ITSELF" discipline.
"""

from __future__ import annotations

import dataclasses

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.codegen import generate_app
from spec_engine.connector_resolver import resolve_connectors
from spec_engine.content import DataModel, HowItLooks, HowItWorks, WhatItDoes, new_id, utc_now_iso
from spec_engine.gate_approval import ApprovalVerificationError, sign_local_approval
from spec_engine.spec_builder import build_spec
from spec_engine.types import Plan


def _plan_with_connectors(integration_names=("Anthropic",)):
    return Plan(
        plan_id=new_id("plan"),
        mission_id=None,
        created_at=utc_now_iso(),
        source_type="structured_brief",
        input_excerpt="An AI-powered app",
        what_it_does=WhatItDoes(summary="Calls a model provider."),
        how_it_looks=HowItLooks(),
        how_it_works=HowItWorks(integrations=list(integration_names)),
        data_model=DataModel(),
        summary_for_approval="summary",
        resolved_connectors=resolve_connectors(list(integration_names)),
    )


def _assert_codegen_never_ran(tmp_path):
    target_dir = tmp_path / "would-be-generated-app"
    assert not target_dir.exists()
    return target_dir


# --------------------------------------------------------------------------
# The positive path, first — proves the mechanism is even ENGAGED (a plan
# whose resolved_connectors is genuinely part of what got signed).
# --------------------------------------------------------------------------


def test_resolved_connectors_are_part_of_the_signed_content_hash():
    from spec_engine.content import plan_content_hash

    plan_a = _plan_with_connectors(["Anthropic"])
    plan_b = _plan_with_connectors(["Anthropic"])
    # Same input, same registry -> same hash (sanity: the mechanism is
    # deterministic, not accidentally including a timestamp/nonce).
    assert plan_content_hash(plan_a) == plan_content_hash(plan_b)

    plan_c = dataclasses.replace(plan_a, resolved_connectors=resolve_connectors(["Stripe"]))
    assert plan_content_hash(plan_a) != plan_content_hash(plan_c)


# --------------------------------------------------------------------------
# MANDATORY (c) — three concrete mutations, each of which must invalidate
# an already-signed approval: swap connector, bump version, change
# side-effect class.
# --------------------------------------------------------------------------


def test_swapping_the_resolved_connector_after_approval_is_rejected(tmp_path):
    target_dir = _assert_codegen_never_ran(tmp_path)
    plan = _plan_with_connectors(["Anthropic"])
    approval = sign_local_approval(plan, approved_by="Xavier")

    # Simulates a registry swap between approval and generation: the SAME
    # integration name now resolves to a DIFFERENT connector.
    plan.resolved_connectors = resolve_connectors(["OpenAI"])

    with pytest.raises(ApprovalVerificationError, match="content-hash"):
        build_spec(plan, approval)
    assert not target_dir.exists()


def test_bumping_the_resolved_connector_version_after_approval_is_rejected(tmp_path):
    target_dir = _assert_codegen_never_ran(tmp_path)
    plan = _plan_with_connectors(["Anthropic"])
    approval = sign_local_approval(plan, approved_by="Xavier")

    bumped = dataclasses.replace(plan.resolved_connectors[0], connector_version="9.9.9", manifest_hash="f" * 64)
    plan.resolved_connectors = [bumped]

    with pytest.raises(ApprovalVerificationError, match="content-hash"):
        build_spec(plan, approval)
    assert not target_dir.exists()


def test_changing_a_side_effect_class_after_approval_is_rejected(tmp_path):
    """The specific case the design doc calls out by name (§4.3): approving
    a 'read'-class call and having it silently become 'spend'-class (or
    vice versa) after the fact must be impossible — this is exactly the
    "human approves the exact external-call surface" guarantee."""
    target_dir = _assert_codegen_never_ran(tmp_path)
    plan = _plan_with_connectors(["Anthropic"])
    approval = sign_local_approval(plan, approved_by="Xavier")

    original_op = plan.resolved_connectors[0].operations[0]
    escalated_op = dataclasses.replace(original_op, side_effect="write")
    escalated = dataclasses.replace(plan.resolved_connectors[0], operations=[escalated_op])
    plan.resolved_connectors = [escalated]

    with pytest.raises(ApprovalVerificationError, match="content-hash"):
        build_spec(plan, approval)
    assert not target_dir.exists()


def test_adding_a_previously_unresolved_connector_after_approval_is_rejected(tmp_path):
    """A plan approved with 'Stripe' unresolved (a 501 stub) must not be
    allowed to silently become a real, spend-class Anthropic call after
    the fact (e.g. because the registry gained an entry between approval
    and generation) — the approved surface is frozen at sign time."""
    target_dir = _assert_codegen_never_ran(tmp_path)
    plan = _plan_with_connectors(["Stripe"])
    assert plan.resolved_connectors[0].status == "unresolved"
    approval = sign_local_approval(plan, approved_by="Xavier")

    plan.how_it_works = dataclasses.replace(plan.how_it_works, integrations=["Anthropic"])
    plan.resolved_connectors = resolve_connectors(["Anthropic"])

    with pytest.raises(ApprovalVerificationError, match="content-hash"):
        build_spec(plan, approval)
    assert not target_dir.exists()


# --------------------------------------------------------------------------
# Explicit proof that generate_app() itself is never reached under a
# rejected approval — spying on the REAL function, same as
# test_spec_builder.py::test_generate_app_is_never_reached_when_build_spec_rejects.
# --------------------------------------------------------------------------


def test_generate_app_is_never_reached_under_a_stale_connector_approval(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("spec_engine.codegen.generate_app", lambda *a, **kw: calls.append((a, kw)))
    import spec_engine.codegen as codegen_module  # re-import to get the patched symbol

    target_dir = tmp_path / "would-be-generated-app"
    plan = _plan_with_connectors(["Anthropic"])
    approval = sign_local_approval(plan, approved_by="Xavier")
    plan.resolved_connectors = resolve_connectors(["OpenAI"])  # swapped post-approval

    with pytest.raises(ApprovalVerificationError):
        spec = build_spec(plan, approval)  # raises here -- next line never runs
        codegen_module.generate_app(spec, target_dir)  # pragma: no cover

    assert calls == []
    assert not target_dir.exists()


def test_unmutated_resolved_connectors_approval_still_succeeds_and_generates(tmp_path):
    """Sanity/control: the mechanism only fires on an ACTUAL mutation —
    an honest, unmutated approval for a resolved connector still crosses
    the gate and generate_app() still produces a real client."""
    plan = _plan_with_connectors(["Anthropic"])
    approval = sign_local_approval(plan, approved_by="Xavier")
    spec = build_spec(plan, approval)  # must NOT raise
    result = generate_app(spec, tmp_path)
    assert (tmp_path / "src" / "integrations" / "anthropic.js").is_file()
    module = next(m for m in result.manifest["modules"] if m["kind"] == "integration")
    assert module["generation_status"] == "generated-connector"
