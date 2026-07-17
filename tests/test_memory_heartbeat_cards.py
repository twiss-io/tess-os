"""Unit tests for scripts/heartbeat/cards.py — card read/write discipline.

All file I/O here happens under pytest's own `tmp_path` fixture — never
against a real git-tracked project — so these tests can never touch a real
remote regardless of what the card-writing code does.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from heartbeat import cards  # noqa: E402

CARD_TEXT = """---
id: demo
title: "Demo Project"
state: ACTIVE
owner: someone
priority: P1
repo: acme/demo
heartbeat:
  cadence: "session-driven"
  last_activity: "2026-01-01T00:00:00Z"
  activity_proof: "seed"
  stall_after: "7 days with no commit"
stall:
  stalled: false
  reason: null
  since: null
next_move: "do the thing"
resume: |
  fresh clone from origin HEAD
gates: []
facts_last_verified: "2026-01-01T00:00:00Z"
---

# Demo Project

Body prose untouched by the writer.
"""


@pytest.fixture
def card_path(tmp_path):
    p = tmp_path / "demo.md"
    p.write_text(CARD_TEXT, encoding="utf-8")
    return p


def test_read_card_parses_required_fields(card_path):
    card = cards.read_card(card_path)
    assert card.slug == "demo"
    assert card.repo == "acme/demo"
    assert card.priority == "P1"
    assert card.is_stalled is False


def test_read_card_missing_frontmatter_raises(tmp_path):
    p = tmp_path / "bad.md"
    p.write_text("# no frontmatter here\n", encoding="utf-8")
    with pytest.raises(cards.CardError):
        cards.read_card(p)


def test_read_card_missing_required_field_raises(tmp_path):
    p = tmp_path / "bad2.md"
    p.write_text("---\nid: x\ntitle: X\n---\nbody\n", encoding="utf-8")
    with pytest.raises(cards.CardError):
        cards.read_card(p)


def test_list_card_paths_excludes_example_and_readme(tmp_path):
    (tmp_path / "real.md").write_text(CARD_TEXT, encoding="utf-8")
    (tmp_path / "EXAMPLE.md").write_text(CARD_TEXT, encoding="utf-8")
    (tmp_path / "README.md").write_text("# not a card\n", encoding="utf-8")
    found = cards.list_card_paths(tmp_path)
    assert [p.name for p in found] == ["real.md"]


def test_apply_updates_only_touches_writable_fields(card_path):
    card = cards.read_card(card_path)
    new_text = cards.apply_updates(card, {
        "heartbeat.last_activity": "2026-02-01T00:00:00Z",
        "stall.stalled": True,
        "stall.reason": "attention-shift",
    })
    assert 'last_activity: "2026-02-01T00:00:00Z"' in new_text
    assert "stalled: true" in new_text
    assert "reason: attention-shift" in new_text
    # Body prose byte-for-byte untouched.
    assert "Body prose untouched by the writer." in new_text
    # Untouched fields still present verbatim.
    assert 'next_move: "do the thing"' in new_text


def test_apply_updates_rejects_non_whitelisted_field(card_path):
    card = cards.read_card(card_path)
    with pytest.raises(cards.CardError):
        cards.apply_updates(card, {"next_move": "sneaky overwrite"})


def test_apply_updates_null_value_renders_bare(card_path):
    card = cards.read_card(card_path)
    new_text = cards.apply_updates(card, {"stall.reason": None})
    assert "reason: null" in new_text


def test_replace_scalar_line_hard_stops_on_zero_matches(card_path):
    card = cards.read_card(card_path)
    # heartbeat.stall_after is not writable, but even if it were, simulate
    # a schema-drift scenario: no matching line for a bogus key.
    with pytest.raises(cards.CardError):
        cards._replace_scalar_line(card.raw_frontmatter, "nonexistent_key", "x")


def test_replace_scalar_line_hard_stops_on_duplicate_matches():
    text = "reason: foo\nreason: bar\n"
    with pytest.raises(cards.CardError):
        cards._replace_scalar_line(text, "reason", "baz")
