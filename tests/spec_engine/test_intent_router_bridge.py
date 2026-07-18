"""End-to-end proof of how the spec engine composes with the front door
(Epic E2 dependency: "E1 (intake routes to it)"): a real
`intent_router.route()` call feeds a real `spec_engine` pipeline run, with
the routing decision's identity carried all the way through to the
finished spec's provenance.

This is the ONE test file that imports both `intent_router` and
`spec_engine` together — everywhere else, spec_engine has zero import
dependency on intent_router (see integrations/from_intent_router.py's
module docstring). If this test file is skipped (e.g. `intent-router/` is
not present in a given checkout), the rest of the spec-engine suite is
unaffected — the two components are independently deployable."""

from __future__ import annotations

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap
from _spec_engine_paths import INTENT_ROUTER_ROOT

pytest.importorskip("intent_router")
if not INTENT_ROUTER_ROOT.is_dir():
    pytest.skip("intent-router/ not present in this checkout", allow_module_level=True)

from intent_router.routing_table import RoutingTable
from intent_router.router import route

from spec_engine.integrations.from_intent_router import routing_context_from_decision
from spec_engine.pipeline import finalize_spec, run_intake_and_plan

EXAMPLE_TABLE_PATH = INTENT_ROUTER_ROOT / "routing_table.example.yaml"


@pytest.fixture()
def routed_decision():
    table = RoutingTable.load(EXAMPLE_TABLE_PATH)
    return route(
        "We need to build a new internal tool and I want the engineering team's take on the architecture.",
        table,
        force=True,
    )


def test_routing_context_from_decision_carries_every_field(routed_decision):
    rc = routing_context_from_decision(routed_decision)
    assert rc.decision_id == routed_decision.decision_id
    assert rc.mission_id == routed_decision.mission_id
    assert rc.entry_command == routed_decision.entry_command
    assert rc.orchestrator == routed_decision.orchestrator
    assert rc.outcome_type == routed_decision.outcome_type


def test_a_routed_build_decision_flows_through_to_a_finished_specs_provenance(routed_decision):
    assert routed_decision.route_id == "product-mode"  # sanity: this input should route to product-mode
    rc = routing_context_from_decision(routed_decision)

    plan = run_intake_and_plan(
        "We need a small internal tool that tracks vendor invoices and flags overdue ones.",
        "fragment",
        mission_id=routed_decision.mission_id,
        routing_context=rc,
        log_path=False,
    )
    spec = finalize_spec(plan, approved_by="Xavier", log_path=False)

    assert spec is not None
    assert spec.provenance.routing_decision_id == routed_decision.decision_id
    assert spec.provenance.entry_command == "/product-mode"
    assert spec.provenance.orchestrator == "product-delivery-orchestrator"
    assert spec.provenance.mission_id == routed_decision.mission_id


def test_an_ambiguous_routing_decision_can_still_be_resolved_before_reaching_the_spec_engine():
    """If intent-router itself is ambiguous, that is resolved WITHIN
    intent-router (its own one-clarifying-question contract) before a
    RoutingContext is ever built — spec_engine never has to handle an
    in-flight ambiguous decision itself."""
    from intent_router.pipeline import continue_with_clarification
    from intent_router.router import route as _route

    table = RoutingTable.load(EXAMPLE_TABLE_PATH)
    decision = _route("something is happening and I'm not sure what to do", table)
    if decision.ambiguous:
        decision = continue_with_clarification(decision, "It's a build/architecture question.", EXAMPLE_TABLE_PATH, log_path=False)
    assert decision.ambiguous is False

    rc = routing_context_from_decision(decision)
    plan = run_intake_and_plan("A vague idea I want turned into something concrete.", "fragment", routing_context=rc, log_path=False)
    assert plan.routing_context.decision_id == decision.decision_id
