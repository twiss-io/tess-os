"""Tests for spec_engine.render — the SPEC.md markdown projection."""

from __future__ import annotations

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.approval import record_approval
from spec_engine.intake import harvest_intake
from spec_engine.plan_builder import build_plan
from spec_engine.render import render_markdown
from spec_engine.spec_builder import build_spec

REQUIRED_HEADERS = [
    "## What It Does",
    "## How It Looks",
    "## How It Works",
    "## Data Model",
    "## Non-Goals",
    "## Acceptance Criteria",
    "## Open Questions Ledger",
    "## Provenance",
]


def _spec(text="An app that tracks invoices, approved by design.", source="fragment"):
    plan = build_plan(harvest_intake(text, source))
    approval = record_approval(plan, approved_by="Xavier")
    return build_spec(plan, approval)


def test_render_markdown_includes_every_required_section_header():
    spec = _spec()
    md = render_markdown(spec)
    for header in REQUIRED_HEADERS:
        assert header in md


def test_render_markdown_includes_the_spec_is_authoritative_directive():
    spec = _spec()
    md = render_markdown(spec)
    assert "CODE IS GENERATED FROM THIS SPEC" in md


def test_render_markdown_is_deterministic():
    spec = _spec()
    assert render_markdown(spec) == render_markdown(spec)


def test_render_markdown_open_questions_table_lists_every_question():
    spec = _spec("A vague idea, not sure what it should look like.", "voice_transcript")
    md = render_markdown(spec)
    for q in spec.open_questions:
        assert q.id in md


def test_render_markdown_data_model_section_lists_entities_and_fields():
    text = "The data model needs a Widget entity (name, price)."
    spec = _spec(text, "structured_brief")
    md = render_markdown(spec)
    assert "### Widget" in md
    assert "`name`" in md
    assert "`price`" in md
