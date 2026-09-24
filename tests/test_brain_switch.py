"""Fix round 3 (V12): switching to a new option without naming the old one.

"let's use Postgres" ... "actually, go with SQLite" never records Postgres as
ACCEPTED: not in the same message, not across several turns, not in other
wordings, and not when the switch arrives in a later sync. A true single
decision is still accepted. Lint flags two accepted decisions on the same
topic from one session.
"""
import json
import sys
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

sys.path.insert(0, str(Path(fxlib.REPO) / "scripts" / "brain"))
from brainlib import records, switch  # noqa: E402
from brainlib.config import Config  # noqa: E402

SID = "swi00001-aaaa-4bbb-8ccc-000000000001"
POSTGRES = "Decision: let's use Postgres for the ledger."
SWITCHES = [  # the new option only; the old one is never named
    "Actually go with SQLite.", "Actually, go with SQLite.", "Let's go with SQLite.", "Scrap that, we'll do SQLite.",
    "Change of plan: SQLite it is.", "On second thought, SQLite.", "No, SQLite.", "No, use SQLite.",
    "Let's not, we'll use SQLite.", "Maybe SQLite instead.", "Switch to SQLite.", "We'll go with SQLite then.",
    "Decision: SQLite for the ledger.", "Go back to SQLite.",
]
KEPT = [  # later sentences that are not a new choice: a single decision stands
    "Thanks.", "The deadline is Friday.", "Can you draft the schema?", "Add an index on the date column.",
    "From now on, always answer in bullet points.", "No, that's wrong: the client's timezone is SGT, not UTC.",
    "Remind me to send the pricing note to Sam by Friday.", "If we went with CouchDB, would that be faster?",
]


def _run(tmp_path, turns, sid=SID, minute=0, inst=None):
    inst = inst or Path(fxlib.make(str(tmp_path / "fx")))
    cdir = tmp_path / "claude"
    fxlib.claude_session(cdir / (sid + ".jsonl"), sid, turns, start_minute=minute)
    r = fxlib.sync_dir(inst, cdir)
    assert r.returncode in (0, 3), r.stdout + r.stderr
    return inst, json.loads(r.stdout)


def _records(inst):
    return [p.read_text() for p in (inst / "brain").rglob("D-*.md")]


def _accepted(inst):
    return "\n".join(t for t in _records(inst) if 'status: "accepted"' in t)


def _start_here_accepted(inst):
    return [l for l in (inst / "brain/START-HERE.md").read_text().splitlines() if "(accepted)" in l]


def _held(inst, word):
    return [c for c in (json.loads(p.read_text()) for p in (inst / "brain/inbox").glob("C-*.json"))
            if word in c["quote"]]


def _assert_postgres_not_accepted(inst):
    assert "Postgres" not in _accepted(inst)
    assert not [l for l in _start_here_accepted(inst) if "Postgres" in l]
    assert fxlib.cli(inst, "lint").returncode == 0


@pytest.mark.parametrize("later", SWITCHES)
def test_switch_phrasings_are_detected(later):
    assert switch.switch_in("let's use Postgres for the ledger", [later]), later


@pytest.mark.parametrize("later", KEPT)
def test_non_choices_leave_the_decision(later):
    assert switch.switch_in("let's use Postgres for the ledger", [later]) is None, later


def test_switch_without_naming_the_old_option(tmp_path):
    """The verifier's case: 'let's use Postgres' ... 'actually go with SQLite'."""
    inst, _ = _run(tmp_path, [("user", POSTGRES), ("user", "Actually go with SQLite.")])
    _assert_postgres_not_accepted(inst)
    held = _held(inst, "Postgres")
    assert held and held[0]["verification"]["status"] == "review"
    assert held[0]["verification"]["reasons"][0].startswith("V12"), held[0]["verification"]


def test_switch_in_the_same_message(tmp_path):
    inst, _ = _run(tmp_path, [("user", POSTGRES + " Actually, go with SQLite.")])
    _assert_postgres_not_accepted(inst)


def test_switch_across_several_turns(tmp_path):
    inst, _ = _run(tmp_path, [("user", POSTGRES), ("assistant", "Noted. Anything else?"),
                              ("user", "Can you draft the schema?"), ("assistant", "Here is a draft."),
                              ("user", "Add an index on the date column."), ("assistant", "Done."),
                              ("user", "Hmm, go with SQLite instead.")])
    _assert_postgres_not_accepted(inst)


def test_alternative_question_then_yes_across_turns(tmp_path):
    inst, _ = _run(tmp_path, [("user", POSTGRES), ("user", "What about SQLite instead?"),
                              ("assistant", "SQLite would be simpler for a single user."), ("user", "Yes, do that.")])
    _assert_postgres_not_accepted(inst)


@pytest.mark.parametrize("later", ["Scrap that, we'll do SQLite.", "Change of plan: SQLite it is.",
                                   "Let's go with SQLite for the ledger.", "No, SQLite."])
def test_switch_in_other_wordings(tmp_path, later):
    inst, _ = _run(tmp_path, [("user", POSTGRES), ("user", later)])
    _assert_postgres_not_accepted(inst)


def test_later_choice_is_the_one_accepted(tmp_path):
    inst, _ = _run(tmp_path, [("user", POSTGRES), ("user", "Decision: let's use SQLite for the ledger.")])
    _assert_postgres_not_accepted(inst)
    assert "SQLite for the ledger" in _accepted(inst)


def test_switch_after_promotion_moves_it_to_proposed(tmp_path):
    inst, _ = _run(tmp_path, [("user", POSTGRES)])
    assert "Postgres" in _accepted(inst)
    inst, out = _run(tmp_path, [("user", "Thanks. Actually go with SQLite.")], minute=30, inst=inst)
    _assert_postgres_not_accepted(inst)
    assert any(h["status"] == "proposed" and h["reason"].startswith("V12") for h in out["held"]), out["held"]


def test_true_single_decision_is_still_accepted(tmp_path):
    inst, _ = _run(tmp_path, [("user", POSTGRES), ("assistant", "Noted."), ("user", "Can you draft the schema?"),
                              ("user", "The deadline is Friday."), ("user", "Thanks.")])
    assert "let's use Postgres for the ledger" in _accepted(inst)
    assert [l for l in _start_here_accepted(inst) if "Postgres" in l]
    assert fxlib.cli(inst, "lint").returncode == 0


def _hand_accepted(inst, rid, quote, label, **meta):
    cfg = Config(inst)
    ref = "brain/journal/2026/09/24/1400-claude-%s.md#%s" % (SID[:8], label)
    m = {"id": rid, "type": "decision", "title": quote, "status": "accepted", "source_quote": quote,
         "source_at": "2026-09-24T14:00:00+08:00", "source_ref": ref, "decided_by": "probe", "confirmed": False}
    m.update(meta)
    rec = records.write(cfg, "decision", inst / "brain/decisions", m, {"quote": quote})
    records.update_fields(rec, {})
    return rec


def test_lint_flags_two_accepted_decisions_on_one_topic_from_one_session(tmp_path):
    inst, _ = _run(tmp_path, [("user", "Hello."), ("user", "Thanks.")])  # only to create the journal
    journal = Path(fxlib.journal_of(inst, SID))
    body = journal.read_text()
    journal.write_text(body.replace("Hello.", "let's use Postgres for the ledger").replace(
        "Thanks.", "actually go with SQLite"))
    _hand_accepted(inst, "D-20260924-1400-postgres", "let's use Postgres for the ledger", "L1")
    _hand_accepted(inst, "D-20260924-1401-sqlite", "actually go with SQLite", "L2")
    fxlib.cli(inst, "index")
    r = fxlib.cli(inst, "lint")
    assert r.returncode == 1 and "two accepted decisions on the same topic from one session" in r.stdout, r.stdout


def test_lint_flags_a_shared_subject_even_when_both_are_confirmed(tmp_path):
    inst, _ = _run(tmp_path, [("user", "Hello."), ("user", "Thanks.")])
    journal = Path(fxlib.journal_of(inst, SID))
    journal.write_text(journal.read_text().replace("Hello.", "we use Postgres for the ledger").replace(
        "Thanks.", "we use SQLite for the ledger"))
    _hand_accepted(inst, "D-20260924-1400-pg", "we use Postgres for the ledger", "L1", confirmed=True)
    _hand_accepted(inst, "D-20260924-1401-sq", "we use SQLite for the ledger", "L2", confirmed=True)
    fxlib.cli(inst, "index")
    r = fxlib.cli(inst, "lint")
    assert r.returncode == 1 and "(ledger)" in r.stdout, r.stdout


def test_lint_leaves_two_unrelated_confirmed_decisions(tmp_path):
    inst, _ = _run(tmp_path, [("user", "Hello."), ("user", "Thanks.")])
    journal = Path(fxlib.journal_of(inst, SID))
    journal.write_text(journal.read_text().replace("Hello.", "we use Postgres for the ledger").replace(
        "Thanks.", "we publish the newsletter on Tuesdays"))
    _hand_accepted(inst, "D-20260924-1400-pg", "we use Postgres for the ledger", "L1", confirmed=True)
    _hand_accepted(inst, "D-20260924-1401-nl", "we publish the newsletter on Tuesdays", "L2", confirmed=True)
    fxlib.cli(inst, "index")
    r = fxlib.cli(inst, "lint")
    assert "same topic" not in r.stdout, r.stdout
