"""Tests for spec_engine.types, INCLUDING a live drift check against this
repo's own core/contracts/crew-plan.schema.json — mirrors
tests/intent_router/test_crew_plan_sketch.py's drift-detection discipline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.content import DataModel, HowItLooks, HowItWorks, SpecEngineError, WhatItDoes
from spec_engine.types import (
    Approval,
    Plan,
    Provenance,
    ROUTING_OUTCOME_TYPES,
    RoutingContext,
    ScaffoldModule,
    ScaffoldPlan,
    SpecDocument,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CREW_PLAN_SCHEMA_PATH = REPO_ROOT / "core" / "contracts" / "crew-plan.schema.json"


def _content():
    return dict(
        what_it_does=WhatItDoes(summary="does a thing"),
        how_it_looks=HowItLooks(description="looks clean"),
        how_it_works=HowItWorks(description="works simply"),
        data_model=DataModel(entities=[]),
    )


def test_routing_context_accepts_none_outcome_type():
    RoutingContext()  # all defaults None — must not raise


def test_routing_context_rejects_bad_outcome_type():
    with pytest.raises(SpecEngineError):
        RoutingContext(outcome_type="not-a-real-outcome")


def test_local_routing_outcome_types_matches_the_live_crew_plan_schema():
    """Drift check: spec_engine.types.ROUTING_OUTCOME_TYPES must stay
    byte-identical to core/contracts/crew-plan.schema.json's own
    outcome_type enum (the same one intent_router.types.OUTCOME_TYPES
    mirrors) — one vocabulary, not two."""
    if not CREW_PLAN_SCHEMA_PATH.is_file():
        pytest.skip("core/contracts/crew-plan.schema.json not present in this checkout")
    schema = json.loads(CREW_PLAN_SCHEMA_PATH.read_text(encoding="utf-8"))
    live_enum = schema["properties"]["crew_plan"]["properties"]["outcome_type"]["enum"]
    assert tuple(live_enum) == ROUTING_OUTCOME_TYPES


def test_provenance_requires_non_empty_approved_by():
    with pytest.raises(SpecEngineError):
        Provenance(
            source_type="fragment",
            input_excerpt="x",
            approved_by="",
            approved_at="2026-01-01T00:00:00.000Z",
            generated_at="2026-01-01T00:00:00.000Z",
            plan_id="plan-1",
        )


def test_provenance_rejects_bad_source_type():
    with pytest.raises(SpecEngineError):
        Provenance(
            source_type="telepathy",
            input_excerpt="x",
            approved_by="Xavier",
            approved_at="2026-01-01T00:00:00.000Z",
            generated_at="2026-01-01T00:00:00.000Z",
            plan_id="plan-1",
        )


def test_plan_rejects_unsafe_plan_id():
    with pytest.raises(SpecEngineError):
        Plan(
            plan_id="not safe!",
            mission_id=None,
            created_at="2026-01-01T00:00:00.000Z",
            source_type="fragment",
            input_excerpt="x",
            **_content(),
        )


def test_plan_to_log_record_includes_open_question_count():
    plan = Plan(
        plan_id="plan-1",
        mission_id=None,
        created_at="2026-01-01T00:00:00.000Z",
        source_type="fragment",
        input_excerpt="x",
        **_content(),
    )
    record = plan.to_log_record()
    assert record["open_question_count"] == 0


def test_approval_requires_non_empty_approved_by_even_on_rejection():
    with pytest.raises(SpecEngineError):
        Approval(
            approval_id="appr-1",
            plan_id="plan-1",
            approved=False,
            approved_by="",
            approved_at="2026-01-01T00:00:00.000Z",
        )


def test_spec_document_rejects_version_below_one():
    with pytest.raises(SpecEngineError):
        SpecDocument(
            spec_id="spec-1",
            title="Title",
            spec_version=0,
            status="active",
            provenance=Provenance(
                source_type="fragment",
                input_excerpt="x",
                approved_by="Xavier",
                approved_at="2026-01-01T00:00:00.000Z",
                generated_at="2026-01-01T00:00:00.000Z",
                plan_id="plan-1",
            ),
            **_content(),
        )


def test_scaffold_module_rejects_bad_kind():
    with pytest.raises(SpecEngineError):
        ScaffoldModule(module_id="mod-1", source_section="x", kind="not-a-real-kind")


def test_scaffold_plan_pins_codegen_status_not_started():
    sp = ScaffoldPlan(spec_id="spec-1", spec_version=1, generated_at="2026-01-01T00:00:00.000Z")
    assert sp.codegen_status == "not_started"
    with pytest.raises(SpecEngineError):
        ScaffoldPlan(
            spec_id="spec-1", spec_version=1, generated_at="2026-01-01T00:00:00.000Z", codegen_status="done",
        )
