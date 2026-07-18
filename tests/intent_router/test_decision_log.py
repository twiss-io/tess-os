"""Tests for the routing-decision JSONL log, its schema validation, and
intent_router.schema_check's minimal validator."""

from __future__ import annotations

import json

import pytest

import _paths  # noqa: F401 -- sys.path bootstrap, see _paths.py docstring
from _paths import example_routing_table  # noqa: F401 -- pytest fixture, used by parameter name

from intent_router import RoutingDecision, append_decision, read_decisions
from intent_router.router import route
from intent_router.schema_check import SchemaValidationError, validate


def _decision(**overrides):
    defaults = dict(
        decision_id="abc123",
        timestamp="2026-07-17T00:00:00.000Z",
        input_text="build a new feature please, this is a somewhat long input " * 3,
        ambiguous=False,
        route_id="product-mode",
        entry_command="/product-mode",
        orchestrator="product-delivery-orchestrator",
        outcome_type="build",
        confidence=0.7,
        matched_signals=["feature"],
        narration="Routing this to `/product-mode`.",
    )
    defaults.update(overrides)
    return RoutingDecision(**defaults)


def test_append_decision_writes_one_jsonl_line(tmp_path):
    log_path = tmp_path / "decisions" / "log.jsonl"
    decision = _decision()
    append_decision(decision, log_path)
    assert log_path.is_file()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["route_id"] == "product-mode"
    assert record["decision_id"] == "abc123"


def test_append_decision_truncates_input_to_280_chars(tmp_path):
    long_input = "x" * 500
    decision = _decision(input_text=long_input)
    log_path = tmp_path / "log.jsonl"
    append_decision(decision, log_path)
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert len(record["input_excerpt"]) == 280


def test_append_decision_is_additive_across_multiple_calls(tmp_path):
    log_path = tmp_path / "log.jsonl"
    append_decision(_decision(decision_id="one"), log_path)
    append_decision(_decision(decision_id="two"), log_path)
    records = list(read_decisions(log_path))
    assert [r["decision_id"] for r in records] == ["one", "two"]


def test_read_decisions_on_missing_file_yields_nothing(tmp_path):
    assert list(read_decisions(tmp_path / "does-not-exist.jsonl")) == []


def test_a_real_router_decision_round_trips_through_the_log(tmp_path, example_routing_table):
    decision = route(
        "we need to build a new feature and finish the roadmap",
        example_routing_table,
    )
    log_path = tmp_path / "log.jsonl"
    append_decision(decision, log_path)
    records = list(read_decisions(log_path))
    assert len(records) == 1
    assert records[0]["route_id"] == decision.route_id


def test_ambiguous_decision_also_validates_and_logs(tmp_path, example_routing_table):
    decision = route("hello", example_routing_table)
    assert decision.ambiguous is True
    log_path = tmp_path / "log.jsonl"
    append_decision(decision, log_path)
    records = list(read_decisions(log_path))
    assert records[0]["ambiguous"] is True
    assert records[0]["clarifying_question"] is not None


# -- schema_check (minimal validator) direct tests ---------------------------


def test_schema_check_rejects_missing_required_property():
    schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}}
    with pytest.raises(SchemaValidationError):
        validate({}, schema)


def test_schema_check_rejects_additional_property():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": False}
    with pytest.raises(SchemaValidationError):
        validate({"a": "x", "b": "y"}, schema)


def test_schema_check_rejects_wrong_type():
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    with pytest.raises(SchemaValidationError):
        validate({"a": "not an int"}, schema)


def test_schema_check_rejects_bool_where_integer_required():
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    with pytest.raises(SchemaValidationError):
        validate({"a": True}, schema)


def test_schema_check_rejects_value_outside_enum():
    schema = {"type": "object", "properties": {"a": {"type": "string", "enum": ["x", "y"]}}}
    with pytest.raises(SchemaValidationError):
        validate({"a": "z"}, schema)


def test_schema_check_allows_null_when_type_list_includes_null():
    schema = {"type": "object", "properties": {"a": {"type": ["string", "null"]}}}
    validate({"a": None}, schema)  # must not raise


def test_schema_check_validates_items_in_arrays():
    schema = {"type": "object", "properties": {"a": {"type": "array", "items": {"type": "string"}}}}
    with pytest.raises(SchemaValidationError):
        validate({"a": ["ok", 5]}, schema)
    validate({"a": ["ok", "also-ok"]}, schema)  # must not raise
