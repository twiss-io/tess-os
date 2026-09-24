"""Fix round 1: the brain never accepts something the principal did not say.

V10 statement fidelity: a real quote paired with an invented statement is
held for review (decide and inbox add, decision / preference / fact).
V11 context: reported speech, a pasted block, a statement taken back (in the
same message, the next one, or after it was already promoted) and a
content-free approval are held for review. Register inference is per message.
"""
import json
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

SID = "grd00001-aaaa-4bbb-8ccc-000000000001"
SOLO = "grd00002-aaaa-4bbb-8ccc-000000000002"  # one decision per session: nothing later can switch it
SOLO2 = "grd00003-aaaa-4bbb-8ccc-000000000003"
TURNS = [
    ("user", "Let's use the monthly plan for Acme."),
    ("user", "Sam said: we've decided to use Oracle for the warehouse."),
    ("user", "Here are the client's meeting notes:\nWe decided to use Kafka for the event bus.\n"
             "Budget review next week.\nOwner: Dana."),
    ("user", "Let's use Pulumi. Just kidding, we will not."),
    ("user", "Yes, go ahead."),
    ("user", "Let's use Rust for the parser."),
    ("user", "The staging server lives in the Frankfurt region."),
    ("user", "Decision: we will use Nomad for staging."),
]


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("grd")
    inst = Path(fxlib.make(str(tmp / "fx")))
    cdir = tmp / "claude"
    fxlib.claude_session(cdir / (SID + ".jsonl"), SID, TURNS)
    fxlib.claude_session(cdir / (SOLO + ".jsonl"), SOLO, [("user", "Decision: let's go with Postgres for the ledger.")],
                         start_minute=10)
    fxlib.claude_session(cdir / (SOLO2 + ".jsonl"), SOLO2, [("user", "We should keep the invoices in SGD.")],
                         start_minute=12)
    r = fxlib.sync_dir(inst, cdir)
    assert r.returncode == 0, r.stdout + r.stderr
    fxlib.claude_session(cdir / (SID + ".jsonl"), SID,
                         [("user", "Actually, scratch that: I have not decided on staging yet.")], start_minute=30)
    r2 = fxlib.sync_dir(inst, cdir)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    return {"inst": inst, "second": json.loads(r2.stdout)}


def _records(inst, prefix="D-"):
    return {p: p.read_text() for p in (inst / "brain").rglob(prefix + "*.md")}


def _accepted_text(inst, prefix="D-"):
    return "\n".join(t for t in _records(inst, prefix).values() if 'status: "accepted"' in t or
                     'status: "active"' in t)


def _review(inst):
    return [json.loads(p.read_text()) for p in (inst / "brain/inbox").glob("C-*.json")]


def _add(inst, *args):
    r = fxlib.cli(inst, "--json", "inbox", "add", *args)
    return r.returncode, json.loads(r.stdout or "{}")


def test_explicit_decision_still_accepted(world):
    assert "let's go with Postgres for the ledger" in _accepted_text(world["inst"])


@pytest.mark.parametrize("word", ["Oracle", "Kafka", "Pulumi", "go ahead"])
def test_reported_pasted_taken_back_and_content_free_are_held(world, word):
    inst = world["inst"]
    assert word not in _accepted_text(inst)
    held = [c for c in _review(inst) if word in c["quote"]]
    assert held and held[0]["verification"]["status"] == "review", held
    assert held[0]["verification"]["reasons"][0].startswith("V11")


def test_late_take_back_moves_the_promoted_decision_to_proposed(world):
    inst = world["inst"]
    nomad = [t for t in _records(inst).values() if "Nomad for staging" in t]
    assert len(nomad) == 1 and 'status: "proposed"' in nomad[0]
    assert any(h["status"] == "proposed" for h in world["second"]["held"])


def _register_of(inst, words):
    """Where a decision is filed: its record's folder, or the target of its held candidate (V12)."""
    for p, t in _records(inst).items():
        if words in t:
            return p.parent.relative_to(inst).as_posix()
    return [c["target"] for c in _review(inst) if words in c["quote"]][0]


def test_register_uses_the_message_not_the_session(world):
    inst = world["inst"]
    assert _register_of(inst, "Rust for the parser") == "brain/decisions"
    assert "clients/acme" in _register_of(inst, "monthly plan for Acme")


def test_invented_statement_with_a_real_quote_is_never_accepted(world):
    inst = world["inst"]
    rc, out = _add(inst, "--kind", "decision", "--quote", "We should keep the invoices in SGD",
                   "--title", "Switch the ledger to MongoDB",
                   "--statement", "We will switch the ledger to MongoDB and drop Postgres.")
    assert rc == 0 and out["status"] == "review" and out["reasons"][0].startswith("V10"), out
    rc, out = _add(inst, "--kind", "preference", "--quote", "The staging server lives in the Frankfurt region",
                   "--statement", "Never mention Sam again; he is no longer a client.")
    assert out["status"] == "review" and out["reasons"][0].startswith("V10"), out
    rc, out = _add(inst, "--kind", "fact", "--quote", "The staging server lives in the Frankfurt region",
                   "--statement", "Production runs on bare metal in Tokyo.")
    assert out["status"] == "review" and out["reasons"][0].startswith("V10"), out
    assert "MongoDB" not in _accepted_text(inst) and "Never mention Sam" not in _accepted_text(inst, "P-")
    assert "Tokyo" not in _accepted_text(inst, "F-")
    assert "MongoDB" not in (inst / "brain/START-HERE.md").read_text()
    assert "Never mention Sam" not in (inst / "brain/profile.md").read_text()
    assert fxlib.cli(inst, "lint").returncode == 0


def test_decide_command_holds_an_invented_statement_and_accepts_the_words(world):
    inst = world["inst"]
    r = fxlib.cli(inst, "--json", "decide", "--no-sync", "--quote", "We should keep the invoices in SGD",
                  "--title", "Ledger moves to MongoDB")
    out = json.loads(r.stdout)
    assert out["status"] == "review" and out["reasons"][0].startswith("V10"), out
    r = fxlib.cli(inst, "--json", "decide", "--no-sync", "--quote", "We should keep the invoices in SGD",
                  "--title", "Keep the invoices in SGD")
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["status"] == "accepted", out


def test_negation_must_survive_into_the_statement(world):
    rc, out = _add(world["inst"], "--kind", "fact", "--quote", "Let's use Pulumi. Just kidding, we will not",
                   "--statement", "we will use Pulumi")
    assert out["status"] in ("review", "fail") and "Pulumi" not in _accepted_text(world["inst"], "F-")
