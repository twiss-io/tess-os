"""Intake harvesting — the deterministic half of "rambling in, governed
source-of-truth spec out" (Epic E2 goal, verbatim).

This module NEVER calls a model and NEVER blocks on incomplete input.
Given ANY non-empty freeform text — a voice-note transcript, a pasted doc,
a single-paragraph fragment — `harvest_intake()` always returns a complete
`IntakeHarvest`: every one of the four core dimensions (what it does / how
it looks / how it works / data model) is either populated from a real
signal in the text, or explicitly captured as an open question in the
ledger. There is no third outcome where a dimension is silently left
blank with no record of the gap — that would be exactly the "demanding a
finished brief" failure mode Pillar 02 rejects.

Two harvesting passes, run BEFORE any optional model-assisted blend, then
gap-detection runs AFTER the blend (so a model-assisted supplement that
genuinely fills a gap suppresses the corresponding "not specified" open
question instead of leaving a stale, contradictory one in the ledger):

  1. **Bucket classification** — each sentence is scored against three
     keyword vocabularies (looks / works / data-ish) using the same
     phrase-matching technique intent_router.classifier uses for routing
     (deliberately consistent style across this repo's two "freeform text
     in, structured decision out" components). Sentences that don't
     clearly match a bucket fall through to "what it does" — the default
     assumption for undifferentiated prose.
  2. **Ambiguity/hedge detection** — any sentence containing a hedge
     phrase ("not sure", "maybe", "TBD", a bare "?", ...) is harvested
     directly into the open-questions ledger, verbatim, regardless of
     which bucket it also landed in. This is the literal mechanism for
     "rough edges are inputs, not blockers."

Data-model entities are deliberately NEVER *fabricated* from prose —
inventing a plausible-looking schema from a sentence that only vaguely
gestures at "tracking something" would be confabulation, not harvesting.
The one exception is literal, unambiguous parsing: an explicit
`<Name> entity (field, field, field)` declaration (exactly the shape a
detailed brief tends to state — see eval/fixtures/brief_detailed.txt) is
parsed verbatim, because every name in it came directly from the author's
own text, nothing is invented. Anything short of that explicit shape stays
an open question rather than a guess. `ModelAssistedHarvest` is the same
purely-additive, optional hook contract `intent_router.types.ExternalSignal`
uses for routing, so the deterministic path stays independently
unit-testable with no model call required to test it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .content import (
    DataModel,
    Entity,
    HowItLooks,
    HowItWorks,
    KeyFlow,
    KeyScreen,
    OpenQuestion,
    SpecEngineError,
    WhatItDoes,
    new_id,
)
from .entity_extraction import extract_entities
from .model_assisted import ModelAssistedHarvest
from .types import SOURCE_TYPES

__all__ = ["IntakeHarvest", "ModelAssistedHarvest", "harvest_intake"]

MAX_AMBIGUITY_QUESTIONS = 10

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")

LOOKS_KEYWORDS = (
    "look", "looks", "ui", "design", "screen", "page", "color", "colour",
    "layout", "style", "visual", "interface", "theme", "font", "logo",
    "brand", "mockup", "wireframe",
)
WORKS_KEYWORDS = (
    "flow", "api", "backend", "workflow", "process", "trigger", "integrat",
    "sync", "automat", "logic", "rule", "server", "notify", "notification",
    "schedule", "webhook", "when the user", "engine",
)
DATA_KEYWORDS = (
    "database", "table", "field", "store", "record", "entity", "schema",
    "column", "track", "invoice", "customer record", "profile", "list of",
)
HEDGE_PHRASES = (
    "not sure", "maybe", "i think", "tbd", "to be decided", "figure out",
    "not certain", "unclear", "undecided", "possibly", "i guess",
    "kind of", "sort of", "we'll see", "haven't decided", "not 100%",
    "no idea", "not entirely sure", "still deciding",
)
NON_GOAL_PHRASES = (
    "not going to", "won't", "out of scope", "not for v1", "no plans to",
    "not included", "not building", "skipping",
)
ACCEPTANCE_PHRASES = (
    "should be able to", "must be able to", "needs to be able to",
    "success looks like", "done when", "has to be able to",
)

@dataclass
class IntakeHarvest:
    """What one `harvest_intake()` call produces: draft content for each
    core dimension plus the open-questions ledger. `plan_builder.build_plan`
    is the only consumer — this is an internal staging shape, not a public
    contract with its own JSON schema (Plan is the first contract-bearing
    stage)."""

    source_type: str
    input_text: str
    what_it_does: WhatItDoes
    how_it_looks: HowItLooks
    how_it_works: HowItWorks
    data_model: DataModel
    non_goals: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    open_questions: List[OpenQuestion] = field(default_factory=list)


def _split_sentences(text: str) -> List[str]:
    parts = _SENTENCE_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def _contains_any(sentence_lower: str, phrases) -> bool:
    return any(p in sentence_lower for p in phrases)


def _open_question(question: str, category: str, raised_from: str, *, blocking: bool = False) -> OpenQuestion:
    return OpenQuestion(
        id=new_id("oq"),
        question=question,
        category=category,
        raised_from=raised_from[:200],
        blocking=blocking,
    )


def harvest_intake(
    input_text: str,
    source_type: str,
    *,
    model_assisted: Optional[ModelAssistedHarvest] = None,
) -> IntakeHarvest:
    """Harvest `input_text` into an `IntakeHarvest`. Raises `SpecEngineError`
    only on structurally invalid arguments (empty input, unknown
    source_type) — never because the content itself is thin, rough, or
    ambiguous. That is the whole point of this module."""
    if not input_text or not input_text.strip():
        raise SpecEngineError("harvest_intake() requires non-empty input_text — nothing to harvest from")
    if source_type not in SOURCE_TYPES:
        raise SpecEngineError(f"harvest_intake() source_type {source_type!r} must be one of {SOURCE_TYPES}")

    sentences = _split_sentences(input_text)
    what_bucket: List[str] = []
    looks_bucket: List[str] = []
    works_bucket: List[str] = []
    data_bucket: List[str] = []
    non_goals: List[str] = []
    acceptance: List[str] = []
    open_questions: List[OpenQuestion] = []

    for sentence in sentences:
        low = sentence.lower()
        if _contains_any(low, HEDGE_PHRASES) or "?" in sentence:
            if len(open_questions) < MAX_AMBIGUITY_QUESTIONS:
                open_questions.append(
                    _open_question(f"Resolve ambiguity in: {sentence.strip()!r}", "ambiguity", sentence)
                )
        if _contains_any(low, NON_GOAL_PHRASES):
            non_goals.append(sentence)
        if _contains_any(low, ACCEPTANCE_PHRASES):
            acceptance.append(sentence)

        is_looks = _contains_any(low, LOOKS_KEYWORDS)
        is_works = _contains_any(low, WORKS_KEYWORDS)
        is_data = _contains_any(low, DATA_KEYWORDS)
        if is_looks:
            looks_bucket.append(sentence)
        if is_works:
            works_bucket.append(sentence)
        if is_data:
            data_bucket.append(sentence)
        if not (is_looks or is_works or is_data):
            what_bucket.append(sentence)

    # what_it_does always has SOME content: the bucket if anything landed
    # there, else the raw input's own first sentence — never empty, since
    # every non-empty input is at minimum a description of itself.
    summary = " ".join(what_bucket) if what_bucket else sentences[0]
    user_stories = [s for s in sentences if re.search(r"\bas an?\b.+\bi want\b", s, re.IGNORECASE)]
    goals: List[str] = []

    looks_description = " ".join(looks_bucket)
    works_description = " ".join(works_bucket)
    data_signal_text = " ".join(data_bucket)
    key_screens: List[KeyScreen] = []
    key_flows: List[KeyFlow] = []
    integrations: List[str] = []
    design_references: List[str] = []
    entities: List[Entity] = extract_entities(sentences)  # literal parse only — see module docstring

    # --- blend in the optional model-assisted supplement BEFORE deciding
    # which gaps still need an open question (purely additive: fills
    # empty slots, unions onto populated ones, never deletes a heuristic
    # finding). ---
    if model_assisted is not None:
        if model_assisted.what_it_does_summary:
            summary = (
                f"{summary} {model_assisted.what_it_does_summary}".strip()
                if summary
                else model_assisted.what_it_does_summary
            )
        goals = list(model_assisted.goals)
        user_stories = user_stories + [s for s in model_assisted.user_stories if s not in user_stories]
        looks_description = looks_description or (model_assisted.how_it_looks_description or "")
        key_screens = list(model_assisted.key_screens)
        design_references = list(model_assisted.design_references)
        works_description = works_description or (model_assisted.how_it_works_description or "")
        key_flows = list(model_assisted.key_flows)
        integrations = list(model_assisted.integrations)
        existing_entity_names = {e.name for e in entities}
        entities = entities + [e for e in model_assisted.entities if e.name not in existing_entity_names]
        non_goals = non_goals + [g for g in model_assisted.non_goals if g not in non_goals]
        acceptance = acceptance + [a for a in model_assisted.acceptance_criteria if a not in acceptance]

    # --- gap detection runs LAST, against the fully blended state. ---
    if not looks_description:
        open_questions.append(
            _open_question(
                "Visual design / UI direction was not specified in the intake input — what should this look like?",
                "design",
                "no signal found for how-it-looks",
            )
        )
    if not works_description:
        open_questions.append(
            _open_question(
                "How the app technically operates (flows, integrations, automation) was not specified — "
                "how should it work under the hood?",
                "technical",
                "no signal found for how-it-works",
            )
        )
    if not entities:
        open_questions.append(
            _open_question(
                "Data model not specified — what entities/fields does this app need to persist?"
                if data_signal_text
                else "No data-related signal found in the intake input at all — does this app need to persist any data?",
                "data",
                data_signal_text or "no signal found for data model",
            )
        )
    if not acceptance:
        open_questions.append(
            _open_question(
                "No acceptance criteria were stated — how will 'done' be verified for this app?",
                "scope",
                "no acceptance-criteria phrasing found in the intake input",
            )
        )

    if model_assisted is not None:
        open_questions = open_questions + list(model_assisted.additional_open_questions)

    return IntakeHarvest(
        source_type=source_type,
        input_text=input_text,
        what_it_does=WhatItDoes(summary=summary, goals=goals, user_stories=user_stories),
        how_it_looks=HowItLooks(
            description=looks_description, key_screens=key_screens, design_references=design_references
        ),
        how_it_works=HowItWorks(description=works_description, key_flows=key_flows, integrations=integrations),
        data_model=DataModel(entities=entities),
        non_goals=non_goals,
        acceptance_criteria=acceptance,
        open_questions=open_questions,
    )
