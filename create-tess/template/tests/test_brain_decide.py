"""`tessbrain.py decide` (spec 11): verbatim, verified, immutable, superseded
never edited; registers per entity; material stays proposed."""
import json
import re
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

SID = "dec00001-aaaa-4bbb-8ccc-000000000001"
ENV = {}


@pytest.fixture
def inst(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    home = tmp_path / "claude-home"  # CLAUDE_CONFIG_DIR: decide's own sync finds the transcript here
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(inst))
    fxlib.claude_session(home / "projects" / slug / (SID + ".jsonl"), SID, [
        ("user", "We will publish the newsletter on Tuesdays."),
        ("user", "Our readers seem happy with the current format."),  # a later change is a supersede
        ("user", "Change of plan: we will publish the newsletter on Thursdays."),
        ("user", "For Acme we keep the invoices monthly, and only in SGD."),
        ("user", "Should the retainer be 2 hours a week?"),
        ("user", "We pay the photographer 1200 per shoot."),
    ])
    ENV["CLAUDE_CONFIG_DIR"] = str(home)
    return inst


def decide(inst, *args):
    r = fxlib.cli(inst, "--json", "decide", *args, env=ENV)
    return r.returncode, json.loads(r.stdout or "{}")


def test_decide_syncs_first_and_records_a_resolving_quote(inst):
    rc, out = decide(inst, "--quote", "We will publish the newsletter on Tuesdays", "--title", "Newsletter on Tuesdays")
    assert rc == 0 and out["status"] == "accepted", out
    rec = (inst / out["record"]).read_text()
    assert 'source_ref: "brain/journal/2026/09/24/1400-claude-dec00001.md#L1"' in rec
    assert fxlib.cli(inst, "lint", env=ENV).returncode == 0


def test_supersede_keeps_history_and_indexes_only_the_active_one(inst):
    _, first = decide(inst, "--quote", "We will publish the newsletter on Tuesdays", "--title", "Newsletter on Tuesdays")
    old_id = Path(first["record"]).stem
    rc, out = decide(inst, "--quote", "we will publish the newsletter on Thursdays", "--supersedes", old_id,
                     "--title", "Newsletter on Thursdays")
    assert rc == 0 and out["status"] == "accepted", out
    old = (inst / first["record"]).read_text()
    new_id = Path(out["record"]).stem
    assert 'status: "superseded"' in old and 'superseded_by: "%s"' % new_id in old
    idx = (inst / "brain/decisions/INDEX.md").read_text()
    assert "Newsletter on Thursdays" in idx and "Newsletter on Tuesdays" not in idx
    assert "Newsletter on Tuesdays" in (inst / "brain/decisions/ALL.md").read_text()
    assert fxlib.cli(inst, "lint", env=ENV).returncode == 0  # the body was never touched
    rc, out = decide(inst, "--quote", "we will publish the newsletter on Thursdays", "--supersedes", old_id)
    assert rc == 1 and "already superseded" in out["reasons"][0]


def test_entity_register_also_quoted_and_start_here_block(inst):
    rc, out = decide(inst, "--register", "brain/clients/acme/decisions", "--title", "Acme invoices monthly",
                     "--quote", "For Acme we keep the invoices monthly", "--also-quoted", "only in SGD")
    assert rc == 0 and out["record"].startswith("brain/clients/acme/decisions/"), out
    assert 'also_quoted: ["only in SGD"]' in (inst / out["record"]).read_text()
    agents = (inst / "brain/clients/acme/AGENTS.md").read_text()
    block = agents.split("<!-- tess:gen:decisions:start -->")[1].split("<!-- tess:gen:decisions:end -->")[0]
    assert "Acme invoices monthly" in block


def test_material_and_question_kinds(inst):
    rc, out = decide(inst, "--quote", "We pay the photographer 1200 per shoot", "--tier", "material",
                     "--title", "Photographer at 1200 per shoot")
    assert rc == 0 and out["status"] == "proposed"
    rc, out = decide(inst, "--quote", "Should the retainer be 2 hours a week?", "--kind", "question")
    assert rc == 1 and out["reasons"] == ["V8: hypothetical"]


def test_title_with_a_number_not_in_the_quote_is_refused(inst):
    rc, out = decide(inst, "--quote", "We will publish the newsletter on Tuesdays", "--title", "Newsletter at 9am")
    assert rc == 1 and out["reasons"][0].startswith("V4")
