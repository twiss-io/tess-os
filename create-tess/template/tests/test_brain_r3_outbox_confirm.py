"""v1.0 learning loop, GPT-6 review round 3 (2026-09-29): N1 and the R7 remainder.

Threat model: a repo writer (prompt-injected agent, planted file, collaborator) with no
access to the external state folder or the key. On release/v1.0 @ 40dfd4c all five
N1 tests, the end-to-end two-line conditional, and seven grammar cases (a condition,
lead-in or trailing line, and a code fence) failed; the other cases pin behaviour
that must not regress (accepted forms, blockquote and list refusals).

N1  outbox replay. A sandboxed shell queues signed rows in .tess/state/brain/outbox.jsonl.
    The MAC covered only the row body, so a kept copy of a genuine `shown` row, restored
    after a newer presentation reached the external ledger, read (and drained) as the
    NEWEST presentation, re-opening an operator line that predated the newer one. Every
    row now carries an authenticated one-use event id and the ledger sequence/head it was
    made against; a pending row whose id is already in the ledger, or that is older than
    the ledger's state for its item, is dropped. A confirmation is recorded in the
    external ledger BEFORE it is reported accepted; a sandboxed shell only queues it and
    the next hook (outside the sandbox) completes it.
R7  the WHOLE operator message must be the directive: a condition on another line, a
    code fence, a blockquote or a list item never confirms.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib
from test_brain_provenance_adversarial import _cli, _material, _meta, _say

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "brain"))
from brainlib import confirm  # noqa: E402

BOX = ".tess/state/brain/outbox.jsonl"


def _pdir(inst):
    from brainlib import extstate
    from brainlib.config import Config
    return extstate.project_dir(Config(inst))


class _Sandbox:
    """What the Codex sandbox leaves the agent's shell: the external state folder is read-only."""

    def __init__(self, inst):
        self.d = _pdir(inst)

    def __enter__(self):
        self.files = [f for f in self.d.iterdir() if f.is_file()]
        for f in self.files + [self.d]:
            os.chmod(str(f), 0o500 if f == self.d else 0o400)
        return self

    def __exit__(self, *exc):
        for f in self.files + [self.d]:
            os.chmod(str(f), 0o700 if f == self.d else 0o600)


def _ledger_rows(inst):
    led = _pdir(inst) / "ledger.jsonl"
    return [json.loads(l)["row"] for l in led.read_text().splitlines() if l.strip()] if led.is_file() else []


def _review(inst, rid):
    rc, items = _cli(inst, "review")
    assert rc == 0, items
    return next(it for it in items if it["id"] == rid)


# N1 ---------------------------------------------------------------------------------------------------

def test_n1_an_old_shown_row_restored_after_a_newer_presentation_is_not_selected(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    box = inst / BOX
    with _Sandbox(inst):
        _review(inst, rid)  # presentation 1: queued, signed, in the repo
    kept = box.read_text()
    box.unlink()  # the attacker hides it so it never reaches the ledger
    time.sleep(1.1)
    _say(inst, cdir, path, "confirm %s" % rid)  # after presentation 1 ...
    time.sleep(3.1)  # (operator_says stamps its words 2 s ahead)
    _review(inst, rid)  # ... but before presentation 2, which is durable in the external ledger
    box.write_text(kept)  # the attacker restores the genuine old row
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % rid)
    assert rc == 1 and _meta(rec)["status"] == "proposed", out
    assert "predate" in out["error"], out
    shown = [r for r in _ledger_rows(inst) if r.get("t") == "shown" and r.get("id") == rid]
    assert len(shown) == 1, shown  # the stale row was dropped, not drained


def test_n1_a_duplicate_outbox_row_is_rejected(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    box = inst / BOX
    with _Sandbox(inst):
        _review(inst, rid)
    kept = box.read_text()
    assert fxlib.sync_dir(inst, cdir).returncode in (0, 3)  # the hook drains it once
    assert not box.exists()
    box.write_text(kept)  # replayed
    assert fxlib.sync_dir(inst, cdir).returncode in (0, 3)
    shown = [r for r in _ledger_rows(inst) if r.get("t") == "shown" and r.get("id") == rid]
    assert len(shown) == 1, shown
    assert all(r.get("eid") and isinstance(r.get("base"), int) for r in _ledger_rows(inst))


_SPY = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from brainlib import extstate, promote
orig = promote.change_status
def spy(cfg, rid, action, quote, line):
    extstate._CACHE.clear(); extstate._LEDGER.clear()
    led = extstate.project_dir(cfg) / "ledger.jsonl"
    rows = [json.loads(l)["row"] for l in led.read_text().splitlines() if l.strip()]
    ok = any(r.get("t") == "used" and r.get("id") == rid and r.get("ref") == line.ref for r in rows)
    open(sys.argv[2], "w").write("durable" if ok else "not-durable")
    return orig(cfg, rid, action, quote, line)
promote.change_status = spy
import tessbrain
sys.exit(tessbrain.main(sys.argv[3:]))
"""


def test_n1_consumption_is_recorded_in_the_external_ledger_before_acceptance(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    _review(inst, rid)
    _say(inst, cdir, path, "confirm %s" % rid)
    spy, mark = tmp_path / "spy.py", tmp_path / "mark"
    spy.write_text(_SPY)
    env = dict(os.environ, TESS_BRAIN_NO_BACKFILL="1", CODEX_HOME=str(inst / ".none"),
               GEMINI_CLI_HOME=str(inst / ".none"), CLAUDE_CONFIG_DIR=str(inst / ".none"))
    r = subprocess.run([sys.executable, str(spy), str(Path(fxlib.TESSBRAIN).parent), str(mark), "--root", str(inst),
                        "--json", "confirm", rid, "--quote", "confirm %s" % rid],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0 and json.loads(r.stdout)["status"] == "accepted", r.stdout + r.stderr
    assert mark.read_text() == "durable"


def test_n1_a_sandboxed_confirm_stays_pending_until_a_hook_records_it(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    _review(inst, rid)
    _say(inst, cdir, path, "confirm %s" % rid)
    with _Sandbox(inst):
        rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % rid)
        assert rc == 0 and out["status"] == "pending" and "hook" in out["note"], out
        assert _meta(rec)["status"] == "proposed"
        rc, again = _cli(inst, "confirm", rid, "--quote", "confirm %s" % rid)  # no second claim for the line
        assert rc == 1 and _meta(rec)["status"] == "proposed", again
    kept = (inst / BOX).read_text()
    assert fxlib.sync_dir(inst, cdir).returncode in (0, 3)  # the next hook, outside the sandbox
    assert _meta(rec)["status"] == "accepted"
    rows = _ledger_rows(inst)
    used = [r for r in rows if r.get("t") == "used" and r.get("id") == rid]
    applied = [r for r in rows if r.get("t") == "applied"]
    assert len(used) == 1 and used[0].get("claim") and [a["claim"] for a in applied] == [used[0]["eid"]], rows
    assert rows.index(used[0]) < rows.index(applied[0])
    # replay: flip the record back and restore the drained claim; nothing re-applies it
    rec.write_text(rec.read_text().replace('status: "accepted"', 'status: "proposed"', 1))
    (inst / BOX).write_text(kept)
    assert fxlib.sync_dir(inst, cdir).returncode in (0, 3)
    assert _meta(rec)["status"] == "proposed"


def test_n1_a_deleted_pending_claim_confirms_nothing(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    _review(inst, rid)
    _say(inst, cdir, path, "confirm %s" % rid)
    with _Sandbox(inst):
        rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % rid)
        assert out["status"] == "pending", out
    (inst / BOX).unlink()
    assert fxlib.sync_dir(inst, cdir).returncode in (0, 3)
    assert _meta(rec)["status"] == "proposed"


def test_n1_one_message_captured_twice_answers_one_presentation_once(tmp_path):
    """Live run 2026-09-29 (Codex): the operator's "confirm" was both a journal line and a captured turn (two
    refs), and each was consumed separately. A presentation now takes one answer."""
    inst, cdir, path, rec, rid = _material(tmp_path)
    _review(inst, rid)
    _say(inst, cdir, path, "confirm %s" % rid)
    from test_brain_provenance_adversarial import SID
    r = fxlib.cli(inst, "hook", "prompt", stdin=json.dumps({"session_id": SID, "prompt": "confirm %s" % rid}))
    assert r.returncode == 0, r.stderr
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % rid)
    assert rc == 0 and out["status"] == "accepted", out
    rec.write_text(rec.read_text().replace('status: "accepted"', 'status: "proposed"', 1))  # a repo writer
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % rid)
    assert rc == 1 and _meta(rec)["status"] == "proposed", out


# R7 remainder -----------------------------------------------------------------------------------------

RID, ALIAS = "D-20260929-1412-pricing", "D-0929-pricing"

REFUSED = [
    "If legal approves:\nconfirm D-0929-pricing",
    "if legal approves\n\nconfirm D-0929-pricing",
    "Looks right to me.\nconfirm D-0929-pricing",
    "confirm D-0929-pricing\nfor now",
    "```\nconfirm D-0929-pricing\n```",
    "Example:\n```\nconfirm D-0929-pricing\n```",
    "> confirm D-0929-pricing",
    "Reply like this:\n> confirm D-0929-pricing",
    "If legal approves:\n- confirm D-0929-pricing",
    "- confirm D-0929-pricing",
    "1. confirm D-0929-pricing",
    "confirm D-0929-pricing\nconfirm D-0929-pricing",
    "confirm D-0929-pricing\nconfirm D-20260929-1412-pricing",
    '"If legal approves:\nconfirm D-0929-pricing"',
]
ACCEPTED = [
    "confirm D-0929-pricing",
    "  confirm D-0929-pricing  \n",
    "yes, confirm D-0929-pricing",
    "accept D-0929-pricing.",
    '"confirm D-0929-pricing"',
    "“confirm D-0929-pricing”.",
    "confirm D-0929-pricing\nconfirm D-0929-other",
    "confirm D-0929-other\n\naccept D-0929-pricing",
]


@pytest.mark.parametrize("text", REFUSED)
def test_r7_a_directive_inside_a_larger_message_does_not_confirm(text):
    assert confirm.intent(text, RID, "confirm", ALIAS) != "", text


@pytest.mark.parametrize("text", ACCEPTED)
def test_r7_whole_message_directives_still_confirm(text):
    assert confirm.intent(text, RID, "confirm", ALIAS) == "", text


@pytest.mark.parametrize("text,ok", [
    ("If they object:\nreject D-0929-pricing", False), ("> reject D-0929-pricing", False),
    ("reject D-0929-pricing: wrong number.", True), ("reject D-0929-pricing\nreject D-0929-other", True),
])
def test_r7_rejections_need_the_whole_message_too(text, ok):
    assert (confirm.intent(text, RID, "reject", ALIAS) == "") is ok, text


def test_r7_a_two_line_conditional_does_not_confirm_end_to_end(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    short = _review(inst, rid)["short_id"]
    _say(inst, cdir, path, "If legal approves:\nconfirm %s" % short)
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % short)
    assert rc == 1 and _meta(rec)["status"] == "proposed", out
    _say(inst, cdir, path, "confirm %s" % short)
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % short)
    assert rc == 0 and out["status"] == "accepted", out
