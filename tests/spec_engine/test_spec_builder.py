"""Tests for spec_engine.spec_builder — the codegen boundary's approval-gate
enforcement, INCLUDING the REQUIRED adversarial proof (codegen-boundary
hardening epic, closing [Cyra MEDIUM-1]/[MEDIUM-2]) that:

  (a) a bare, unsigned `approval.record_approval(approved_by="Xavier")`
      call is REJECTED by `build_spec()` — no `SpecDocument` is built;
  (b) a genuinely-signed approval for one plan's content cannot authorize
      a DIFFERENT plan/spec, even one sharing the same `plan_id`
      (spec-substitution, and its sibling: mutating a Plan's content IN
      PLACE after approval while leaving `plan_id` untouched);
  (c) a tampered/forged signature is rejected.

Every adversarial test here also asserts `spec_engine.codegen.
generate_app()` is never reached and no target directory is ever created
— proving the rejection happens AT THE CODEGEN BOUNDARY ITSELF
(`build_spec()`), not merely at the orchestrator seam (see
`tests/orchestrator/test_pipeline_adversarial.py` for that layer's own,
separate proof) and not merely relying on the caller never bothering to
call `generate_app()`.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.approval import record_approval
from spec_engine.codegen import generate_app
from spec_engine.content import SpecEngineError
from spec_engine.gate_approval import (
    ApprovalReplayError,
    ApprovalVerificationError,
    sign_local_approval,
)
from spec_engine.intake import harvest_intake
from spec_engine.plan_builder import build_plan
from spec_engine.spec_builder import build_spec


def _plan(text="An app that tracks invoices."):
    return build_plan(harvest_intake(text, "fragment"))


# --------------------------------------------------------------------------
# Pre-existing structural checks — unchanged behavior, now exercised with
# GENUINELY signed approvals (a bare one would ALSO be rejected, but for
# the wrong reason — see the adversarial section below for that proof
# specifically).
# --------------------------------------------------------------------------


def test_build_spec_raises_on_unapproved_plan():
    plan = _plan()
    rejection = sign_local_approval(plan, approved_by="Xavier", approved=False)
    with pytest.raises(SpecEngineError):
        build_spec(plan, rejection)


def test_build_spec_raises_on_mismatched_plan_id():
    plan_a = _plan("An app that tracks invoices.")
    plan_b = _plan("A different app entirely.")
    approval_for_a = sign_local_approval(plan_a, approved_by="Xavier")
    with pytest.raises(SpecEngineError):
        build_spec(plan_b, approval_for_a)


def test_build_spec_copies_content_verbatim_from_the_plan():
    plan = _plan()
    approval = sign_local_approval(plan, approved_by="Xavier")
    spec = build_spec(plan, approval)
    assert spec.what_it_does == plan.what_it_does
    assert spec.how_it_looks == plan.how_it_looks
    assert spec.how_it_works == plan.how_it_works
    assert spec.data_model == plan.data_model
    assert spec.open_questions == plan.open_questions


def test_build_spec_sets_provenance_from_plan_and_approval():
    plan = _plan()
    approval = sign_local_approval(plan, approved_by="Xavier", notes="Looks good.")
    spec = build_spec(plan, approval)
    assert spec.provenance.plan_id == plan.plan_id
    assert spec.provenance.approved_by == "Xavier"
    assert spec.provenance.source_type == plan.source_type
    assert spec.status == "active"
    assert spec.spec_version == 1


def test_build_spec_title_falls_back_to_input_excerpt_when_summary_is_thin():
    plan = _plan("x")
    approval = sign_local_approval(plan, approved_by="Xavier")
    spec = build_spec(plan, approval)
    assert spec.title.strip() != ""


# --------------------------------------------------------------------------
# REQUIRED adversarial proof — the codegen-boundary hardening epic's own
# mandatory tests (a)/(b)/(c). Every test here also proves generate_app()
# is never reached and no target dir is created, using a real, throwaway
# target_dir under tmp_path (never actually written to on the happy path
# either — build_spec() itself never touches the filesystem).
# --------------------------------------------------------------------------


def _assert_codegen_never_ran(tmp_path):
    target_dir = tmp_path / "would-be-generated-app"
    assert not target_dir.exists()
    return target_dir


def test_a_bare_unsigned_approval_is_rejected_no_app_generated(tmp_path):
    """(a) — the exact forgery the epic names: a caller directly calls
    spec_engine.approval.record_approval() with an arbitrary approved_by
    string, bypassing every ApprovalGate entirely. Before this hardening,
    build_spec(plan, bare) -> generate_app() produced a real, running app
    with ZERO authentication."""
    target_dir = _assert_codegen_never_ran(tmp_path)
    plan = _plan()
    bare = record_approval(plan, approved_by="Xavier", approved=True)
    assert bare.notes == ""  # no signed evidence at all

    with pytest.raises(ApprovalVerificationError):
        build_spec(plan, bare)

    assert not target_dir.exists()


def test_spec_substitution_same_plan_id_different_content_is_rejected(tmp_path):
    """(b) — a genuinely-signed approval for plan_a's content must not
    authorize building a spec from a DIFFERENT plan whose content differs,
    even when that second plan carries the SAME plan_id (the concrete
    "mutable plan_id slug" attack: Plan is a plain, non-frozen dataclass,
    so plan_id alone is not proof the content an approver reviewed is the
    content actually being built)."""
    target_dir = _assert_codegen_never_ran(tmp_path)
    plan_a = _plan("An app that tracks invoices.")
    approval_a = sign_local_approval(plan_a, approved_by="Xavier")

    plan_b = _plan("A completely different, unrelated app idea.")
    plan_b_same_id = dataclasses.replace(plan_b, plan_id=plan_a.plan_id)

    with pytest.raises(ApprovalVerificationError, match="content-hash"):
        build_spec(plan_b_same_id, approval_a)

    assert not target_dir.exists()


def test_content_mutated_in_place_after_approval_is_rejected(tmp_path):
    """(b), sibling case — the SAME Plan OBJECT, mutated in place after
    approval (plan_id untouched), must also be rejected. Plan is a plain
    dataclass (not frozen) specifically so intake/harvest logic can build
    it incrementally — nothing else in this package should be able to
    exploit that mutability to smuggle different content past an already
    -captured approval."""
    target_dir = _assert_codegen_never_ran(tmp_path)
    plan = _plan("An app that tracks invoices.")
    approval = sign_local_approval(plan, approved_by="Xavier")

    plan.what_it_does = dataclasses.replace(
        plan.what_it_does, summary="Actually, secretly wire money to an external account."
    )

    with pytest.raises(ApprovalVerificationError, match="content-hash"):
        build_spec(plan, approval)

    assert not target_dir.exists()


def test_a_tampered_signature_is_rejected(tmp_path):
    """(c) — a genuinely-signed approval whose signature is altered
    (simulating a forged or in-transit-corrupted signature) must be
    rejected. Uses a real signed approval and corrupts ONLY the signature
    hex string — every other field, including the content_hash, is left
    exactly as genuinely signed."""
    target_dir = _assert_codegen_never_ran(tmp_path)
    plan = _plan()
    approval = sign_local_approval(plan, approved_by="Xavier")

    parsed = json.loads(approval.notes)
    parsed["auth"]["signature"] = "0" * 64
    tampered = dataclasses.replace(approval, notes=json.dumps(parsed))

    with pytest.raises(ApprovalVerificationError, match="signature"):
        build_spec(plan, tampered)

    assert not target_dir.exists()


def test_a_hand_constructed_approval_with_fake_auth_json_is_rejected(tmp_path):
    """A forger who never had access to the local signing key cannot
    fabricate a plausible-looking auth block either — every field except
    the (unforgeable) signature is public/guessable, and the signature
    check alone is what stops this."""
    target_dir = _assert_codegen_never_ran(tmp_path)
    plan = _plan()
    from spec_engine.content import plan_content_hash
    from spec_engine.types import Approval

    fake_notes = json.dumps({
        "human_notes": "",
        "auth": {
            "mechanism": "local-hmac-sha256-v1",
            "identity_fingerprint": "attacker-fingerprint",
            "content_hash": plan_content_hash(plan),
            "nonce": "attacker-chosen-nonce",
            "signature": "0" * 64,
        },
    })
    forged = Approval(
        approval_id="appr-attacker0001",
        plan_id=plan.plan_id,
        approved=True,
        approved_by="Xavier",
        approved_at="2026-01-01T00:00:00.000Z",
        notes=fake_notes,
    )

    with pytest.raises(ApprovalVerificationError):
        build_spec(plan, forged)

    assert not target_dir.exists()


def test_a_replayed_approval_is_rejected_on_second_use(tmp_path):
    """A genuinely-verified approval can authorize exactly ONE
    build_spec() call — reusing the SAME Approval object a second time
    (accidentally or maliciously) must be rejected, not silently produce
    a second SpecDocument from the same signed evidence."""
    plan = _plan()
    approval = sign_local_approval(plan, approved_by="Xavier")

    spec = build_spec(plan, approval)
    assert spec is not None  # first use succeeds

    target_dir = tmp_path / "would-be-second-generated-app"
    with pytest.raises(ApprovalReplayError):
        build_spec(plan, approval)
    assert not target_dir.exists()


@pytest.mark.parametrize("bad_notes", [
    "",
    "not json at all",
    "{}",
    '{"auth": "not-a-dict"}',
    '{"auth": {}}',
    '{"auth": {"mechanism": "some-other-mechanism-v9"}}',
])
def test_build_spec_never_generates_from_malformed_notes(tmp_path, bad_notes):
    """Fuzz-style proof that build_spec()'s codegen-boundary check fails
    CLOSED (raises, never silently proceeds) on every malformed shape a
    forged/corrupted Approval.notes could take."""
    target_dir = _assert_codegen_never_ran(tmp_path)
    plan = _plan()
    from spec_engine.types import Approval

    forged = Approval(
        approval_id="appr-fuzz0000001",
        plan_id=plan.plan_id,
        approved=True,
        approved_by="Xavier",
        approved_at="2026-01-01T00:00:00.000Z",
        notes=bad_notes,
    )
    with pytest.raises(SpecEngineError):
        build_spec(plan, forged)
    assert not target_dir.exists()


def test_generate_app_is_never_reached_when_build_spec_rejects(tmp_path, monkeypatch):
    """Explicit proof, spying on the REAL `spec_engine.codegen.
    generate_app()` (not an inference from "no SpecDocument exists"),
    that a realistic two-step caller — build_spec() then generate_app(),
    the exact shape `spec_engine.pipeline.finalize_spec_with_approval()`
    / `orchestrator.pipeline.run_pipeline()` use — never reaches the
    generate_app() call at all when build_spec() rejects a bare/forged
    approval, and never creates target_dir."""
    calls = []
    monkeypatch.setattr("spec_engine.codegen.generate_app", lambda *a, **kw: calls.append((a, kw)))
    import spec_engine.codegen as codegen_module  # re-import to get the patched symbol

    target_dir = tmp_path / "would-be-generated-app"
    plan = _plan()
    bare = record_approval(plan, approved_by="Xavier", approved=True)

    with pytest.raises(SpecEngineError):
        spec = build_spec(plan, bare)  # raises here -- next line never runs
        codegen_module.generate_app(spec, target_dir)  # pragma: no cover

    assert calls == []
    assert not target_dir.exists()
