"""Literal data-model entity parsing — the ONE exception to intake.py's
"never fabricate a data model from prose" rule.

Parses explicit `<Name> entity (field, field, field)` declarations, plus
any `<Child> belongs to <Parent>` sentence linking two already-declared
entities, into `Entity` objects. This is verbatim parsing of structure the
author already wrote — every name that ends up in the result came
directly from the input text, nothing is invented or inferred. Returns
`[]` if no such literal declaration exists; this module never guesses at
a schema from vaguer language ("we probably need to track some records
somewhere" yields nothing here — see spec-engine/eval/fixtures/
brief_voice_ramble.txt for exactly that case, and
tests/spec_engine/test_intake.py's
`test_harvest_never_fabricates_entities_from_vague_data_language`).

Kept as its own module (split out of intake.py) because it is a genuinely
separate concern from the heuristic bucket-classification/hedge-detection
passes: this is deterministic *structural* parsing, not signal scoring.
"""

from __future__ import annotations

import re
from typing import Dict, List

from .content import Entity, EntityField

_ENTITY_DECLARATION_RE = re.compile(r"\b([A-Z][A-Za-z]*)\s+entity\s*\(([^)]+)\)")
_BELONGS_TO_RE = re.compile(
    r"\b([A-Z][A-Za-z]*)\s+belongs\s+to\s+(?:exactly\s+one\s+|one\s+|many\s+)?([A-Z][A-Za-z]*)",
    re.IGNORECASE,
)


def extract_entities(sentences: List[str]) -> List[Entity]:
    """Parse `sentences` for literal entity declarations. Order of
    returned entities follows first-declaration order in the input."""
    entities: Dict[str, Entity] = {}
    for sentence in sentences:
        for match in _ENTITY_DECLARATION_RE.finditer(sentence):
            name = match.group(1)
            field_names = [f.strip() for f in match.group(2).split(",") if f.strip()]
            entities[name] = Entity(name=name, fields=[EntityField(name=f) for f in field_names])
    if entities:
        for sentence in sentences:
            for match in _BELONGS_TO_RE.finditer(sentence):
                child, parent = match.group(1), match.group(2)
                if child in entities and parent in entities:
                    e = entities[child]
                    entities[child] = Entity(
                        name=e.name, fields=e.fields, relationships=list(e.relationships) + [f"belongs to {parent}"]
                    )
    return list(entities.values())
