"""Fix round 4 (V12 settle rule): a distilled decision is a CANDIDATE, never accepted from wording alone.

The QA verifier's adversarial transcripts (all fictional): every one starts with
"Let's go with Postgres for the ledger." and later moves to SQLite in a wording
the phrase lists of round 3 did not know ("No wait, SQLite.", "Make it SQLite.",
the assistant offering "Want me to switch the ledger to SQLite?" and the operator
saying "Yes please."). Postgres must never be ACCEPTED in any of them, while a
true single decision still is. Then the rule's own parts: the settle window,
learn.auto_accept off, an explicit confirmation turn, START-HERE counts, lint.
"""
import json
import os
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

PG = "Let's go with Postgres for the ledger."


def _write(path, sid, recs):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    out = []
    for i, r in enumerate(recs):
        base = {"sessionId": sid, "timestamp": "2026-09-24T06:%02d:00.000Z" % i, "cwd": "/work/fx",
                "version": "2.1.281", "gitBranch": "main", "uuid": "q-%s-%d" % (sid[:4], i), "isSidechain": False}
        kind, payload = r
        if kind == "user":
            base.update(type="user", promptSource="typed", message={"role": "user", "content": payload})
        elif kind == "assistant":
            base.update(type="assistant", message={"role": "assistant", "content": [{"type": "text", "text": payload}]})
        elif kind == "tool_use":
            base.update(type="assistant", message={"role": "assistant", "content": [
                {"type": "tool_use", "id": "toolu_%d" % i, "name": "Bash", "input": {"command": payload}}]})
        elif kind == "tool_result":
            base.update(type="user", message={"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_%d" % (i - 1), "content": payload}]})
        out.append(json.dumps(base))
    Path(path).write_text("\n".join(out) + "\n")


def _run(tmp_path, recs, sid="qa000001-aaaa-4bbb-8ccc-000000000001", env=None, learn=None):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    if learn is not None:
        bj = inst / "brain" / "brain.json"
        data = json.loads(bj.read_text())
        data["learn"] = learn
        bj.write_text(json.dumps(data, indent=2))
    cdir = tmp_path / "claude"
    _write(cdir / (sid + ".jsonl"), sid, recs)
    r = fxlib.sync_dir(inst, cdir, env=env)
    assert r.returncode in (0, 3), r.stdout + r.stderr
    return inst, r


def _inbox(inst, word):
    return [c for c in (json.loads(p.read_text()) for p in (inst / "brain/inbox").glob("C-*.json"))
            if word in c["quote"]]


def _accepted(inst):
    return "\n".join(p.read_text() for p in (inst / "brain").rglob("D-*.md") if 'status: "accepted"' in p.read_text())


def _all_written(inst):
    return "\n".join(p.read_text(errors="replace") for p in (inst / "brain").rglob("*") if p.is_file())


# T1: "no wait" reversals (no "actually/instead", no "No," with punctuation)
T1 = ["No wait, SQLite.", "Wait, make it SQLite.", "No wait — SQLite for the ledger.", "Hmm no. SQLite.",
      "Ugh, Postgres is overkill here. SQLite.", "We should use SQLite for the ledger."]

# T2: switch across a tool call
T2 = ["Hmm, on second thought, SQLite.", "Hmm. That container is too heavy; SQLite for the ledger."]

# T3: assistant proposes the switch, operator approves tersely
T3 = ["Yes please.", "Yep, SQLite.", "Sure, SQLite then.", "Do it.", "ok switch"]


@pytest.mark.parametrize("later", T1)
def test_t1_no_wait_reversal(tmp_path, later):
    inst, _ = _run(tmp_path, [("user", PG), ("assistant", "Noted."), ("user", later)])
    assert "Postgres" not in _accepted(inst), (later, _accepted(inst))


@pytest.mark.parametrize("later", T2)
def test_t2_switch_across_tool_call(tmp_path, later):
    inst, _ = _run(tmp_path, [("user", PG), ("tool_use", "docker run -d postgres:16"),
                              ("tool_result", "Unable to find image 'postgres:16' locally ... 412MB"),
                              ("assistant", "Postgres container is up (412MB)."), ("user", later)])
    assert "Postgres" not in _accepted(inst), (later, _accepted(inst))


@pytest.mark.parametrize("later", T3)
def test_t3_assistant_proposed_switch_approved(tmp_path, later):
    inst, _ = _run(tmp_path, [("user", PG), ("assistant",
                   "For one user, SQLite would be simpler than Postgres. Want me to switch the ledger to SQLite?"),
                              ("user", later)])
    assert "Postgres" not in _accepted(inst), (later, _accepted(inst))


def test_control_single_decision_accepted(tmp_path):
    inst, _ = _run(tmp_path, [("user", PG), ("assistant", "Noted."), ("user", "Thanks.")])
    assert "Postgres" in _accepted(inst)


@pytest.mark.parametrize("hypo", ["What if we used MongoDB for the ledger?", "What if we used MongoDB for the ledger.",
                                  "Suppose we go with MongoDB for the ledger.", "Let's say we use MongoDB for the ledger.",
                                  "We could go with MongoDB for the ledger.", "Maybe let's use MongoDB for the ledger."])
def test_hypothetical_never_accepted(tmp_path, hypo):
    inst, _ = _run(tmp_path, [("user", hypo), ("assistant", "Could work."), ("user", "Thanks.")])
    acc = _accepted(inst)
    assert "MongoDB" not in acc, (hypo, acc)


def test_secret_redacted_before_write(tmp_path):
    tok = "ghp_" + "".join(chr(65 + (i * 7) % 26) for i in range(36))  # built at runtime
    aws = "AKIA" + "".join(chr(65 + (i * 3) % 26) for i in range(16))
    inst, r = _run(tmp_path, [("user", "Decision: let's use the deploy token %s for CI." % tok),
                              ("user", "Also the key is %s ok" % aws), ("assistant", "echo %s" % tok)])
    blob = _all_written(inst) + r.stdout + r.stderr
    assert tok not in blob and tok[4:] not in blob
    assert aws not in blob


def test_every_accepted_has_real_source_ref(tmp_path):
    inst, _ = _run(tmp_path, [("user", PG), ("assistant", "Noted."), ("user", "From now on, always answer in bullets."),
                              ("user", "Thanks.")])
    recs = [p for p in (inst / "brain").rglob("*.md") if 'status: "accepted"' in p.read_text()]
    assert recs
    for p in recs:
        t = p.read_text()
        ref = [l for l in t.splitlines() if l.startswith("source_ref:")][0].split(":", 1)[1].strip().strip('"')
        path, _, anchor = ref.partition("#")
        jf = inst / path
        assert jf.is_file(), ref
        assert anchor and anchor in jf.read_text(), ref
        quote = [l for l in t.splitlines() if l.startswith("source_quote:")][0].split(":", 1)[1].strip().strip('"')
        assert quote.replace('\\"', '"') in jf.read_text(), (quote, ref)


# -- the settle rule's own parts ------------------------------------------------------------------

NOTED = [("user", PG), ("assistant", "Noted."), ("user", "Thanks.")]  # transcript ends 06:02Z (14:02 SGT)


def test_clean_decision_waits_until_the_session_settles(tmp_path):
    inst, _ = _run(tmp_path, NOTED, env={"TESS_BRAIN_NOW": "2026-09-24T14:10:00+08:00"})
    assert "Postgres" not in _accepted(inst)
    held = _inbox(inst, "Postgres")
    assert held and held[0]["verification"]["status"] == "waiting", held
    start = (inst / "brain/START-HERE.md").read_text()
    assert "1 decision awaiting review (not accepted)" in start and "Postgres" not in start
    r = fxlib.sync_dir(inst, tmp_path / "claude", env={"TESS_BRAIN_NOW": "2026-09-24T14:40:00+08:00"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Postgres" in _accepted(inst) and not _inbox(inst, "Postgres")
    assert fxlib.cli(inst, "lint").returncode == 0


def test_settle_minutes_is_configurable(tmp_path):
    inst, _ = _run(tmp_path, NOTED, env={"TESS_BRAIN_NOW": "2026-09-24T14:10:00+08:00"},
                   learn={"settle_minutes": 5})
    assert "Postgres" in _accepted(inst)


def test_auto_accept_off_sends_every_decision_to_review(tmp_path):
    inst, _ = _run(tmp_path, NOTED, learn={"auto_accept": "off"})
    assert "Postgres" not in _accepted(inst)
    held = _inbox(inst, "Postgres")
    assert held and "auto_accept is off" in held[0]["verification"]["reasons"][0]


def test_yes_to_an_assistant_question_restating_the_decision_confirms_it(tmp_path):
    inst, _ = _run(tmp_path, [("user", PG), ("assistant", "Want me to set up Postgres for the ledger?"),
                              ("user", "Yes."), ("assistant", "Done.")])
    acc = _accepted(inst)
    assert "Postgres" in acc and "confirmed: true" in acc and 'confirmed_ref: "brain/journal/' in acc


def test_agreed_assistant_alternative_supersedes_the_earlier_choice(tmp_path):
    inst, _ = _run(tmp_path, [("user", PG), ("assistant", "SQLite would be simpler here. Should I use it instead?"),
                              ("user", "Yes please.")])
    assert "Postgres" not in _accepted(inst)
    reason = _inbox(inst, "Postgres")[0]["verification"]["reasons"][0]
    assert reason.startswith("V12") and "supersedes the earlier choice" in reason, reason


def test_indexes_list_only_accepted_decisions_plus_a_count(tmp_path):
    inst, _ = _run(tmp_path, [("user", PG), ("assistant", "Noted."), ("user", "No wait, SQLite.")])
    for page in ("START-HERE.md", "decisions/INDEX.md"):
        text = (inst / "brain" / page).read_text()
        assert "Postgres" not in text, page
        assert "1 decision awaiting review (not accepted)" in text, page


def _hand_accept(inst, quote, label, confirmed):
    import sys
    sys.path.insert(0, str(Path(fxlib.REPO) / "scripts" / "brain"))
    from brainlib import records
    from brainlib.config import Config
    cfg = Config(inst)
    journal = Path(fxlib.journal_of(inst, "qa000001-aaaa-4bbb-8ccc-000000000001")).relative_to(inst).as_posix()
    m = {"id": "D-20260924-1400-hand", "type": "decision", "title": quote, "status": "accepted",
         "source_quote": quote, "source_at": "2026-09-24T14:00:00+08:00", "source_ref": "%s#%s" % (journal, label),
         "decided_by": "probe", "confirmed": confirmed}
    rec = records.write(cfg, "decision", inst / "brain/decisions", m, {"quote": quote})
    records.update_fields(rec, {})
    fxlib.cli(inst, "index")


def test_lint_fails_on_an_accepted_decision_with_a_later_same_topic_candidate(tmp_path):
    inst, _ = _run(tmp_path, [("user", PG), ("assistant", "Noted."),
                              ("user", "Let's go with SQLite for the ledger if the budget allows.")])
    assert _inbox(inst, "SQLite")  # the later candidate waits for review (conditional)
    _hand_accept(inst, "Let's go with Postgres for the ledger", "L1", confirmed=True)
    r = fxlib.cli(inst, "lint")
    assert r.returncode == 1 and "later candidate on the same topic" in r.stdout, r.stdout


def test_lint_fails_on_an_unconfirmed_accepted_decision_with_later_doubt(tmp_path):
    inst, _ = _run(tmp_path, [("user", PG), ("assistant", "Noted."), ("user", "Hmm no. SQLite.")])
    _hand_accept(inst, "Let's go with Postgres for the ledger", "L1", confirmed=False)
    r = fxlib.cli(inst, "lint")
    assert r.returncode == 1 and "accepted without confirmation, but V12" in r.stdout, r.stdout
