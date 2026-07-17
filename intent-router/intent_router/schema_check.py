"""Minimal, dependency-free structural validator.

Deliberately NOT a general JSON Schema engine — it supports exactly the
keyword subset `schema/routing-decision.schema.json` uses: type, required,
properties, additionalProperties, enum, items. This mirrors this repo's
own documented convention (every `core/contracts/*.schema.json` file ends
with a "Minimal-validator keyword subset supported by tessctl validate"
`$comment`) without importing or depending on `.tess/bin/tessctl`'s
internal validator — keeping this component importable and testable on
its own, with no coupling to the framework's keystone-managed engine.
"""

from __future__ import annotations

from typing import Any, Dict, List

_TYPE_MAP: Dict[str, Any] = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "number": (int, float),
    "integer": int,
}


class SchemaValidationError(ValueError):
    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _check(value: Any, schema: Dict[str, Any], path: str, errors: List[str]) -> None:
    if "type" in schema:
        expected = schema["type"]
        types = expected if isinstance(expected, list) else [expected]
        allow_null = "null" in types
        if value is None:
            if not allow_null:
                errors.append(f"{path}: null not allowed")
            return
        py_types = tuple(_TYPE_MAP[t] for t in types if t in _TYPE_MAP)
        # bool is a subclass of int in Python — reject a bool where an
        # integer/number was NOT explicitly requested, so `true` never
        # silently satisfies `{"type": "integer"}`.
        if isinstance(value, bool) and bool not in py_types:
            errors.append(f"{path}: expected type {types}, got bool")
            return
        if py_types and not isinstance(value, py_types):
            errors.append(f"{path}: expected type {types}, got {type(value).__name__}")
            return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in enum {schema['enum']}")

    if isinstance(value, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}: missing required property {req!r}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: unexpected property {key!r}")
        for key, sub_schema in props.items():
            if key in value:
                _check(value[key], sub_schema, f"{path}.{key}", errors)

    if isinstance(value, list) and "items" in schema:
        item_schema = schema["items"]
        for i, item in enumerate(value):
            _check(item, item_schema, f"{path}[{i}]", errors)


def validate(instance: Dict[str, Any], schema: Dict[str, Any]) -> None:
    """Raise `SchemaValidationError` if `instance` does not conform to
    `schema` under the supported keyword subset above. Returns None (does
    not mutate `instance`) on success."""
    errors: List[str] = []
    _check(instance, schema, "$", errors)
    if errors:
        raise SchemaValidationError(errors)
