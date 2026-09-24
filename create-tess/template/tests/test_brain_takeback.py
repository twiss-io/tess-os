"""Fix round 2: a decision the principal takes back is never recorded as accepted.

Covers the 18 take-back phrasings from the independent verifier (same message
and next message), content-free corrections, conditional decisions, a
push URL that differs from the fetch URL, front-matter tampering, the added
redaction shapes, and the over-cap report. Planted secrets are built at run time.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

sys.path.insert(0, str(Path(fxlib.REPO) / "scripts" / "brain"))
from brainlib import redact, takeback  # noqa: E402

DECISION = "Decision: let's go with Heroku for hosting."
TAKEBACKS = [
    "Actually no.", "Wait, no.", "I changed my mind.", "Cancel that.", "On second thought, no.",
    "Hmm, not Heroku after all.", "Let me rethink that.", "Forget Heroku, that was a bad idea.",
    "No, don't do that.", "Hold off on that.", "Ignore my last message.", "That is not a decision.",
    "It is not a decision, I was just brainstorming.", "No, that was not a decision.", "Scratch that.",
    "Never mind.", "Just kidding.", "Actually no, I changed my mind, not Heroku.",
]
KEPT_AFTER = [  # later sentences with their own substance: the decision stands
    "From now on, always answer in bullet points.",
    "No, that's wrong: the client's timezone is SGT, not UTC.",
    "Remind me to send the pricing note to Sam by Friday.",
    "No, keep the old data.",
]


@pytest.mark.parametrize("later", TAKEBACKS)
def test_every_take_back_phrasing_is_detected(later):
    target = "let's go with Heroku for hosting"
    assert takeback.taken_back(target, later, ""), "same message: " + later
    assert takeback.taken_back(target, "", later), "next message: " + later


@pytest.mark.parametrize("later", KEPT_AFTER)
def test_a_later_sentence_about_something_else_leaves_the_decision(later):
    assert not takeback.taken_back("let's go with Heroku for hosting", later, "")


def test_bare_take_back_only_reaches_the_sentence_just_before_it():
    rest = "If we went with CouchDB instead, would that be faster?\nJust thinking out loud."
    assert not takeback.taken_back("let's go with Heroku for hosting", rest, "")


def _run(tmp_path, turns):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    cdir = tmp_path / "claude"
    sid = "tkb00001-aaaa-4bbb-8ccc-000000000001"
    fxlib.claude_session(cdir / (sid + ".jsonl"), sid, turns)
    r = fxlib.sync_dir(inst, cdir)
    assert r.returncode in (0, 3), r.stdout + r.stderr
    return inst


def _accepted(inst, prefix):
    return "\n".join(p.read_text() for p in (inst / "brain").rglob(prefix + "*.md")
                     if 'status: "accepted"' in p.read_text() or 'status: "active"' in p.read_text())


@pytest.mark.parametrize("later", ["Actually no, I changed my mind.", "Wait, no.", "Hold off on that."])
def test_end_to_end_same_message(tmp_path, later):
    inst = _run(tmp_path, [("user", DECISION + " " + later)])
    assert "Heroku" not in _accepted(inst, "D-")
    assert fxlib.cli(inst, "lint").returncode == 0


@pytest.mark.parametrize("later", ["That is not a decision.", "Forget Heroku, that was a bad idea.",
                                   "Ignore my last message."])
def test_end_to_end_next_message(tmp_path, later):
    inst = _run(tmp_path, [("user", DECISION), ("user", later)])
    assert "Heroku" not in _accepted(inst, "D-")


def test_late_take_back_after_promotion_goes_to_proposed(tmp_path):
    inst = _run(tmp_path, [("user", DECISION)])
    assert "Heroku" in _accepted(inst, "D-")
    cdir = tmp_path / "claude"
    sid = "tkb00001-aaaa-4bbb-8ccc-000000000001"
    fxlib.claude_session(cdir / (sid + ".jsonl"), sid, [("user", "Wait, no.")], start_minute=30)
    r = fxlib.sync_dir(inst, cdir)
    assert r.returncode == 0, r.stderr
    assert "Heroku" not in _accepted(inst, "D-")
    assert any(h["status"] == "proposed" for h in json.loads(r.stdout)["held"])


def test_content_free_correction_and_conditionals_go_to_review(tmp_path):
    inst = _run(tmp_path, [("user", "No, don't do that."),
                           ("user", "Let's go with CouchDB for the ledger if the benchmark passes."),
                           ("user", "Decision: let's go with Redis for the cache or not"),
                           ("user", "Decision: let's go with Postgres for the ledger.")])
    assert "don't do that" not in _accepted(inst, "C-")
    assert "don't do that" not in (inst / "brain/profile.md").read_text()
    accepted = _accepted(inst, "D-")
    assert "CouchDB" not in accepted and "Redis" not in accepted and "Postgres for the ledger" in accepted
    held = [json.loads(p.read_text()) for p in (inst / "brain/inbox").glob("C-*.json")]
    assert sum(1 for c in held if "conditional" in " ".join(c["verification"]["reasons"])) == 2


def test_front_matter_tamper_fails_lint(tmp_path):
    inst = _run(tmp_path, [("user", "Decision: let's go with Postgres for the ledger.")])
    rec = next(p for p in (inst / "brain/decisions").glob("D-*.md"))
    assert fxlib.cli(inst, "lint").returncode == 0
    text = rec.read_text()
    title = [l for l in text.splitlines() if l.startswith("title:")][0]
    rec.write_text(text.replace(title, 'title: "use CouchDB for the ledger"'))
    r = fxlib.cli(inst, "lint")
    assert r.returncode == 1 and "meta_sha256" in r.stdout + r.stderr


def test_push_url_is_what_gets_checked(tmp_path):
    bj = json.loads(Path(fxlib.HERE, "brain.json").read_text())
    bj["save"]["autopush"] = True
    p = tmp_path / "bj.json"
    p.write_text(json.dumps(bj))
    inst = Path(fxlib.make(str(tmp_path / "fx"), brain_json=str(p)))
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    fxlib.run(str(inst), "remote", "add", "origin", str(bare))
    fw = tmp_path / "github.com" / "twiss-io" / "tess-os.git"
    subprocess.run(["git", "init", "-q", "--bare", str(fw)], check=True)
    fxlib.run(str(inst), "config", "remote.origin.pushurl", str(fw))
    fxlib.sync_fixture(inst)
    r = fxlib.cli(inst, "--json", "save", "-m", "probe")
    out = json.loads(r.stdout)
    assert out["pushed"] is False and any("framework repo" in n for n in out["notes"]), out
    assert subprocess.run(["git", "-C", str(fw), "rev-parse", "-q", "--verify", "main"],
                          capture_output=True).returncode != 0


def _shapes():
    hx = "0123456789abcdef"
    return {
        "slack-webhook": "https://hooks.slack.com/services/T" + "A" * 8 + "/B" + "B" * 8 + "/" + "c" * 24,
        "npm": "npm_" + "a1B2" * 9,
        "sendgrid": "SG." + "x" * 22 + "." + "y" * 43,
        "twilio": "SK" + hx * 2,
        "azure": "AccountName=foo;AccountKey=" + "Ab1+" * 21 + "==",
        "gcp": '"private_key_id": "' + hx * 2 + '12345678"',
        "nric-lower": "s" + "1234567" + "d",
        "said": "my password is " + "hunter" + "22",
        "aws-said": "the aws secret is " + "wJalrXUtnFEMI" + "K7MDENGbPxRfiCY" + "EXAMPLEKEY12",
    }


@pytest.mark.parametrize("name", sorted(_shapes()))
def test_added_credential_shapes_are_redacted(name):
    value = _shapes()[name]
    out, counts = redact.redact("note: " + value + " end")
    assert counts and "<REDACTED:" in out, (name, out)


@pytest.mark.parametrize("prose", ["the token is expired", "the password is required", "we use Heroku"])
def test_prose_is_left_alone(prose):
    assert redact.redact(prose) == (prose, {})


def test_over_cap_hold_is_reported(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    inbox = inst / "brain/inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "C-20260924-1400-01.json").write_text(json.dumps({"id": "C-20260924-1400-01", "verification": {
        "status": "review", "reasons": ["brain/profile.md would be over its cap (12300 B > 12288 B)"]}}))
    st = json.loads(fxlib.cli(inst, "status", "--json").stdout)
    assert any("consolidate: brain-review --consolidate" in b for b in st["budgets"]), st["budgets"]
