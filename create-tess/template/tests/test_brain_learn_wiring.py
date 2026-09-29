"""v1.0 learning loop: hook wiring and pinning in BOTH runtimes.

Claude Code (.claude/settings.json, byte-identical to .tess/core/settings-core.json)
and Codex (.codex/config.toml, byte-identical to its core template) run the
learning loop's hooks, and every brain hook goes through
.claude/hooks/run-pinned.py with `--closure scripts/brain`. The tests below run
the exact shipped command lines, end to end, in a copy of the pinned tree:
a prompt is captured, a Stop journals the transcript and records the decision,
a tampered or extra module is refused with a warning (never run), and no hook
ever blocks the user's turn.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

tomllib = pytest.importorskip("tomllib", reason="tomllib needs Python 3.11+ (the Codex wiring is TOML)")

from fixtures.brain_learn import fxlib

REPO = Path(fxlib.REPO)
SETTINGS = json.loads((REPO / ".tess/core/settings-core.json").read_text())
CODEX_TOML = (REPO / ".codex/config.toml").read_text()
CODEX = tomllib.loads(CODEX_TOML)
LAUNCH = 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/run-pinned.py" --on-fail warn --closure scripts/brain -- '
EVENTS = {"SessionStart": "session-start", "UserPromptSubmit": "prompt", "Stop": "stop", "SessionEnd": "stop"}
SID = "wir00001-aaaa-4bbb-8ccc-000000000001"
DECISION = "Decision: let's use Postgres for the ledger."


def _cmds(hooks: dict, event: str) -> list:
    return [h["command"] for g in hooks.get(event, []) for h in g.get("hooks", [])]


def _brain_cmds(hooks: dict, event: str) -> list:
    return [c for c in _cmds(hooks, event) if "scripts/brain/" in c]


# --- static wiring -------------------------------------------------------------------------------

@pytest.mark.parametrize("event,arg", sorted(EVENTS.items()))
def test_claude_runs_the_learning_hook_through_the_launcher(event, arg):
    want = LAUNCH + "scripts/brain/tessbrain.py hook %s --runtime claude" % arg
    assert want in _cmds(SETTINGS["hooks"], event)


@pytest.mark.parametrize("event,arg", sorted(EVENTS.items()))
def test_codex_runs_the_learning_hook_through_the_launcher(event, arg):
    cmds = [c for c in _brain_cmds(CODEX["hooks"], event) if "tessbrain.py" in c]
    assert len(cmds) == 1, cmds
    assert 'l="$r/.claude/hooks/run-pinned.py"' in cmds[0]
    assert ('"$l" --on-fail warn --closure scripts/brain -- scripts/brain/tessbrain.py hook %s --runtime codex'
            % arg) in cmds[0]


@pytest.mark.parametrize("hooks", [SETTINGS["hooks"], CODEX["hooks"]], ids=["claude", "codex"])
def test_every_brain_hook_is_pinned_warn_only_and_bounded(hooks):
    groups = [h for ev in hooks.values() for g in ev for h in g.get("hooks", [])]
    brain = [h for h in groups if "scripts/brain/" in h["command"]]
    assert len(brain) >= 5
    for h in brain:
        assert "run-pinned.py" in h["command"] and "--closure scripts/brain" in h["command"], h["command"]
        assert "--on-fail warn" in h["command"], "a brain hook must never block the turn"
        assert 0 < h.get("timeout", 0) <= 30


def test_live_codex_config_is_the_core_template_and_both_are_locked():
    tpl = REPO / ".tess/core/templates/agents-md/codex-config.toml.tpl"
    assert CODEX_TOML == tpl.read_text()
    lock = (REPO / ".tess/tess.lock").read_text()
    digest = "sha256:" + hashlib.sha256(tpl.read_bytes()).hexdigest()
    block = lock.split("  .tess/core/templates/agents-md/codex-config.toml.tpl:\n", 1)[1].split("\n  .", 1)[0]
    assert "base_sha: %s" % digest in block
    rendered = lock.split("  .codex/config.toml:\n", 1)[1].split("\n  ", 3)
    assert digest in "\n".join(rendered[:3])


def test_only_save_is_pre_approved_among_the_write_verbs():
    """v1.0 e2e review (S6, owner decision): `tessbrain.py save` is pre-approved in
    Claude Code so saving does not ask every time; it is a path-scoped commit of
    brain/ that still runs the git hooks and the pre-push gate. The verbs that change
    what the brain believes (confirm, promote, reject, retract) and githooks stay
    unapproved, and there is no blanket tessbrain.py rule."""
    allow = SETTINGS["permissions"]["allow"]
    assert "Bash(python3 scripts/brain/tessbrain.py save:*)" in allow
    for verb in ("confirm", "promote", "reject", "retract", "githooks"):
        assert not any("tessbrain.py %s" % verb in a for a in allow), verb
    assert "Bash(python3 scripts/brain/tessbrain.py:*)" not in allow


def test_every_brain_script_is_pinned_and_the_pin_list_is_locked():
    pins = {}
    for line in (REPO / ".tess/core/pinned-scripts.sha256").read_text().splitlines():
        if line and not line.startswith("#"):
            sha, rel = line.split(None, 1)
            pins[rel] = sha
    for p in sorted((REPO / "scripts/brain").rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(REPO).as_posix()
        assert pins.get(rel) == hashlib.sha256(p.read_bytes()).hexdigest(), "unpinned or stale: " + rel
    assert "scripts/brain/tessbrain.py" in pins
    r = subprocess.run([sys.executable, "-B", "-c",
                        "import importlib.util,sys;s=importlib.util.spec_from_file_location('rp',sys.argv[1]);"
                        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                        "print(m.verify(m.Path(sys.argv[2]),'scripts/brain/tessbrain.py','scripts/brain'))",
                        str(REPO / ".claude/hooks/run-pinned.py"), str(REPO)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip().endswith("tessbrain.py"), r.stderr


# --- end to end through the shipped command lines -------------------------------------------------

@pytest.fixture
def pinned(tmp_path):
    """A copy of the pinned tree (launcher, lock, pin list, scripts/brain) that is also a brain instance."""
    root = tmp_path / "inst"
    ign = shutil.ignore_patterns("__pycache__")
    for rel in (".claude/hooks/run-pinned.py", ".tess/tess.lock", ".tess/core/pinned-scripts.sha256"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    shutil.copytree(REPO / "scripts/brain", root / "scripts/brain", ignore=ign)
    fxlib.make(str(root))
    return root


def _env(root, **extra):
    e = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), TESS_BRAIN_NO_BACKFILL="1", TESS_BRAIN_HOOK_INLINE="1")
    none = str(root / ".no-such-home")
    e.update(CODEX_HOME=none, GEMINI_CLI_HOME=none, CLAUDE_CONFIG_DIR=none)
    e.update(extra)
    return e


def _run_hook(cmd, root, payload):
    return subprocess.run(cmd, shell=True, cwd=str(root), input=json.dumps(payload), capture_output=True,
                          text=True, env=_env(root), timeout=120)


def _transcript(tmp_path, turns):
    return fxlib.claude_session(tmp_path / "t" / (SID + ".jsonl"), SID, turns)


def _one(hooks, event):
    return [c for c in _cmds(hooks, event) if "tessbrain.py" in c][0]


def test_claude_prompt_then_stop_captures_notes_and_records(pinned, tmp_path):
    t = _transcript(tmp_path, [("user", DECISION), ("assistant", "Noted: Postgres for the ledger.")])
    base = {"session_id": SID, "transcript_path": str(t), "cwd": str(pinned)}
    r = _run_hook(_one(SETTINGS["hooks"], "UserPromptSubmit"), pinned, dict(base, prompt=DECISION))
    assert r.returncode == 0 and "TESS HOOK NOT RUN" not in r.stdout + r.stderr, r.stderr
    assert "possible decision" in r.stdout
    assert DECISION in (pinned / ".tess/state/brain/turns.jsonl").read_text()
    r = _run_hook(_one(SETTINGS["hooks"], "Stop"), pinned, base)
    assert r.returncode == 0 and "TESS HOOK NOT RUN" not in r.stderr, r.stderr
    note = Path(fxlib.journal_of(pinned, SID)).read_text()
    assert "## Summary" in note and "1 decision" in note and "[L1 " in note
    recs = [p.read_text() for p in (pinned / "brain").rglob("D-*.md")]
    assert any("Postgres" in t and 'status: "accepted"' in t for t in recs), recs


def test_codex_stop_hook_prints_json_and_records(pinned, tmp_path):
    t = _transcript(tmp_path, [("user", DECISION), ("assistant", "Noted.")])
    cmd = _one(CODEX["hooks"], "Stop").replace("--runtime codex", "--runtime claude")  # fixture is a Claude file
    r = _run_hook(cmd, pinned, {"session_id": SID, "transcript_path": str(t), "cwd": str(pinned)})
    assert r.returncode == 0, r.stderr
    assert fxlib.journal_of(pinned, SID)
    r = _run_hook(_one(CODEX["hooks"], "Stop"), pinned, {"session_id": "x", "cwd": str(pinned)})
    assert r.returncode == 0 and json.loads(r.stdout) == {}


def test_codex_prompt_hook_captures(pinned):
    r = _run_hook(_one(CODEX["hooks"], "UserPromptSubmit"), pinned,
                  {"session_id": SID, "prompt": DECISION, "cwd": str(pinned), "turn_id": "1"})
    assert r.returncode == 0 and "TESS HOOK NOT RUN" not in r.stderr, r.stderr
    assert DECISION in (pinned / ".tess/state/brain/turns.jsonl").read_text()


@pytest.mark.parametrize("tamper", ["edit", "extra-module"])
@pytest.mark.parametrize("runtime", ["claude", "codex"])
def test_tampered_brain_code_is_never_run_and_never_blocks(pinned, tamper, runtime):
    if tamper == "edit":
        with open(pinned / "scripts/brain/brainlib/cues.py", "a") as fh:
            fh.write("\n# planted\n")
    else:
        (pinned / "scripts/brain/brainlib/json.py").write_text("raise SystemExit('shadow')\n")
    hooks = SETTINGS["hooks"] if runtime == "claude" else CODEX["hooks"]
    r = _run_hook(_one(hooks, "UserPromptSubmit"), pinned, {"session_id": SID, "prompt": DECISION})
    assert r.returncode == 0, "a refused hook must not block the user's turn"
    assert "TESS HOOK NOT RUN" in r.stderr and "systemMessage" in r.stdout
    assert not (pinned / ".tess/state/brain/turns.jsonl").exists()
    r = _run_hook(_one(hooks, "Stop"), pinned, {"session_id": SID})
    assert r.returncode == 0 and "decision" not in json.loads(r.stdout)


@pytest.mark.parametrize("runtime", ["claude", "codex"])
def test_broken_brain_json_warns_and_never_blocks(pinned, runtime):
    (pinned / "brain/brain.json").write_text("{not json")
    hooks = SETTINGS["hooks"] if runtime == "claude" else CODEX["hooks"]
    for event in ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"):
        r = _run_hook(_one(hooks, event), pinned, {"session_id": SID, "prompt": DECISION})
        assert r.returncode == 0, (event, r.stderr)
        assert '"block"' not in r.stdout and '"continue": false' not in r.stdout


def test_codex_hooks_outside_a_work_tree_exit_zero(tmp_path):
    for event in ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"):
        for cmd in _cmds(CODEX["hooks"], event):
            r = subprocess.run(cmd, shell=True, cwd=str(tmp_path), input="{}", capture_output=True, text=True,
                               timeout=30)
            assert r.returncode == 0, (event, r.stderr)
            if event in ("Stop", "SessionEnd"):
                assert json.loads(r.stdout or "{}") == {}


# --- codex-cli 0.158 rollout shape (verified live 2026-09-29) ------------------------------------

def _rollout_0158(path, cwd):
    tid = "01a0e9f3-0000-7000-a000-00000000c158"
    recs = [
        {"type": "session_meta", "payload": {"id": tid, "cwd": cwd, "cli_version": "0.158.0",
                                              "timestamp": "2026-09-29T05:37:50Z"}},
        {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "# AGENTS.md instructions for x\n<INSTRUCTIONS>..."}]}},
        {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": DECISION}]}},
        {"type": "event_msg", "payload": {"type": "item_completed", "item": {
            "type": "UserMessage", "content": [{"type": "text", "text": DECISION}]}}},
        {"type": "event_msg", "payload": {"type": "item_completed", "item": {
            "type": "CommandExecution", "command": ["/bin/zsh", "-lc", "cat brain/.private/pay.md"]}}},
        {"type": "event_msg", "payload": {"type": "item_completed", "item": {
            "type": "AgentMessage", "content": [{"type": "Text", "text": "Recorded: Postgres for the ledger."}]}}},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": "Recorded: Postgres for the ledger."}]}},
    ]
    for r in recs:
        r["timestamp"] = "2026-09-29T05:38:00Z"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return path


def test_codex_0158_rollout_is_journaled_once_with_its_reply(tmp_path):
    sys.path.insert(0, str(REPO / "scripts" / "brain"))
    from brainlib.parsers import codex
    sess = codex.parse(_rollout_0158(tmp_path / "rollout-2026-09-29T05-37-50-x.jsonl", "/work/fx"))
    assert [(m.role, m.text) for m in sess.msgs] == [("human", DECISION),
                                                     ("assistant", "Recorded: Postgres for the ledger.")]
    assert any(".private" in t for t in sess.tool_inputs)  # a shell read of a private path is seen


def test_codex_session_end_timeout_fits_what_codex_allows():
    """codex-cli 0.158 clamps a SessionEnd hook timeout to 3 s and prints a
    warning on every session when the config asks for more (seen live on a
    fresh install, 2026-09-29). The hook only hands the transcript to a
    detached sync, so 3 s is enough; ask for no more than Codex grants."""
    for group in CODEX["hooks"]["SessionEnd"]:
        for h in group["hooks"]:
            assert 0 < h["timeout"] <= 3, h
