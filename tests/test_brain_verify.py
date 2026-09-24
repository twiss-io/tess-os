"""The mechanical verifier V1-V9 (spec 10.5), rule by rule."""
import json
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

SID = "ver00001-aaaa-4bbb-8ccc-000000000001"


@pytest.fixture
def inst(tmp_path):
    bj = json.loads(Path(fxlib.HERE, "brain.json").read_text())
    bj["principals"].append({"slug": "ada", "role": "advisor", "decides": False, "scope": ["**"],
                             "aliases": ["telegram:7777"], "journal_consent": "shared"})
    p = tmp_path / "bj.json"
    p.write_text(json.dumps(bj))
    inst = Path(fxlib.make(str(tmp_path / "fx"), brain_json=str(p)))
    cdir = tmp_path / "claude"
    fxlib.claude_session(cdir / (SID + ".jsonl"), SID, [
        ("user", "We  should keep the “weekly” report format going forward."),
        ("assistant", "I propose we move the retainer review to the first Monday of each month."),
        ("user", "yes, do that"),
        ("tg:7777", "Decision: let's use Linear for tickets."),
        ("assistant", "Another idea: switch the newsletter to fortnightly."),
        ("user", "Unrelated question about lunch."),
        ("user", "Also unrelated."),
        ("user", "ok fine"),
    ])
    assert fxlib.sync_dir(inst, cdir).returncode == 0
    return inst


def add(inst, *args):
    r = fxlib.cli(inst, "--json", "inbox", "add", *args)
    return r.returncode, json.loads(r.stdout or "{}")


def test_v1_normalises_only_whitespace_and_smart_quotes(inst):
    rc, out = add(inst, "--kind", "preference", "--quote", 'We should keep the "weekly" report format going forward')
    assert rc == 0 and out["status"] == "active", out
    rc, out = add(inst, "--kind", "preference", "--quote", "We should keep the weekly reports")
    assert rc == 1 and out["reasons"][0].startswith("V1")


def test_v1_minimum_length(inst):
    rc, out = add(inst, "--kind", "fact", "--quote", "ok fine")
    assert rc == 1 and "shorter than 12" in out["reasons"][0]


def test_v2_non_deciding_principal(inst):
    rc, out = add(inst, "--kind", "decision", "--quote", "let's use Linear for tickets")
    assert rc == 1 and out["reasons"][0].startswith("V2")


def test_v2_speaker_must_match_the_line(inst):
    rc, out = add(inst, "--kind", "preference", "--quote", "report format going forward", "--speaker", "sam")
    assert rc == 1 and "does not match" in out["reasons"][0]


def test_v3_approval_of_an_assistant_proposal(inst):
    rc, out = fxlib_decide(inst, "yes, do that", "--approves-quote",
                           "move the retainer review to the first Monday of each month",
                           "--statement", "We will move the retainer review to the first Monday of each month")
    assert rc == 0 and out["status"] == "accepted", out
    rec = next(Path(inst, "brain/decisions").glob("D-*.md")).read_text()
    assert 'authority: "approval"' in rec and "first Monday" in rec
    rc, out = fxlib_decide(inst, "ok fine", "--approves-quote", "switch the newsletter to fortnightly",
                           "--statement", "We will switch the newsletter to fortnightly")
    assert rc == 1 and out["reasons"][0].startswith("V3")


def fxlib_decide(inst, quote, *args):
    r = fxlib.cli(inst, "--json", "decide", "--no-sync", "--quote", quote, *args)
    return r.returncode, json.loads(r.stdout or "{}")


def test_v5_duplicate_is_noop_and_supersedes_must_exist(inst):
    q = 'keep the "weekly" report format going forward'
    assert add(inst, "--kind", "preference", "--quote", q)[0] == 0
    rc, out = add(inst, "--kind", "preference", "--quote", q)
    assert rc == 0 and out["status"] == "noop" and out["reasons"][0].startswith("V5")
    rc, out = add(inst, "--kind", "preference", "--quote", q, "--supersedes", "P-20200101-0000-nothing")
    assert rc == 1 and "supersedes target" in out["reasons"][0]


def test_v7_secret_shaped_statement(inst):
    token = fxlib.planted_github_token()
    rc, out = add(inst, "--kind", "fact", "--quote", 'keep the "weekly" report format', "--statement",
                  "The deploy key is %s" % token)
    assert rc == 1 and out["reasons"][0].startswith("V7")
    assert token not in "".join(p.read_text() for p in Path(inst, "brain").rglob("*") if p.is_file())


def test_pending_then_unverified_after_two_failed_syncs(inst, tmp_path):
    fxlib.cli(inst, "hook", "prompt", stdin=json.dumps({"session_id": "zz", "prompt": "From now on, sign off as T."}))
    rc, out = add(inst, "--kind", "preference", "--quote", "From now on, sign off as T")
    assert out["status"] == "pending-verification", out
    rec = Path(inst, out["record"])
    (inst / ".tess/state/brain/turns.jsonl").unlink()  # the turn never reaches a transcript
    for _ in range(2):
        fxlib.sync_dir(inst, tmp_path / "empty")
    assert 'status: "unverified"' in rec.read_text()
    assert "sign off as T" not in (inst / "brain/profile.md").read_text()


def test_hand_written_note_is_never_auto_promoted(inst):
    r = fxlib.cli(inst, "--json", "journal", "note", "--text", "Decision: let's go with weekly standups.")
    out = json.loads(r.stdout)
    assert out["journaled"] and [o["status"] for o in out["outcomes"]] == ["review"]
    assert "hand-written journal note" in out["outcomes"][0]["reasons"][0]


def test_unknown_git_user_is_not_credited_to_a_principal(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    fxlib.run(str(inst), "config", "user.email", "someone-else@example.invalid")
    fxlib.sync_fixture(inst)
    text = (inst / "brain/journal/2026/09/24/1405-claude-11111111.md").read_text()
    assert "[non-principal operator omitted: no consent]" in text and "Postgres" not in text
    assert "[L2 14:10 sam telegram] Decision: we'll use the blue logo for Acme." in text  # channel alias still maps
    st = fxlib.cli(inst, "status").stdout
    assert "matches no principal's git_emails" in st
