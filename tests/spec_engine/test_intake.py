"""Tests for spec_engine.intake — the deterministic harvest pass."""

from __future__ import annotations

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.content import Entity, EntityField, KeyScreen, OpenQuestion, SpecEngineError
from spec_engine.intake import ModelAssistedHarvest, harvest_intake


def test_harvest_rejects_empty_input():
    with pytest.raises(SpecEngineError):
        harvest_intake("   ", "fragment")


def test_harvest_rejects_unknown_source_type():
    with pytest.raises(SpecEngineError):
        harvest_intake("An app that does things.", "telepathy")


def test_harvest_never_blocks_on_a_single_terse_paragraph():
    harvest = harvest_intake("An app that tracks overdue invoices and nudges clients.", "fragment")
    assert harvest.what_it_does.summary.strip() != ""
    assert isinstance(harvest.open_questions, list)


def test_harvest_populates_what_it_does_from_fallback_bucket_when_nothing_else_matches():
    harvest = harvest_intake("A tool that helps people remember birthdays.", "fragment")
    assert "birthdays" in harvest.what_it_does.summary


def test_harvest_gap_detection_raises_open_questions_for_every_missing_dimension():
    harvest = harvest_intake("A tool that helps people remember birthdays.", "fragment")
    categories = {q.category for q in harvest.open_questions}
    assert "design" in categories       # no how-it-looks signal
    assert "technical" in categories    # no how-it-works signal
    assert "data" in categories         # no explicit entity declared
    assert "scope" in categories        # no acceptance-criteria phrasing


def test_harvest_hedge_phrases_are_captured_as_ambiguity_open_questions():
    harvest = harvest_intake("I think it should have categories, but not sure honestly.", "voice_transcript")
    ambiguity_qs = [q for q in harvest.open_questions if q.category == "ambiguity"]
    assert len(ambiguity_qs) >= 1


def test_harvest_looks_bucket_suppresses_the_design_gap_question():
    harvest = harvest_intake(
        "The app should have a clean, minimal visual design with a dark navy color scheme on the main screen.",
        "pasted_doc",
    )
    assert harvest.how_it_looks.description.strip() != ""
    categories = {q.category for q in harvest.open_questions}
    assert "design" not in categories


def test_harvest_works_bucket_suppresses_the_technical_gap_question():
    harvest = harvest_intake(
        "Under the hood, a backend workflow should trigger a webhook integration whenever a new record is created.",
        "pasted_doc",
    )
    assert harvest.how_it_works.description.strip() != ""
    categories = {q.category for q in harvest.open_questions}
    assert "technical" not in categories


def test_harvest_extracts_explicit_entity_declarations_verbatim():
    text = "The data model needs a Teammate entity (name, email, timezone). Each Update belongs to exactly one Teammate."
    harvest = harvest_intake(text, "structured_brief")
    names = {e.name for e in harvest.data_model.entities}
    assert "Teammate" in names
    teammate = next(e for e in harvest.data_model.entities if e.name == "Teammate")
    assert [f.name for f in teammate.fields] == ["name", "email", "timezone"]
    categories = {q.category for q in harvest.open_questions}
    assert "data" not in categories  # entity found -> gap question suppressed


def test_harvest_never_fabricates_entities_from_vague_data_language():
    harvest = harvest_intake("We probably need to track some records somewhere in a database.", "voice_transcript")
    assert harvest.data_model.entities == []
    categories = {q.category for q in harvest.open_questions}
    assert "data" in categories


def test_harvest_non_goal_phrase_detection():
    harvest = harvest_intake(
        "We are not going to build threaded replies in this version. The app posts updates to a feed.",
        "structured_brief",
    )
    assert any("threaded replies" in g for g in harvest.non_goals)


def test_harvest_acceptance_phrase_detection_suppresses_scope_gap():
    harvest = harvest_intake(
        "The app should be able to send a reminder every morning. It also posts updates to a feed.",
        "structured_brief",
    )
    assert harvest.acceptance_criteria
    categories = {q.category for q in harvest.open_questions}
    assert "scope" not in categories


def test_model_assisted_harvest_fills_gaps_and_suppresses_the_corresponding_question():
    supplement = ModelAssistedHarvest(
        how_it_looks_description="A clean two-column layout with a sidebar.",
        key_screens=[KeyScreen(name="Home", description="Main feed")],
        entities=[Entity(name="Item", fields=[EntityField(name="title")])],
        acceptance_criteria=["The item list loads in under a second."],
    )
    harvest = harvest_intake("A tool that helps people remember birthdays.", "fragment", model_assisted=supplement)
    assert harvest.how_it_looks.description == "A clean two-column layout with a sidebar."
    assert harvest.data_model.entities and harvest.data_model.entities[0].name == "Item"
    categories = {q.category for q in harvest.open_questions}
    assert "design" not in categories
    assert "data" not in categories


def test_model_assisted_harvest_never_removes_a_heuristic_finding():
    supplement = ModelAssistedHarvest(non_goals=["Not building push notifications."])
    harvest = harvest_intake(
        "We are not going to build threaded replies in this version.", "structured_brief", model_assisted=supplement,
    )
    assert any("threaded replies" in g for g in harvest.non_goals)
    assert any("push notifications" in g for g in harvest.non_goals)


def test_model_assisted_additional_open_questions_are_appended_verbatim():
    extra = OpenQuestion(id="oq-extra", question="Which payment provider?", category="technical", raised_from="model read")
    supplement = ModelAssistedHarvest(additional_open_questions=[extra])
    harvest = harvest_intake("An app for tracking invoices.", "fragment", model_assisted=supplement)
    assert any(q.id == "oq-extra" for q in harvest.open_questions)
