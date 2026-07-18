"""Minimal, dependency-free structural validator — telemetry's own copy.

Deliberately NOT a general JSON Schema engine — it supports exactly the
keyword subset `schema/telemetry-event.schema.json` uses: type, required,
properties, additionalProperties, enum, pattern. This is a
byte-for-byte-in-spirit copy of `intent_router.schema_check` /
`spec_engine.spec_check` (see those modules' own docstrings for the full
rationale) — deliberately DUPLICATED, not imported, so this component
keeps zero import dependency on any sibling top-level component and stays
independently deployable (the same discipline `spec_engine.content.
utc_now_iso()` documents for itself: "Duplicated here (not imported) so
spec-engine has zero import dependency on intent-router").

`pattern` ([Cyra LOW-1]) is checked with `re.search` (not `re.fullmatch`)
against string values only — every pattern this schema actually declares
(`event_id`/`install_id`/`timestamp`) is itself `^...$`-anchored, so
`search` and `fullmatch` are equivalent for THIS schema; `search` is used
because it is the one behavior every other keyword here (`enum`,
`additionalProperties`) already assumes zero surprises for a schema that
declares no pattern at all (an absent `pattern` key never blocks
anything, exactly like an absent `enum` key today).
"""

from __future__ import annotations

import re
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
        # bool is a subclass of int in Python -- reject a bool where an
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

    if "pattern" in schema and isinstance(value, str) and re.search(schema["pattern"], value) is None:
        errors.append(f"{path}: {value!r} does not match pattern {schema['pattern']!r}")

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


def validate(instance: Dict[str, Any], schema: Dict[str, Any]) -> None:
    """Raise `SchemaValidationError` if `instance` does not conform to
    `schema` under the supported keyword subset above. Returns None (does
    not mutate `instance`) on success."""
    errors: List[str] = []
    _check(instance, schema, "$", errors)
    if errors:
        raise SchemaValidationError(errors)
