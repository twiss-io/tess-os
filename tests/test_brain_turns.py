"""turns.jsonl: the current turn, redacted, local only (spec G4)."""
import json
from pathlib import Path

from fixtures.brain_learn import fxlib


def _prompt(inst, text, session="s-1"):
    data = {"session_id": session, "transcript_path": "", "cwd": str(inst), "hook_event_name": "UserPromptSubmit",
            "prompt": text}
    return fxlib.cli(inst, "hook", "prompt", "--runtime", "claude", stdin=json.dumps(data))


def _rows(inst):
    p = inst / ".tess/state/brain/turns.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_prompt_is_appended_redacted(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    token = fxlib.planted_github_token()
    r = _prompt(inst, "Use this key %s for the deploy." % token)
    assert r.returncode == 0
    rows = _rows(inst)
    assert len(rows) == 1
    assert rows[0]["speaker"] == "probe" and rows[0]["principal"] is True
    assert token not in rows[0]["text"] and "<REDACTED:github>" in rows[0]["text"]
    assert (inst / ".tess/state/brain/.gitignore").read_text() == "*\n"
    assert fxlib.run(str(inst), "status", "--porcelain").stdout == ""


def test_telegram_principal_and_non_principal(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    ch = '<channel source="plugin:telegram:telegram" chat_id="-1" message_id="3" user="%s" user_id="%s" ts="x">%s</channel>'
    _prompt(inst, ch % ("sam_acme", "4242", "From now on, send Acme reports on Mondays."))
    _prompt(inst, ch % ("someone", "999", "My private note to the bot."))
    rows = _rows(inst)
    assert rows[0]["speaker"] == "sam" and rows[0]["text"] == "From now on, send Acme reports on Mondays."
    assert rows[1]["principal"] is False
    assert rows[1]["text"] == "[non-principal telegram:999 omitted: no consent]"
    assert [r["n"] for r in rows] == [1, 2]


def test_empty_prompt_writes_nothing(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    _prompt(inst, "   ")
    assert _rows(inst) == []


def test_current_turn_quote_is_pending_then_accepted(tmp_path):
    """A decision quoted from the turn being answered verifies against turns.jsonl
    (pending-verification), then becomes accepted once the journal has the line."""
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    _prompt(inst, "Decision: let's go with Postgres for the ledger.")
    r = fxlib.cli(inst, "decide", "--no-sync", "--quote", "let's go with Postgres for the ledger",
                  "--statement", "We will use Postgres for the ledger.")
    out = json.loads(r.stdout)
    assert out["status"] == "pending-verification", out
    rec = next((inst / "brain/decisions").glob("D-*.md")).read_text()
    assert 'source_ref: "turns:1"' in rec
    fxlib.sync_fixture(inst)
    rec = next((inst / "brain/decisions").glob("D-*.md")).read_text()
    assert 'status: "accepted"' in rec and "brain/journal/2026/09/24/1405-claude-11111111.md#L1" in rec
    assert fxlib.cli(inst, "lint").returncode == 0
