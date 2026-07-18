"""Tests for intent_router.routing_table / intent_router.types.Route."""

from __future__ import annotations

import pytest

import _paths  # noqa: F401 -- sys.path bootstrap, see _paths.py docstring
from _paths import example_routing_table  # noqa: F401 -- pytest fixture, used by parameter name

from intent_router import Route, RoutingTable, RoutingTableError
from intent_router.types import IntentRouterError


def test_example_table_loads_and_has_26_routes(example_routing_table):
    assert len(example_routing_table) == 26


def test_example_table_route_ids_are_unique(example_routing_table):
    ids = [r.id for r in example_routing_table]
    assert len(ids) == len(set(ids))


def test_get_returns_the_named_route(example_routing_table):
    route = example_routing_table.get("founder-mode")
    assert route.entry_command == "/founder-mode"
    assert route.orchestrator == "founders-office-orchestrator"
    assert route.outcome_type == "decide"


def test_get_raises_on_unknown_id(example_routing_table):
    with pytest.raises(RoutingTableError):
        example_routing_table.get("does-not-exist")


def test_missing_file_fails_loud(tmp_path):
    with pytest.raises(RoutingTableError):
        RoutingTable.load(tmp_path / "nope.yaml")


def test_malformed_table_missing_routes_key_fails_loud(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("not_routes: []\n", encoding="utf-8")
    with pytest.raises(RoutingTableError):
        RoutingTable.load(p)


def test_route_missing_required_field_fails_loud(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        "routes:\n  - id: x\n    entry_command: \"/x\"\n",  # missing outcome_type
        encoding="utf-8",
    )
    with pytest.raises(RoutingTableError):
        RoutingTable.load(p)


def test_duplicate_route_id_fails_loud():
    r1 = Route(id="a", entry_command="/a", outcome_type="decide")
    r2 = Route(id="a", entry_command="/a-again", outcome_type="build")
    with pytest.raises(RoutingTableError):
        RoutingTable([r1, r2])


def test_route_rejects_unsafe_slug_id():
    with pytest.raises(IntentRouterError):
        Route(id="../../etc/passwd", entry_command="/x", outcome_type="decide")


def test_route_rejects_invalid_outcome_type():
    with pytest.raises(IntentRouterError):
        Route(id="a", entry_command="/a", outcome_type="not-a-real-type")


def test_route_rejects_empty_entry_command():
    with pytest.raises(IntentRouterError):
        Route(id="a", entry_command="", outcome_type="decide")


def test_empty_table_rejected():
    with pytest.raises(RoutingTableError):
        RoutingTable([])
