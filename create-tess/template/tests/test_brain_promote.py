"""Promotion policy (spec 10.6) and the operator's review commands."""
import json
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

SID = "pro00001-aaaa-4bbb-8ccc-000000000001"


@pytest.fixture
def inst(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    cdir = tmp_path / "claude"
    fxlib.claude_session(cdir / (SID + ".jsonl"), SID, [
        ("user", "Decision: approve S$900 for the Acme shoot."),
        ("user", "From now on, answer in bullet points."),
        ("user", "Remind me to renew the domain."),
        ("user", "The office wifi password rotates every Monday."),
        ("assistant", "The printer is on the second floor."),
        ("user", "approve 1 and reject 2"),
        ("user", "that one was not a decision"),
        ("user", "Please go back to full sentences for answers."),
    ])
    r = fxlib.sync_dir(inst, cdir)
    assert r.returncode == 0, r.stderr
    return inst


def cli(inst, *args):
    r = fxlib.cli(inst, "--json", *args)
    return r.returncode, json.loads(r.stdout or "null")


def say(inst, text):
    """The operator answers in the session, after `review` showed the item with its id; then sync."""
    cdir = inst.parent / "claude"
    fxlib.operator_says(cdir / (SID + ".jsonl"), SID, text)
    assert fxlib.sync_dir(inst, cdir).returncode == 0


def meta(path):
    return {l.split(":", 1)[0]: l.split(":", 1)[1].strip() for l in Path(path).read_text().split("---")[1].splitlines()
            if ":" in l}


def test_material_decision_stays_proposed_until_confirmed(inst):
    rec = next(inst.rglob("D-*approve*.md"))
    m = meta(rec)
    assert m["status"] == '"proposed"' and m["tier"] == '"material"' and m["confirmed"] == "false"
    rid = m["id"].strip('"')
    rc, out = cli(inst, "confirm", rid, "--quote", "approve 1 and reject 2")  # an old line never confirms it
    assert rc == 1 and "naming %s" % rid in out["error"] and meta(rec)["status"] == '"proposed"'
    assert cli(inst, "review")[0] == 0
    say(inst, "confirm %s" % rid)
    rc, out = cli(inst, "confirm", rid, "--quote", "confirm %s" % rid)
    assert rc == 0 and out["status"] == "accepted", out
    assert meta(rec)["confirmed"] == "true"


def test_preference_active_unconfirmed_and_in_profile(inst):
    prof = (inst / "brain/profile.md").read_text()
    assert "From now on, answer in bullet points." in prof and "*unconfirmed*" in prof


def test_loop_is_proposed_never_active(inst):
    rec = next(inst.rglob("L-*.md"))
    assert meta(rec)["status"] == '"proposed"'
    assert "renew the domain" in (inst / "brain/open-loops.md").read_text()


def test_fact_from_principal_words_and_from_assistant(inst):
    rc, out = cli(inst, "inbox", "add", "--kind", "fact", "--quote", "The office wifi password rotates every Monday")
    assert rc == 0 and out["status"] == "active", out
    rc, out = cli(inst, "inbox", "add", "--kind", "fact", "--quote", "The printer is on the second floor")
    assert rc == 0 and out["status"] == "review"
    cid = out["candidate"]
    rc, out = cli(inst, "promote", cid, "--quote", "approve 1 and reject 2")
    assert rc == 1 and "V1/V2" in out["error"]
    say(inst, "approve %s" % cid)  # inbox add showed it (with its id) before the operator answered
    rc, out = cli(inst, "promote", cid, "--quote", "approve %s" % cid)
    assert rc == 0 and out["status"] == "active" and out["confirmed"] is True
    rec = inst / out["record"]
    assert 'source_kind: "assistant"' in rec.read_text()


def test_skill_goes_to_drafts_only(inst):
    rc, out = cli(inst, "inbox", "add", "--kind", "skill", "--quote", "From now on, answer in bullet points",
                  "--title", "bullet answers")
    assert rc == 0 and out["record"] == "brain/skills-drafts/bullet-answers.md"


def test_correction_supersedes_and_retract(inst):
    old = next((inst / "brain/profile").glob("P-*bullet*.md"))
    oid = meta(old)["id"].strip('"')
    rc, out = cli(inst, "remember", "--no-sync", "--kind", "correction", "--quote",
                  "go back to full sentences for answers", "--supersedes", oid)
    assert rc == 0 and out["status"] == "active", out
    assert meta(old)["status"] == '"superseded"'
    prof = (inst / "brain/profile.md").read_text()
    assert "bullet points" not in prof and "full sentences" in prof
    new_id = Path(out["record"]).stem
    assert cli(inst, "review")[0] == 0
    say(inst, "retract %s, that one was not a decision" % new_id)
    rc, out = cli(inst, "retract", new_id, "--quote", "retract %s, that one was not a decision" % new_id)
    assert rc == 0 and out["status"] == "retracted", out
    assert "full sentences" not in (inst / "brain/profile.md").read_text()
    learned = (inst / "brain/learned.md").read_text()
    assert "(now retracted)" in learned and "Retracts %s" % new_id in learned


def test_reject_needs_the_principals_words(inst):
    rec = next(inst.rglob("D-*approve*.md"))
    rid = meta(rec)["id"].strip('"')
    rc, out = cli(inst, "reject", rid, "--quote", "the operator never said this")
    assert rc == 1 and "V1/V2" in out["error"]
    rc, out = cli(inst, "reject", rid, "--quote", "that one was not a decision")
    assert rc == 1 and "V1/V2" in out["error"]  # the operator's words must name the record
    assert cli(inst, "review")[0] == 0
    say(inst, "reject %s: that one was not a decision" % rid)
    rc, out = cli(inst, "reject", rid, "--quote", "reject %s: that one was not a decision" % rid)
    assert rc == 0 and meta(rec)["status"] == '"rejected"'


def test_review_lists_numbered_items_with_reasons(inst):
    rc, items = cli(inst, "review")
    assert rc == 0 and [i["n"] for i in items] == list(range(1, len(items) + 1))
    whys = " ".join(w for i in items for w in i["why"])
    assert "proposed: needs your confirmation" in whys and "auto-promoted (confirmed: false)" in whys
