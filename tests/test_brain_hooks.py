"""Hook handlers (spec 9.6, acceptance L9): fast, bounded, fail-open, silent
where they must be."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

STDIN = Path(fxlib.HERE) / "stdin"


@pytest.fixture
def inst(tmp_path):
    return Path(fxlib.make(str(tmp_path / "fx")))


def _hook(root, event, runtime="claude", stdin="{}", env=None):
    t0 = time.monotonic()
    r = fxlib.cli(root, "hook", event, "--runtime", runtime, stdin=stdin, env=env)
    return r, time.monotonic() - t0


def _big(inst, n=1000):
    d = inst / "brain" / "kb" / "research"
    d.mkdir(parents=True)
    for i in range(n):
        (d / ("note-%04d.md" % i)).write_text("# Note %d\n\nplain research text\n" % i)


def test_session_start_snapshot_is_json_bounded_and_fast(inst):
    _big(inst)
    fxlib.sync_fixture(inst)
    r, dt = _hook(inst, "session-start", stdin=(STDIN / "session_start.json").read_text())
    assert r.returncode == 0
    assert dt <= 2.0, dt
    data = json.loads(r.stdout)
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert len(ctx.encode("utf-8")) <= 4096
    assert "brain/START-HERE.md" in ctx
    assert "1000 unreachable" in ctx or "unreachable" in ctx


def test_session_start_reports_learning_since_last_session(inst):
    _hook(inst, "session-start")
    fxlib.sync_fixture(inst)
    r, _ = _hook(inst, "session-start")
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "Since last session I learned" in ctx


def test_nonce_is_echoed_for_smokes(inst):
    r, _ = _hook(inst, "session-start", env={"TESS_BRAIN_TEST_NONCE": "LEARN-NONCE-3K"})
    assert "LEARN-NONCE-3K" in r.stdout


def test_silent_in_source_repo_and_when_quiet(inst):
    r = subprocess.run([sys.executable, fxlib.TESSBRAIN, "hook", "session-start", "--runtime", "claude"],
                       input="{}", capture_output=True, text=True, cwd=fxlib.REPO)
    assert r.returncode == 0 and r.stdout == ""
    for var in ("TESS_BRAIN_QUIET", "TESS_HEADLESS"):
        r, _ = _hook(inst, "session-start", env={var: "1"})
        assert r.returncode == 0 and r.stdout == ""


def test_silent_without_brain_json(tmp_path):
    (tmp_path / "plain").mkdir()
    r, _ = _hook(tmp_path / "plain", "session-start")
    assert r.returncode == 0 and r.stdout == ""
    assert not (tmp_path / "plain" / ".tess").exists()


def test_garbage_stdin_fails_open_and_is_counted(inst):
    for event in ("session-start", "prompt", "stop"):
        before = _errors(inst)
        r, _ = _hook(inst, event, stdin="{not json")
        assert r.returncode == 0
        assert _errors(inst) == before + 1
    s = fxlib.cli(inst, "status", "--json")
    assert json.loads(s.stdout)["errors"] >= 3


def _errors(inst):
    p = inst / ".tess/state/brain/errors.log"
    return len(p.read_text().splitlines()) if p.exists() else 0


def test_stop_returns_fast_and_journals_in_background(inst, tmp_path):
    src = Path(fxlib.CLAUDE_DIR) / "11111111-aaaa-4bbb-8ccc-000000000001.jsonl"
    data = json.loads((STDIN / "stop.json").read_text())
    data["transcript_path"] = str(src)
    r, dt = _hook(inst, "stop", stdin=json.dumps(data))
    assert r.returncode == 0 and dt <= 1.0, dt
    target = inst / "brain/journal/2026/09/24/1405-claude-11111111.md"
    for _ in range(100):
        if target.exists() and (inst / "brain/learned.md").exists():
            break
        time.sleep(0.1)
    assert target.exists()
    sessions = json.loads((inst / ".tess/state/brain/sessions.json").read_text())
    assert sessions["11111111-aaaa-4bbb-8ccc-000000000001"]["transcript_path"] == str(src)


def test_codex_stop_prints_json(inst):
    r, _ = _hook(inst, "stop", runtime="codex", stdin=(STDIN / "stop.json").read_text())
    assert r.stdout.strip() == "{}"


def test_prompt_nudge_is_at_most_two_lines(inst):
    r, _ = _hook(inst, "prompt", stdin=(STDIN / "prompt.json").read_text())
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx.count("\n") <= 1
    assert "possible preference" in ctx


def test_distill_reminder_every_ten_principal_turns(inst):
    outs = []
    for i in range(10):
        d = {"session_id": "s", "prompt": "Plain status question number %d." % i}
        r, _ = _hook(inst, "prompt", stdin=json.dumps(d))
        outs.append(r.stdout)
    assert all("distill" not in o for o in outs[:9])
    assert "10 turns since last distill" in outs[9]
    fxlib.cli(inst, "distilled")
    r, _ = _hook(inst, "prompt", stdin=json.dumps({"prompt": "One more plain question."}))
    assert "distill" not in r.stdout


def test_hooks_never_write_git(inst):
    head = fxlib.run(str(inst), "rev-parse", "HEAD").stdout
    for event in ("session-start", "prompt", "stop"):
        _hook(inst, event, stdin=(STDIN / ("%s.json" % event.replace("-", "_"))).read_text()
              if event != "session-start" else (STDIN / "session_start.json").read_text())
    time.sleep(0.5)
    assert fxlib.run(str(inst), "rev-parse", "HEAD").stdout == head
