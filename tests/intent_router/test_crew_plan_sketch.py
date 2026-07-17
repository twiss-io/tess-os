"""Tests for intent_router.crew_plan_sketch, INCLUDING a live drift check
against this repo's own core/contracts/crew-plan.schema.json — the sketch
must only ever use outcome_type / gate_in values the real, authoritative
schema currently defines, so a future change to that schema's vocabulary
is caught here rather than silently diverging."""

from __future__ import annotations

import json
from pathlib import Path

import _paths  # noqa: F401 -- sys.path bootstrap, see _paths.py docstring
from _paths import example_routing_table  # noqa: F401 -- pytest fixture, used by parameter name

from intent_router import Route
from intent_router.crew_plan_sketch import build_sketch
from intent_router.types import GATES, OUTCOME_TYPES

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CREW_PLAN_SCHEMA_PATH = REPO_ROOT / "core" / "contracts" / "crew-plan.schema.json"


def test_sketch_carries_is_sketch_true_and_expansion_notice():
    route = Route(id="a", entry_command="/a", outcome_type="build", orchestrator="product-delivery-orchestrator")
    sketch = build_sketch(route, mission_id="2026-07-17-test")
    assert sketch["is_sketch"] is True
    assert "expansion_required" in sketch
    assert "SKETCH" in sketch["expansion_required"]


def test_sketch_uses_the_gate_named_intake_before_anything():
    route = Route(id="a", entry_command="/a", outcome_type="build")
    sketch = build_sketch(route, mission_id="m")
    assert sketch["stages"][0]["gate_in"] == "intake-before-anything"


def test_sketch_falls_back_to_a_single_owner_task_when_no_default_guilds():
    route = Route(id="a", entry_command="/a", outcome_type="build", orchestrator="some-orchestrator")
    sketch = build_sketch(route, mission_id="m")
    tasks = sketch["stages"][0]["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["role"] == "Owner"
    assert tasks[0]["candidate_agent"] == "some-orchestrator"
    assert tasks[0]["needs_brief"] is True


def test_sketch_expands_default_guilds_with_first_as_owner():
    route = Route(
        id="a",
        entry_command="/a",
        outcome_type="build",
        default_guilds=["product-guild", "coding-team"],
    )
    sketch = build_sketch(route, mission_id="m")
    tasks = sketch["stages"][0]["tasks"]
    assert [t["candidate_agent"] for t in tasks] == ["product-guild", "coding-team"]
    assert tasks[0]["role"] == "Owner"
    assert tasks[1]["role"] == "Core Contributor"
    assert all(t["needs_brief"] for t in tasks)


def test_sketch_outcome_owner_prefers_orchestrator_over_entry_command():
    route = Route(id="a", entry_command="/a", outcome_type="build", orchestrator="orch-x")
    sketch = build_sketch(route, mission_id="m")
    assert sketch["outcome_owner"] == "orch-x"


def test_sketch_outcome_owner_falls_back_to_entry_command_when_no_orchestrator():
    route = Route(id="a", entry_command="/a", outcome_type="build")
    sketch = build_sketch(route, mission_id="m")
    assert sketch["outcome_owner"] == "/a"


def test_local_outcome_types_constant_matches_the_live_crew_plan_schema():
    """Drift check: intent_router.types.OUTCOME_TYPES must stay byte-identical
    to core/contracts/crew-plan.schema.json's own outcome_type enum. If this
    fails, the schema changed and this component's copy needs updating —
    that is the point of this test."""
    if not CREW_PLAN_SCHEMA_PATH.is_file():
        import pytest

        pytest.skip("core/contracts/crew-plan.schema.json not present in this checkout")
    schema = json.loads(CREW_PLAN_SCHEMA_PATH.read_text(encoding="utf-8"))
    live_enum = schema["properties"]["crew_plan"]["properties"]["outcome_type"]["enum"]
    assert tuple(live_enum) == OUTCOME_TYPES


def test_local_gates_constant_matches_the_live_crew_plan_schema():
    if not CREW_PLAN_SCHEMA_PATH.is_file():
        import pytest

        pytest.skip("core/contracts/crew-plan.schema.json not present in this checkout")
    schema = json.loads(CREW_PLAN_SCHEMA_PATH.read_text(encoding="utf-8"))
    live_enum = schema["$defs"]["Stage"]["properties"]["gate_in"]["enum"]
    assert tuple(live_enum) == GATES


def test_every_example_routing_table_outcome_type_is_a_real_gate_vocabulary_member(
    example_routing_table,
):
    for r in example_routing_table:
        assert r.outcome_type in OUTCOME_TYPES


def test_sketch_built_from_every_example_route_only_uses_real_gate_and_outcome_vocabulary(
    example_routing_table,
):
    for r in example_routing_table:
        sketch = build_sketch(r, mission_id="m")
        assert sketch["outcome_type"] in OUTCOME_TYPES
        for stage in sketch["stages"]:
            assert stage["gate_in"] in GATES
