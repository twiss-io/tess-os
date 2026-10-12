"""Acceptance L7: the brain never writes something wrong.

A principal's decision is accepted with a source_ref that resolves; the
assistant's words (V2), an amount not in the source (V4), an invented quote
(V1), a hypothetical (V8), a principal outside their scope (V9) are all
refused; an external-context fact goes to review (V6); learned.md gains
exactly the expected lines; hand-editing an accepted body fails lint.
"""
import json
import sys
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

sys.path.insert(0, str(Path(fxlib.REPO) / "scripts" / "brain"))
from brainlib import lookup  # noqa: E402
from brainlib.config import Config  # noqa: E402

SID = "fab00001-aaaa-4bbb-8ccc-000000000001"
EXT = "fab00003-aaaa-4bbb-8ccc-000000000003"


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("fab")
    inst = Path(fxlib.make(str(tmp / "fx")))
    cdir = tmp / "claude"
    fxlib.claude_session(cdir / (SID + ".jsonl"), SID, [
        ("user", "Decision: let's use Postgres for the ledger."),
        ("assistant", "Noted. We decided to use MongoDB for the ledger."),
        ("user", "Yes, approve the retainer for Acme this month."),
        ("user", "If we went with MongoDB instead, would that be faster?"),
    ])
    ext = fxlib.claude_session(cdir / (EXT + ".jsonl"), EXT, [("user", "The Acme store runs on Shopify Plus.")],
                               start_minute=20)
    with open(ext, "a") as fh:  # the session searched the web: external context
        fh.write(json.dumps({"type": "assistant", "sessionId": EXT, "timestamp": "2026-09-24T06:21:00.000Z",
                             "message": {"role": "assistant", "content": [
                                 {"type": "tool_use", "id": "t1", "name": "WebSearch", "input": {"query": "x"}}]}})
                 + "\n")
    r = fxlib.sync_dir(inst, cdir)
    assert r.returncode == 0, r.stdout + r.stderr
    note = fxlib.note(inst, "sam", "Decision: we'll switch to the green palette.")  # sam's words, by note
    return {"inst": inst, "sync": json.loads(r.stdout), "note": json.loads(note.stdout), "learned0": _learned(inst)}


def _learned(inst):
    p = inst / "brain/learned.md"
    return [l for l in p.read_text().splitlines() if l.startswith("- ")] if p.exists() else []


def _add(inst, *args):
    r = fxlib.cli(inst, "--json", "inbox", "add", *args)
    return r.returncode, json.loads(r.stdout or "{}")


def test_principal_decision_accepted_with_resolving_source(world):
    inst = world["inst"]
    # the same session later floats "MongoDB instead?": V12 holds the decision for review, never accepted
    assert not list((inst / "brain").rglob("D-*-lets-use-postgres*.md"))
    held = [c for c in (json.loads(p.read_text()) for p in (inst / "brain/inbox").glob("C-*.json"))
            if "Postgres" in c["quote"]]
    assert len(held) == 1 and held[0]["verification"]["reasons"][0].startswith("V12"), held
    start = (inst / "brain/START-HERE.md").read_text()
    assert "awaiting review (not accepted)" in start and "Postgres" not in start
    r = fxlib.cli(inst, "--json", "promote", held[0]["id"], "--quote", "let's use Postgres for the ledger")
    assert r.returncode == 0, r.stdout + r.stderr  # the operator approves it in review
    recs = list((inst / "brain").rglob("D-*-lets-use-postgres*.md"))  # session named Acme: clients/acme
    assert len(recs) == 1
    text = recs[0].read_text()
    assert 'status: "accepted"' in text and 'decided_by: "probe"' in text
    ref = [l for l in text.splitlines() if l.startswith("source_ref:")][0].split('"')[1]
    line = lookup.resolve(Config(inst), ref)
    assert line is not None and "let's use Postgres for the ledger" in line.text
    assert fxlib.cli(inst, "lint").returncode == 0


def test_assistant_words_are_never_a_decision(world):
    inst = world["inst"]
    rc, out = _add(inst, "--kind", "decision", "--quote", "We decided to use MongoDB for the ledger",
                   "--statement", "We will use MongoDB for the ledger")
    assert rc == 1 and out["status"] == "fail" and out["reasons"][0].startswith("V2")
    assert not list((inst / "brain").rglob("D-*mongodb*.md"))


def test_amount_not_in_source_is_refused(world):
    rc, out = _add(world["inst"], "--kind", "decision", "--quote", "approve the retainer for Acme this month",
                   "--statement", "Approve S$450 for the retainer")
    assert rc == 1 and out["reasons"][0].startswith("V4") and "450" in out["reasons"][0]


def test_invented_quote_is_refused(world):
    rc, out = _add(world["inst"], "--kind", "decision", "--quote", "we will migrate everything to Oracle")
    assert rc == 1 and out["reasons"][0].startswith("V1")


def test_hypothetical_is_refused(world):
    rc, out = _add(world["inst"], "--kind", "decision", "--quote",
                   "If we went with MongoDB instead, would that be faster?")
    assert rc == 1 and out["reasons"] == ["V8: hypothetical"]


def test_principal_outside_scope_is_refused(world):
    outcomes = [o for o in world["note"]["outcomes"] if "green palette" in o["statement"]]
    assert outcomes and outcomes[0]["status"] == "fail" and outcomes[0]["reasons"][0].startswith("V9")
    rc, out = _add(world["inst"], "--kind", "decision", "--quote", "we'll switch to the green palette",
                   "--register", "brain/decisions", "--speaker", "sam")
    assert rc == 1 and out["reasons"][0].startswith("V9")
    rejected = list((world["inst"] / "brain/inbox/rejected").glob("C-*.json"))
    assert rejected


def test_external_context_fact_goes_to_review(world):
    rc, out = _add(world["inst"], "--kind", "fact", "--quote", "The Acme store runs on Shopify Plus",
                   "--entity", "clients/acme")
    assert rc == 0 and out["status"] == "review"
    assert any("V6" in r for r in out["reasons"])
    assert not list((world["inst"] / "brain/clients/acme").rglob("F-*.md"))


def test_learned_gains_exactly_the_expected_lines(world):
    assert world["learned0"] == []  # after sync: the one decision waits for review, nothing learned
    lines = _learned(world["inst"])  # after the operator approved it (test above)
    assert len(lines) == 1, lines
    assert "let's use Postgres for the ledger" in lines[0] and "· cue" in lines[0]
    assert "MongoDB" not in (world["inst"] / "brain/learned.md").read_text()


def test_hand_edit_of_accepted_body_fails_lint(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    cdir = tmp_path / "claude"
    fxlib.claude_session(cdir / (SID + ".jsonl"), SID, [("user", "Decision: let's use Postgres for the ledger.")])
    assert fxlib.sync_dir(inst, cdir).returncode == 0
    assert fxlib.cli(inst, "lint").returncode == 0
    rec = next((inst / "brain").rglob("D-*.md"))
    rec.write_text(rec.read_text().replace("## Consequences", "## Consequences\n\nAlso MongoDB."))
    r = fxlib.cli(inst, "lint")
    assert r.returncode == 1 and "body_sha256" in r.stdout
