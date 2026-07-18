"""Unit tests for scripts/heartbeat/escalation.py — pure-arithmetic repeat-stall
handling, no LLM involved."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from heartbeat import escalation  # noqa: E402

NOW = datetime(2026, 1, 10, tzinfo=timezone.utc)


def test_blocked_external_never_notifies():
    decision = escalation.decide(
        slug="s", title="T", reason="blocked-external",
        since=NOW - timedelta(hours=100), last_alarmed=None, now=NOW,
    )
    assert decision.should_notify is False
    assert decision.message is None


def test_awaiting_decision_under_escalate_after_is_silent():
    decision = escalation.decide(
        slug="s", title="T", reason="awaiting-decision",
        since=NOW - timedelta(hours=10), last_alarmed=None, now=NOW,
    )
    assert decision.should_notify is False


def test_awaiting_decision_past_escalate_after_notifies():
    decision = escalation.decide(
        slug="s", title="T", reason="awaiting-decision",
        since=NOW - timedelta(hours=49), last_alarmed=None, now=NOW,
    )
    assert decision.should_notify is True
    assert "awaiting a decision" in decision.message
    assert "49h" in decision.message


def test_cooldown_suppresses_repeat_within_window():
    decision = escalation.decide(
        slug="s", title="T", reason="awaiting-decision",
        since=NOW - timedelta(hours=49),
        last_alarmed=NOW - timedelta(hours=1),
        now=NOW,
    )
    assert decision.should_notify is False


def test_cooldown_expired_notifies_again():
    decision = escalation.decide(
        slug="s", title="T", reason="awaiting-decision",
        since=NOW - timedelta(hours=100),
        last_alarmed=NOW - timedelta(hours=25),
        now=NOW,
    )
    assert decision.should_notify is True


def test_attention_shift_reminder_cooldown_applies():
    # attention-shift is not "reminder class" (no ESCALATE_AFTER gate) but
    # still respects REMIND_COOLDOWN once already alarmed once.
    decision = escalation.decide(
        slug="s", title="T", reason="attention-shift",
        since=NOW - timedelta(hours=5),
        last_alarmed=NOW - timedelta(hours=1),
        now=NOW,
    )
    assert decision.should_notify is False


def test_no_since_never_notifies():
    decision = escalation.decide(
        slug="s", title="T", reason="attention-shift",
        since=None, last_alarmed=None, now=NOW,
    )
    assert decision.should_notify is False
