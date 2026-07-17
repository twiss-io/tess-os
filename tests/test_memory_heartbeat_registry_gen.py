"""Unit tests for scripts/heartbeat/registry_gen.py — regenerating the
auto-generated dashboard tables while preserving hand-authored tail prose.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from heartbeat import cards, registry_gen  # noqa: E402

NOW = datetime(2026, 1, 10, tzinfo=timezone.utc)


def _write_card(tmp_path, name, **overrides):
    fields = {
        "id": name,
        "title": name,
        "state": "ACTIVE",
        "priority": "P1",
        "owner": "someone",
        "repo": "acme/demo",
        "last_activity": "2026-01-01T00:00:00Z",
        "stall_after": "7 days with no commit",
        "stalled": "false",
        "reason": "null",
        "since": "null",
    }
    fields.update(overrides)
    text = f"""---
id: {fields['id']}
title: "{fields['title']}"
state: {fields['state']}
owner: {fields['owner']}
priority: {fields['priority']}
repo: {fields['repo']}
heartbeat:
  cadence: "session-driven"
  last_activity: "{fields['last_activity']}"
  activity_proof: "seed"
  stall_after: "{fields['stall_after']}"
stall:
  stalled: {fields['stalled']}
  reason: {fields['reason']}
  since: {fields['since']}
next_move: "do it"
resume: |
  fresh clone
gates: []
facts_last_verified: "2026-01-01T00:00:00Z"
---
body
"""
    p = tmp_path / f"{name}.md"
    p.write_text(text, encoding="utf-8")
    return cards.read_card(p)


def test_regenerate_empty_registry_no_tail():
    text = registry_gen.regenerate([], "", NOW)
    assert "# Open Projects Registry" in text
    assert registry_gen.TAIL_MARKER not in text


def test_regenerate_preserves_hand_authored_tail(tmp_path):
    card = _write_card(tmp_path, "p1")
    existing = (
        "# Open Projects Registry\n\nstale header\n\n"
        f"{registry_gen.TAIL_MARKER}\n\nHand-authored incident notes here.\n"
    )
    text = registry_gen.regenerate([card], existing, NOW)
    assert "Hand-authored incident notes here." in text
    assert "stale header" not in text  # header above marker is regenerated
    assert "p1" in text


def test_regenerate_missing_marker_on_nonempty_text_hard_stops():
    with pytest.raises(registry_gen.RegistryGenError):
        registry_gen.regenerate([], "# Some pre-existing content\n\nno marker here\n", NOW)


def test_stalled_card_appears_in_stalled_table(tmp_path):
    card = _write_card(tmp_path, "p2", stalled="true", reason="attention-shift", since="2026-01-05T00:00:00Z")
    text = registry_gen.regenerate([card], "", NOW)
    assert "STALLED right now" in text
    assert "p2" in text
    assert "attention-shift" in text


def test_sort_by_priority_groups(tmp_path):
    p0 = _write_card(tmp_path, "high", priority="P0")
    p2 = _write_card(tmp_path, "low", priority="P2")
    text = registry_gen.regenerate([p0, p2], "", NOW)
    assert text.index("## P0") < text.index("## P2")
