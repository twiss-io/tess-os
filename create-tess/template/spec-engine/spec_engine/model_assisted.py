"""`ModelAssistedHarvest` — the optional, purely-additive hook a caller
with a real model-assisted read of the input (e.g. a live Claude Code
session forming its own judgment about an idea) can supply to
`intake.harvest_intake()`.

Same contract shape as `intent_router.types.ExternalSignal`: NEVER
required (`harvest_intake()` is fully deterministic and unit-testable
without one), and purely additive — every field either fills a gap the
heuristic pass left open, or is unioned onto whatever the heuristic pass
already found. It can never REMOVE a heuristic finding — see
intake.py's blending logic for exactly how each field is folded in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .content import Entity, KeyFlow, KeyScreen, OpenQuestion


@dataclass(frozen=True)
class ModelAssistedHarvest:
    what_it_does_summary: Optional[str] = None
    goals: List[str] = field(default_factory=list)
    user_stories: List[str] = field(default_factory=list)
    how_it_looks_description: Optional[str] = None
    key_screens: List[KeyScreen] = field(default_factory=list)
    design_references: List[str] = field(default_factory=list)
    how_it_works_description: Optional[str] = None
    key_flows: List[KeyFlow] = field(default_factory=list)
    integrations: List[str] = field(default_factory=list)
    entities: List[Entity] = field(default_factory=list)
    non_goals: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    additional_open_questions: List[OpenQuestion] = field(default_factory=list)
