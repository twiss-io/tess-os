"""Tests for spec_engine.spec_check (the minimal validator) AND that
spec.schema.json / plan.schema.json / scaffold-plan.schema.json each
correctly validate a real produced instance and correctly reject a
tampered one."""

from __future__ import annotations

import copy
import json

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap
from _spec_engine_paths import SCHEMA_DIR

from spec_engine.gate_approval import sign_local_approval
from spec_engine.intake import harvest_intake
from spec_engine.plan_builder import build_plan
from spec_engine.scaffold import plan_scaffold_from_spec
from spec_engine.spec_builder import build_spec
from spec_engine.spec_check import SchemaValidationError, validate


def _load_schema(name):
    with (SCHEMA_DIR / name).open("r", encoding="utf-8") as f:
        return json.load(f)


def _built_spec():
    plan = build_plan(harvest_intake("An app that tracks invoices.", "fragment"))
    approval = sign_local_approval(plan, approved_by="Xavier")
    return plan, build_spec(plan, approval)


def test_minimal_validator_type_mismatch():
    with pytest.raises(SchemaValidationError):
        validate({"a": "not an int"}, {"type": "object", "properties": {"a": {"type": "integer"}}})


def test_minimal_validator_rejects_bool_for_integer_type():
    with pytest.raises(SchemaValidationError):
        validate({"a": True}, {"type": "object", "properties": {"a": {"type": "integer"}}})


def test_minimal_validator_additional_properties_false():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": False}
    with pytest.raises(SchemaValidationError):
        validate({"a": "ok", "b": "unexpected"}, schema)


def test_real_plan_record_validates_against_plan_schema():
    plan, _ = _built_spec()
    validate(plan.to_log_record(), _load_schema("plan.schema.json"))


def test_real_spec_record_validates_against_spec_schema():
    _, spec = _built_spec()
    validate(spec.to_log_record(), _load_schema("spec.schema.json"))


def test_real_scaffold_plan_validates_against_scaffold_plan_schema():
    _, spec = _built_spec()
    sp = plan_scaffold_from_spec(spec)
    validate(sp.to_log_record(), _load_schema("scaffold-plan.schema.json"))


def test_spec_schema_rejects_missing_required_field():
    _, spec = _built_spec()
    record = spec.to_log_record()
    del record["provenance"]
    with pytest.raises(SchemaValidationError):
        validate(record, _load_schema("spec.schema.json"))


def test_spec_schema_rejects_bad_status_enum():
    _, spec = _built_spec()
    record = copy.deepcopy(spec.to_log_record())
    record["status"] = "not-a-real-status"
    with pytest.raises(SchemaValidationError):
        validate(record, _load_schema("spec.schema.json"))


def test_spec_schema_rejects_undeclared_property():
    _, spec = _built_spec()
    record = copy.deepcopy(spec.to_log_record())
    record["unexpected_field"] = "should never validate"
    with pytest.raises(SchemaValidationError):
        validate(record, _load_schema("spec.schema.json"))
