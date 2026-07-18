"""The 3-brief eval — Epic E2's acceptance criterion, made runnable and
CI-checked (same role tests/intent_router/test_routing_eval.py plays for
Epic E1's 40-case eval).

"Three real briefs (one detailed, one voice-ramble, one single-paragraph
idea) each produce a spec that a DIFFERENT agent pool can build from
without asking the original author anything not already in the
open-questions ledger."

See spec-engine/eval/spec_engine_eval.py's module docstring for the honest
data-source note (hand-authored, representative fixtures — not real
historical user briefs).
"""

from __future__ import annotations

import json

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap
from _spec_engine_paths import EVAL_FIXTURES_DIR, SCHEMA_DIR

from spec_engine.pipeline import run_spec_engine
from spec_engine.render import render_markdown
from spec_engine.spec_check import validate

CASES = [
    ("detailed", "brief_detailed.txt", "structured_brief"),
    ("voice_ramble", "brief_voice_ramble.txt", "voice_transcript"),
    ("single_paragraph", "brief_single_paragraph.txt", "fragment"),
]

REQUIRED_MD_HEADERS = [
    "## What It Does", "## How It Looks", "## How It Works", "## Data Model",
    "## Non-Goals", "## Acceptance Criteria", "## Open Questions Ledger", "## Provenance",
]


def _unaccounted_gaps(spec):
    gaps = []
    oq_categories = {q.category for q in spec.open_questions}
    if not spec.what_it_does.summary.strip():
        gaps.append("what_it_does")
    if not spec.how_it_looks.description.strip() and not spec.how_it_looks.key_screens and "design" not in oq_categories:
        gaps.append("how_it_looks")
    if not spec.how_it_works.description.strip() and not spec.how_it_works.key_flows and "technical" not in oq_categories:
        gaps.append("how_it_works")
    if not spec.data_model.entities and "data" not in oq_categories:
        gaps.append("data_model")
    if not spec.acceptance_criteria and "scope" not in oq_categories:
        gaps.append("acceptance_criteria")
    return gaps


@pytest.fixture(scope="module")
def spec_schema():
    with (SCHEMA_DIR / "spec.schema.json").open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("name,filename,source_type", CASES, ids=[c[0] for c in CASES])
def test_each_brief_produces_a_schema_valid_spec_with_no_unaccounted_gaps(name, filename, source_type, spec_schema):
    text = (EVAL_FIXTURES_DIR / filename).read_text(encoding="utf-8")
    spec = run_spec_engine(text, source_type, approved_by="eval-harness", log_path=False)

    validate(spec.to_log_record(), spec_schema)  # raises on any schema violation

    gaps = _unaccounted_gaps(spec)
    assert not gaps, f"{name}: unaccounted-for gaps not captured by an open question: {gaps}"

    md = render_markdown(spec)
    missing = [h for h in REQUIRED_MD_HEADERS if h not in md]
    assert not missing, f"{name}: rendered SPEC.md is missing headers: {missing}"


def test_detailed_brief_needs_far_fewer_open_questions_than_the_voice_ramble():
    """A fully-specified brief should harvest markedly less ambiguity than
    a rambling, hedge-heavy one — a sanity check that the harvesting
    heuristics are actually responsive to how complete the input is,
    not a fixed count regardless of input quality."""
    detailed_text = (EVAL_FIXTURES_DIR / "brief_detailed.txt").read_text(encoding="utf-8")
    ramble_text = (EVAL_FIXTURES_DIR / "brief_voice_ramble.txt").read_text(encoding="utf-8")

    detailed_spec = run_spec_engine(detailed_text, "structured_brief", approved_by="eval-harness", log_path=False)
    ramble_spec = run_spec_engine(ramble_text, "voice_transcript", approved_by="eval-harness", log_path=False)

    assert len(detailed_spec.open_questions) < len(ramble_spec.open_questions)


def test_all_three_briefs_produce_distinct_spec_ids():
    specs = []
    for _, filename, source_type in CASES:
        text = (EVAL_FIXTURES_DIR / filename).read_text(encoding="utf-8")
        specs.append(run_spec_engine(text, source_type, approved_by="eval-harness", log_path=False))
    assert len({s.spec_id for s in specs}) == 3
