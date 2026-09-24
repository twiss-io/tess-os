"""Journal: deterministic, redacted, one file per session, append-only (spec 9.4)."""
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

sys.path.insert(0, str(Path(fxlib.REPO) / "scripts" / "brain"))
from brainlib import journal  # noqa: E402
from brainlib.config import Config  # noqa: E402

JOURNAL = "brain/journal/2026/09/24/1405-claude-11111111.md"


@pytest.fixture
def inst(tmp_path):
    return Path(fxlib.make(str(tmp_path / "fx")))


def _synced(inst):
    r = fxlib.sync_fixture(inst)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def test_one_file_per_session_and_daily_index(inst):
    out = _synced(inst)
    assert out["journaled"] == 3
    files = sorted(p.name for p in (inst / "brain/journal/2026/09/24").glob("*.md"))
    assert files == ["1000-claude-22222222.md", "1405-claude-11111111.md", "1520-codex-01a0d238.md"]
    daily = (inst / "brain/journal/2026/09/2026-09-24.md").read_text()
    assert "generated: true" in daily and "1405-claude-11111111" in daily


def test_second_run_is_byte_identical(inst):
    _synced(inst)
    fxlib.commit_all(inst, "run 1")
    _synced(inst)
    st = fxlib.run(str(inst), "status", "--porcelain").stdout
    assert st == "", st


def test_messages_verbatim_redacted_and_injected_channels_skipped(inst):
    _synced(inst)
    text = (inst / JOURNAL).read_text()
    assert "[L1 14:05 probe cli] Decision: let's go with Postgres for the ledger." in text
    assert "blue logo" not in text and "let's ship it tonight" not in text  # plugin-injected: not journaled
    assert "<REDACTED:nric>" in text and "<REDACTED:card>" in text
    assert not re.search(r"[STFGM]\d{7}[A-Z]", text)
    assert "system-reminder" not in text and "always dispatch" not in text
    assert "[L2 14:12 probe cli] /wake" in text
    assert "Request interrupted" not in text


def test_front_matter_and_marker(inst):
    _synced(inst)
    text = (inst / JOURNAL).read_text()
    assert text.startswith("---\nschema: 1\ntype: \"journal-session\"\nruntime: \"claude\"")
    assert re.search(r"<!-- tess:session runtime=claude id=11111111-aaaa-4bbb-8ccc-000000000001 through=\d+ -->", text)
    assert 'speakers: ["probe"]' in text
    assert "external_context: false" in text
    ext = (inst / "brain/journal/2026/09/24/1000-claude-22222222.md").read_text()
    assert "external_context: true" in ext


def test_planted_token_redacted_everywhere(inst, tmp_path):
    token = fxlib.planted_github_token()
    cdir = tmp_path / "claude"
    shutil.copytree(fxlib.CLAUDE_DIR, cdir)
    extra = {"type": "user", "sessionId": "33333333-aaaa-4bbb-8ccc-000000000003", "cwd": "/work/fx",
             "timestamp": "2026-09-24T08:00:00.000Z", "promptSource": "typed",
             "message": {"role": "user", "content": "Here is the key %s and password: hunter2" % token}}
    (cdir / "33333333-aaaa-4bbb-8ccc-000000000003.jsonl").write_text(json.dumps(extra) + "\n")
    r = fxlib.cli(inst, "sync", "--claude-dir", str(cdir), "--codex-home", str(tmp_path / "none"))
    assert r.returncode == 0, r.stderr
    blob = "".join(p.read_text() for p in inst.rglob("*") if p.is_file() and ".git" not in p.parts)
    assert token not in blob and "hunter2" not in blob
    assert "<REDACTED:github>" in blob and "<REDACTED:credential>" in blob


def test_append_only_labels_never_move(inst, tmp_path):
    cdir = tmp_path / "claude"
    shutil.copytree(fxlib.CLAUDE_DIR, cdir)
    _ = fxlib.cli(inst, "sync", "--claude-dir", str(cdir), "--codex-home", str(tmp_path / "none"))
    before = (inst / JOURNAL).read_text()
    msgs_before = [l for l in before.splitlines() if l.startswith("[L")]
    f = cdir / "11111111-aaaa-4bbb-8ccc-000000000001.jsonl"
    rec = {"type": "user", "sessionId": "11111111-aaaa-4bbb-8ccc-000000000001", "cwd": "/work/fx",
           "timestamp": "2026-09-24T06:30:00.000Z", "promptSource": "typed",
           "message": {"role": "user", "content": "One more thing for later."}}
    with open(f, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    fxlib.cli(inst, "sync", "--claude-dir", str(cdir), "--codex-home", str(tmp_path / "none"))
    after = (inst / JOURNAL).read_text()
    msgs_after = [l for l in after.splitlines() if l.startswith("[L")]
    assert msgs_after[: len(msgs_before)] == msgs_before
    assert msgs_after[-1] == "[L3 14:30 probe cli] One more thing for later."


def test_split_at_size_limit(inst, monkeypatch):
    cfg = Config(inst)
    from brainlib.parsers import claude
    sess = claude.parse(Path(fxlib.CLAUDE_DIR) / "11111111-aaaa-4bbb-8ccc-000000000001.jsonl")
    monkeypatch.setattr(journal, "SPLIT_BYTES", 300)
    parts = journal.render(cfg, sess, [], "abc")
    assert len(parts) >= 2
    assert parts[1][0].endswith("1405-claude-11111111-2.md")
    labels = [re.findall(r"^\[(L\d+|R\d+) ", p[1], re.M) for p in parts]
    flat = [x for ls in labels for x in ls]
    assert len(flat) == len(set(flat))  # every entry in exactly one part


def test_stub_only_keeps_body_local(tmp_path):
    bj = json.loads(Path(fxlib.HERE, "brain.json").read_text())
    bj["capture"]["journal"] = "stub-only"
    p = tmp_path / "bj.json"
    p.write_text(json.dumps(bj))
    inst = Path(fxlib.make(str(tmp_path / "fx"), brain_json=str(p)))
    _synced(inst)
    stub = (inst / JOURNAL).read_text()
    assert "stub: true" in stub and "Postgres" not in stub and "## Messages" not in stub
    local = (inst / ".tess/state/brain" / JOURNAL[len("brain/"):]).read_text()
    assert "Postgres for the ledger" in local
    assert (inst / ".tess/state/brain/.gitignore").read_text() == "*\n"
    assert fxlib.cli(inst, "lint").returncode == 0


def test_cursor_falls_back_to_marker(inst):
    _synced(inst)
    (inst / ".tess/state/brain/cursors.json").unlink()
    out = _synced(inst)
    assert out["candidates"] == 0 or all(o["status"] == "noop" for o in out["outcomes"])
