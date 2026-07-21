"""Tests for spec_engine.content: OpenQuestion validation, slug helper,
id/timestamp helpers."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from dataclasses import asdict

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.connector_resolver import resolve_connectors
from spec_engine.content import (
    DataModel,
    HowItLooks,
    HowItWorks,
    OpenQuestion,
    SpecEngineError,
    WhatItDoes,
    is_valid_slug,
    new_id,
    plan_content_hash,
    utc_now_iso,
)
from spec_engine.types import Plan


def test_is_valid_slug_accepts_safe_slugs():
    assert is_valid_slug("plan-abc123")
    assert is_valid_slug("a")
    assert is_valid_slug("a.b_c-d9")


@pytest.mark.parametrize("bad", ["", "Abc", "-abc", "a/b", "a\\b", "a b", "../etc/passwd"])
def test_is_valid_slug_rejects_unsafe_values(bad):
    assert not is_valid_slug(bad)


def test_new_id_is_a_safe_slug_with_the_given_prefix():
    the_id = new_id("plan")
    assert the_id.startswith("plan-")
    assert is_valid_slug(the_id)


def test_utc_now_iso_shape():
    ts = utc_now_iso()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", ts)


def test_open_question_valid_construction():
    oq = OpenQuestion(id="oq-1", question="What color?", category="design", raised_from="no signal")
    assert oq.blocking is False
    assert oq.status == "open"
    assert oq.resolution is None


def test_open_question_rejects_bad_id():
    with pytest.raises(SpecEngineError):
        OpenQuestion(id="Not Safe!", question="q", category="design", raised_from="x")


def test_open_question_rejects_empty_question():
    with pytest.raises(SpecEngineError):
        OpenQuestion(id="oq-1", question="   ", category="design", raised_from="x")


def test_open_question_rejects_bad_category():
    with pytest.raises(SpecEngineError):
        OpenQuestion(id="oq-1", question="q", category="not-a-real-category", raised_from="x")


def test_open_question_rejects_bad_status():
    with pytest.raises(SpecEngineError):
        OpenQuestion(id="oq-1", question="q", category="design", raised_from="x", status="pending")


# ---------------------------------------------------------------------------
# Regression lock — PR #84 fix-up round (Reid HIGH, NO-MERGE blocker).
#
# `plan_content_hash()` originally added a `"resolved_connectors"` key to
# its hashed payload UNCONDITIONALLY, even for a plan with zero
# integrations. That silently changed the hash for every pre-Connectors-v1
# plan/approval, breaking `gate_approval.verify_gate_approval()` for any
# approval signed on `main` before this feature — even one for a plan that
# never touched a connector. The fix makes the payload addition truly
# ADDITIVE: the key is present only when `plan.resolved_connectors` is
# non-empty. These two tests lock BOTH halves of that guarantee and will
# fail loud if either regresses.
# ---------------------------------------------------------------------------


def _zero_integration_plan() -> Plan:
    """Deterministic, fully-defaulted content — every field a fixed,
    reproducible value so the resulting hash is a stable constant, not a
    per-run random value (plan_id/created_at are NOT hashed by
    plan_content_hash(), so they're free to be any valid value here)."""
    return Plan(
        plan_id="plan-deadbeef0001",
        mission_id=None,
        created_at="2026-01-01T00:00:00.000Z",
        source_type="fragment",
        input_excerpt="",
        what_it_does=WhatItDoes(),
        how_it_looks=HowItLooks(),
        how_it_works=HowItWorks(),
        data_model=DataModel(),
    )


def test_plan_content_hash_zero_integration_plan_matches_pre_connectors_v1_shape():
    """A zero-integration plan's hash must equal the hash produced by the
    PRE-#84 payload shape (main@88f0d7c1's `plan_content_hash()` body,
    reproduced verbatim below as an independent historical baseline —
    deliberately NOT re-derived from the current implementation, so this
    test cannot pass merely because the current code and this assertion
    drifted together). The hardcoded digest is a REAL value independently
    verified by running main@88f0d7c1's actual `plan_content_hash()`
    against this exact plan content (see PR #84 fix-up disclosure)."""
    plan = _zero_integration_plan()
    assert plan.resolved_connectors == []

    pre_84_payload = {
        "source_type": plan.source_type,
        "input_excerpt": plan.input_excerpt,
        "what_it_does": asdict(plan.what_it_does),
        "how_it_looks": asdict(plan.how_it_looks),
        "how_it_works": asdict(plan.how_it_works),
        "data_model": asdict(plan.data_model),
        "non_goals": list(plan.non_goals),
        "acceptance_criteria": list(plan.acceptance_criteria),
        "open_questions": [asdict(q) for q in plan.open_questions],
    }
    pre_84_canonical = json.dumps(pre_84_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    pre_84_hash = hashlib.sha256(pre_84_canonical).hexdigest()

    # Independently verified against a real run of main@88f0d7c1 for this
    # exact plan content — pins the byte-for-byte claim to a concrete value,
    # not just "same code path as the payload above".
    assert pre_84_hash == "67c9a8409fba8bd35075d57b66b8aa4ebe7f2a42450255ebd2ed483f0efc448f"
    assert plan_content_hash(plan) == pre_84_hash

    # Fails loud if anyone re-adds "resolved_connectors" to the payload
    # unconditionally: a zero-integration plan's hash would then diverge
    # from this pinned pre-#84 baseline again.
    assert "resolved_connectors" not in pre_84_payload


def test_plan_content_hash_connector_bearing_plan_still_binds_the_surface():
    """The other half of the guarantee: a plan that DOES resolve at least
    one connector must still get that surface bound into the hash — the
    key is included whenever the list is non-empty (binding preserved, not
    accidentally dropped by the backward-compat fix). Isolates the ONE
    variable that matters (`resolved_connectors` populated vs. forced back
    to `[]`) by holding every other field — including `how_it_works.
    integrations` itself — fixed via `dataclasses.replace`."""
    plan = _zero_integration_plan()
    plan.how_it_works = HowItWorks(integrations=["Anthropic"])
    plan.resolved_connectors = resolve_connectors(["Anthropic"])
    assert plan.resolved_connectors != []

    resolved_hash = plan_content_hash(plan)

    forced_empty = dataclasses.replace(plan, resolved_connectors=[])
    forced_empty_hash = plan_content_hash(forced_empty)

    # Same how_it_works.integrations text on both sides — the ONLY
    # difference is whether resolved_connectors is populated or empty —
    # so a hash difference here can only come from the conditional key,
    # proving the binding survives the additive-only fix.
    assert resolved_hash != forced_empty_hash
