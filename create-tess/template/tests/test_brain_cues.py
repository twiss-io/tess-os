"""Deterministic cue pass (spec 10.4): verbatim sentences, principal lines
only, currency -> material tier, register inference."""
import json
import sys
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

sys.path.insert(0, str(Path(fxlib.REPO) / "scripts" / "brain"))
from brainlib import cues  # noqa: E402


@pytest.mark.parametrize("sentence,kind", [
    ("Let's go with Postgres for the ledger.", "decision"),
    ("Okay, we'll use Stripe for billing.", "decision"),
    ("Decision: the launch moves to October.", "decision"),
    ("We've decided to drop the blog.", "decision"),
    ("Yes, ship it.", "decision"),
    ("From now on, answer in bullet points.", "preference"),
    ("Always reply in British English.", "preference"),
    ("I prefer short answers.", "preference"),
    ("I want you to cite sources.", "preference"),
    ("No, the client is in Perth.", "correction"),
    ("That's wrong, the invoice went out on Monday.", "correction"),
    ("Actually, the meeting is at 3.", "correction"),
    ("Stop using the old logo.", "correction"),
    ("Remind me to call the bank.", "open_loop"),
    ("Follow up with the printer next week.", "open_loop"),
    ("We are waiting on legal.", "open_loop"),
    ("Send the deck by Friday.", "open_loop"),
])
def test_patterns(sentence, kind):
    hits = cues.scan_text(sentence)
    assert [h.kind for h in hits] == [kind]
    assert hits[0].sentence == sentence  # the statement is the sentence, verbatim


@pytest.mark.parametrize("text", [
    "What do you think about Postgres?", "Can you summarise the report", "The ledger is slow today.",
    "Please draft the email.", "Thanks!",
])
def test_no_cue(text):
    assert cues.scan_text(text) == []


def test_currency_makes_material_and_label_is_stripped():
    hit = cues.scan_text("Decision: approve S$450 for the retainer.")[0]
    assert hit.material and hit.quote == "approve S$450 for the retainer"
    assert not cues.scan_text("Let's go with the blue logo.")[0].material


def test_redacted_sentences_are_skipped():
    assert cues.scan_text("From now on use token <REDACTED:github> for deploys.") == []


@pytest.mark.parametrize("sentence,expected", [
    ("If we went with MongoDB instead, would that be faster?", True),
    ("Maybe we go with Redis.", True),
    ("Let's go with Redis.", False),
    ("Let's go with Redis if the budget allows.", False),  # 'if' after the verb is a condition, not a hypothetical
])
def test_hypothetical_guard(sentence, expected):
    assert cues.is_hypothetical(sentence) is expected
    assert cues.is_hypothetical("Let's go with Redis.", "Just thinking out loud.") is True


def test_register_inference_and_principal_only(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    cdir = tmp_path / "claude"
    fxlib.claude_session(cdir / "cue00001-a.jsonl", "cue00001-a", [
        ("user", "Decision: we'll use the serif logo for Acme."),
        ("assistant", "Decision: let's go with Comic Sans."),
    ])
    fxlib.claude_session(cdir / "cue00002-b.jsonl", "cue00002-b", [("user", "Let's go with weekly invoicing.")],
                         start_minute=30)
    out = json.loads(fxlib.sync_dir(inst, cdir).stdout)
    by = {o["statement"]: o for o in out["outcomes"]}
    assert "Comic Sans" not in json.dumps(out)
    assert by["Decision: we'll use the serif logo for Acme."]["record"].startswith("brain/clients/acme/decisions/D-")
    assert by["Let's go with weekly invoicing."]["record"].startswith("brain/decisions/D-")


def test_prompt_hook_nudges_on_current_turn(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    r = fxlib.cli(inst, "hook", "prompt", stdin=json.dumps({"session_id": "s1", "prompt": "Let's go with Redis."}))
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx.startswith('[brain] possible decision: "Let\'s go with Redis."')
    r = fxlib.cli(inst, "hook", "prompt", stdin=json.dumps({"session_id": "s1", "prompt": "What is the time?"}))
    assert r.stdout == ""
