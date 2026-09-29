"""v1.0 non-technical e2e round 2 (Quinn): Codex hooks off must be visible, plus polish.

Blocker: when Codex has not approved Tess's hooks (it asks again after every
hook change, so after every Tess update), the safety gate silently does not
run. Now:
  * the SessionStart / UserPromptSubmit hooks write .tess/state/hooks-alive.json,
  * `scripts/tess hooks-status` says, in one plain line, whether the hooks ran
    in THIS session, and the BOOT block has the first reply relay the OFF line,
  * `tessctl doctor` warns (never fails) when Codex's stored approval is
    missing or does not match the current hook text,
  * every doc and skill says the /hooks step is REQUIRED.
Nice-to-haves: narrow confirm/reject allow rules, collision-proof candidate
ids, a plain first-push refusal, a silent clean pre-commit, a plain update
check, a plain preset name, plain README "Updating".
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts" / "brain"))

from brainlib import hooksalive, inbox  # noqa: E402
from brainlib.config import Config  # noqa: E402

CODEX_OFF = ("Tess's safety checks are OFF in this Codex session — type /hooks and approve "
             "Tess's hooks, then start a new session.")
SESSION_ENV = ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CLAUDE_CODE_SESSION_ID")


def _clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in SESSION_ENV}
    env.update(TESS_BRAIN_NO_BACKFILL="1")
    env.update(extra)
    return env


# ── heartbeat: written by the hook command ────────────────────────────────


@pytest.mark.parametrize("event", ["session-start", "prompt"])
@pytest.mark.parametrize("runtime", ["codex", "claude"])
def test_hook_command_writes_the_heartbeat(tmp_path, runtime, event):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    (inst / ".tess").mkdir(exist_ok=True)  # a Tess OS folder (the fixture has no engine)
    r = subprocess.run([sys.executable, "-I", "-B", str(REPO / "scripts/brain/tessbrain.py"), "--root", str(inst),
                        "hook", event, "--runtime", runtime],
                       input=json.dumps({"session_id": "sess-123", "prompt": "hi"}), text=True,
                       capture_output=True, env=_clean_env(), timeout=60)
    assert r.returncode == 0, r.stderr
    doc = json.loads((inst / ".tess/state/hooks-alive.json").read_text())
    row = doc[runtime][0]
    assert row["session_id"] == "sess-123" and row["event"] == event and row["at"].endswith("Z")


def test_heartbeat_is_written_before_onboarding_and_in_the_source_repo_shape(tmp_path):
    hooksalive.beat(tmp_path, "codex", {"session_id": "a"}, "session-start")
    assert not (tmp_path / ".tess").exists()  # not a Tess OS folder: nothing written
    (tmp_path / ".tess").mkdir()
    # no brain/ at all (fresh folder, or the source repo): the safety hooks still count
    hooksalive.beat(tmp_path, "codex", {"session_id": "a"}, "session-start")
    hooksalive.beat(tmp_path, "codex", {"session_id": "b"}, "prompt")
    hooksalive.beat(tmp_path, "codex", {"session_id": "a"}, "prompt")
    rows = json.loads((tmp_path / hooksalive.REL).read_text())["codex"]
    assert [r["session_id"] for r in rows] == ["a", "b"]
    hooksalive.beat(tmp_path, "gemini", {"session_id": "x"}, "prompt")  # unknown runtime: ignored
    hooksalive.beat(tmp_path, "codex", {}, "prompt")  # no session id: ignored
    assert set(json.loads((tmp_path / hooksalive.REL).read_text())) == {"codex", "schema"}


def test_heartbeat_is_gitignored_and_both_runtimes_wire_the_hook():
    r = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", ".tess/state/hooks-alive.json"])
    assert r.returncode == 0
    codex = (REPO / ".codex/config.toml").read_text()
    claude = json.loads((REPO / ".claude/settings.json").read_text())["hooks"]
    for ev, cmd in (("SessionStart", "tessbrain.py hook session-start"), ("UserPromptSubmit", "tessbrain.py hook prompt")):
        assert any(cmd in h["command"] for g in claude[ev] for h in g["hooks"])
        assert cmd + " --runtime codex" in codex


# ── scripts/tess hooks-status ─────────────────────────────────────────────


def _status(tmp_path, env, heartbeat=None):
    root = tmp_path / "inst"
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "scripts/tess", root / "scripts/tess")
    if heartbeat is not None:
        (root / ".tess/state").mkdir(parents=True, exist_ok=True)
        (root / ".tess/state/hooks-alive.json").write_text(json.dumps(heartbeat))
    return subprocess.run([sys.executable, "-I", "-B", str(root / "scripts/tess"), "hooks-status"],
                          capture_output=True, text=True, env=_clean_env(**env), timeout=30)


def test_hooks_status_off_when_no_heartbeat(tmp_path):
    r = _status(tmp_path, {"CODEX_THREAD_ID": "t-1"})
    assert r.returncode == 1 and r.stdout.strip() == CODEX_OFF


def test_hooks_status_off_when_only_another_session_beat(tmp_path):
    r = _status(tmp_path, {"CODEX_THREAD_ID": "t-2"}, {"codex": [{"session_id": "t-1"}]})
    assert r.returncode == 1 and r.stdout.strip() == CODEX_OFF
    assert len(r.stdout.strip().splitlines()) == 1


def test_hooks_status_on_for_this_session_and_codex_wins_over_inherited_claude_id(tmp_path):
    hb = {"codex": [{"session_id": "t-1"}], "claude": [{"session_id": "c-9"}]}
    r = _status(tmp_path, {"CODEX_THREAD_ID": "t-1", "CLAUDE_CODE_SESSION_ID": "c-9"}, hb)
    assert r.returncode == 0 and r.stdout.strip() == "Tess's safety checks are on in this Codex session."
    r = _status(tmp_path, {"CLAUDE_CODE_SESSION_ID": "c-9"}, hb)
    assert r.returncode == 0 and "Claude Code session" in r.stdout
    r = _status(tmp_path, {"CLAUDE_CODE_SESSION_ID": "c-0"}, hb)
    assert r.returncode == 1 and r.stdout.startswith("Tess's safety checks are OFF in this Claude Code session")


def test_hooks_status_unknown_runtime_is_quiet_and_plain(tmp_path):
    r = _status(tmp_path, {})
    assert r.returncode == 3 and "OFF" not in r.stdout and "safety checks" in r.stdout


def test_boot_tells_the_first_reply_to_check_and_relay_the_exact_line():
    boot = (REPO / "scripts/brain/BOOT.md").read_text()
    assert "run `python3 scripts/tess hooks-status`" in boot
    assert "prints a line saying the safety checks are OFF, begin the reply with that exact line" in boot
    assert "never paste an internal tool error" in boot and "No jargon (modes, presets, commits, remotes" in boot
    for entry in ("AGENTS.md", "CLAUDE.md"):
        assert "python3 scripts/tess hooks-status" in (REPO / entry).read_text()
    allow = json.loads((REPO / ".tess/core/settings-core.json").read_text())["permissions"]["allow"]
    assert "Bash(python3 scripts/tess hooks-status)" in allow  # Claude never prompts for it


# ── tessctl doctor: Codex hook trust ──────────────────────────────────────


def _codex_home(tmp_path, engine, *, trusted=True, approve=None):
    home = tmp_path / "codex-home"
    home.mkdir(exist_ok=True)
    lines = []
    if trusted:
        lines += ['[projects."%s"]' % REPO, 'trust_level = "trusted"', ""]
    if approve is not None:
        hooks = engine._toml_loads((REPO / ".codex/config.toml").read_text())["hooks"]
        for ev, groups in hooks.items():
            for gi, g in enumerate(groups):
                for hi, h in enumerate(g["hooks"]):
                    key = "%s/.codex/config.toml:%s:%d:%d" % (REPO, engine._CODEX_EVENT_KEYS[ev], gi, hi)
                    lines += ['[hooks.state."%s"]' % key,
                              'trusted_hash = "%s"' % approve(engine._codex_hook_hash(ev, g, h)), ""]
    (home / "config.toml").write_text("\n".join(lines))
    return home


def test_doctor_warns_when_codex_has_no_approval(tmp_path, engine):
    home = _codex_home(tmp_path, engine)
    assert engine._codex_hook_trust_warning(REPO, home) == engine.CODEX_HOOKS_OFF_WARNING
    assert engine.CODEX_HOOKS_OFF_WARNING == ("Codex: Tess's safety hooks are not approved yet — "
                                              "open Codex here and type /hooks")


def test_doctor_warns_when_the_approval_is_for_older_hook_text(tmp_path, engine):
    home = _codex_home(tmp_path, engine, approve=lambda h: "sha256:" + "0" * 64)
    findings = engine._codex_hook_trust_findings(REPO, home)
    assert findings and {kind for _, kind in findings} == {"changed"}
    assert engine._codex_hook_trust_warning(REPO, home) == engine.CODEX_HOOKS_OFF_WARNING


def test_doctor_quiet_when_every_hook_is_approved_or_codex_is_absent(tmp_path, engine):
    home = _codex_home(tmp_path, engine, approve=lambda h: h)
    assert engine._codex_hook_trust_findings(REPO, home) == []
    assert engine._codex_hook_trust_warning(REPO, home) == ""
    assert engine._codex_hook_trust_warning(REPO, tmp_path / "no-codex-here") == ""


def test_doctor_untrusted_folder_says_trust_then_hooks(tmp_path, engine):
    home = _codex_home(tmp_path, engine, trusted=False)
    assert "trust the folder, then type /hooks" in engine._codex_hook_trust_warning(REPO, home)


def test_codex_hash_matches_codex_normalisation(engine):
    # Codex hashes the NORMALIZED identity: default timeout 600, SessionEnd clamped to 3,
    # no matcher for UserPromptSubmit/Stop, async false, sorted compact JSON.
    import hashlib
    ident = {"event_name": "stop", "hooks": [{"async": False, "command": "x", "timeout": 600,
                                             "type": "command"}]}
    want = "sha256:" + hashlib.sha256(json.dumps(ident, sort_keys=True, separators=(",", ":"))
                                      .encode()).hexdigest()
    assert engine._codex_hook_hash("Stop", {"matcher": "ignored"}, {"type": "command", "command": "x"}) == want


def test_doctor_prints_the_warning_line_and_still_passes(tmp_path, engine):
    home = _codex_home(tmp_path, engine)
    r = subprocess.run([str(REPO / "tessctl"), "doctor"], cwd=str(REPO), capture_output=True, text=True,
                       env=_clean_env(CODEX_HOME=str(home), TESS_VERBOSE=""), timeout=600)
    assert r.returncode == 0, r.stdout[-2000:]
    assert "WARNING     " + engine.CODEX_HOOKS_OFF_WARNING in r.stdout
    assert "One warning above: Codex's safety hooks." in r.stdout


# ── docs and skills: the /hooks step is required ──────────────────────────


@pytest.mark.parametrize("rel", [".agents/skills/brain-onboard/SKILL.md", ".claude/skills/brain-onboard/SKILL.md",
                                 "docs/brain/ONBOARDING.md", "docs/brain/RUNTIMES.md", "README.md",
                                 "adapters/codex/README.md"])
def test_docs_say_codex_hooks_are_required(rel):
    text = (REPO / rel).read_text(encoding="utf-8")
    low = text.lower()
    assert "optional: trust the project" not in low and "optional: trust the" not in low
    assert "required" in low and "/hooks" in text
    if rel.endswith("SKILL.md") or rel.startswith("docs/brain/"):
        assert "type `/hooks` in Codex and approve Tess's hooks; Codex asks again after each Tess update" in text


# ── nice-to-haves ─────────────────────────────────────────────────────────


def test_claude_allow_list_confirm_and_reject_are_narrow():
    allow = json.loads((REPO / ".tess/core/settings-core.json").read_text())["permissions"]["allow"]
    assert "Bash(python3 scripts/brain/tessbrain.py confirm:*)" in allow
    assert "Bash(python3 scripts/brain/tessbrain.py reject:*)" in allow
    assert "Bash(python3 scripts/brain/tessbrain.py retract:*)" not in allow
    live = json.loads((REPO / ".claude/settings.json").read_text())["permissions"]["allow"]
    assert live == allow


def test_candidate_ids_never_repeat_within_a_minute_across_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_BRAIN_NOW", "2026-09-29T10:15:30+00:00")
    root = tmp_path / "inst"
    (root / "brain" / "decisions").mkdir(parents=True)
    cfg = Config(root)
    stamp = cfg.now().strftime("%Y%m%d-%H%M")

    def new_run():
        for attr in ("_issued", "_scanned"):
            monkeypatch.delattr(inbox._next_id, attr, raising=False)

    new_run()
    first = inbox._next_id(cfg)
    assert first == "C-%s-01" % stamp
    # run 1 promoted its candidate: the inbox file is gone, a record names the id
    (root / "brain/decisions/pricing.md").write_text("---\ncandidate: %s\n---\nbody\n" % first)
    new_run()
    second = inbox._next_id(cfg)
    assert second != first and second == "C-%s-02" % stamp
    # run 2 left its candidate in the inbox's rejected/ folder; run 3 still moves on
    (root / "brain/inbox/rejected").mkdir(parents=True)
    (root / "brain/inbox/rejected" / ("%s.json" % second)).write_text("{}")
    new_run()
    assert inbox._next_id(cfg) == "C-%s-03" % stamp


def test_first_push_without_proof_is_plain_by_default(engine, capsys, monkeypatch):
    monkeypatch.setattr(engine, "_gate_refused_paths", lambda result: ["CLAUDE.md"])
    safe = {"release_proof": None, "reasons": ["COVERING_APPROVAL_MISSING: no covering APPROVE verdict found"]}
    engine._gate_print_refusal("pre-push", {}, safe, verbose=False, bases=[engine.EMPTY_TREE_SHA])
    out = capsys.readouterr().out
    assert "COVERING_APPROVAL_MISSING" not in out and ".tess/release-proof.json" not in out
    assert "npm create tess@latest my-os" in out and "Nothing was sent." in out
    assert "TESS_VERBOSE=1 git push" in out
    engine._gate_print_refusal("pre-push", {}, safe, verbose=True, bases=[engine.EMPTY_TREE_SHA])
    assert "COVERING_APPROVAL_MISSING" in capsys.readouterr().out


def test_clean_pre_commit_lint_prints_nothing(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    r = fxlib.cli(inst, "lint", "--staged", "--warn-only")
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout
    bare = tmp_path / "bare"
    bare.mkdir()
    r = fxlib.cli(bare, "lint", "--staged", "--warn-only")
    assert r.returncode == 0 and "{" not in r.stdout
    r = fxlib.cli(inst, "lint", "--json")
    assert json.loads(r.stdout) == {"errors": [], "warnings": []}  # machine output unchanged


def test_readme_updating_explains_ref_and_hooks_in_plain_words():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    upd = text[text.index("## Updating"): text.index("## More detail")]
    assert "`--ref v1.0.0` names the version to move to" in upd
    assert "Hooks are the small checks Tess runs automatically" in upd
    assert "type `/hooks` in Codex once more" in upd


def test_wizard_summary_uses_the_plain_preset_name():
    journey = (REPO / "create-tess/src/journey.js").read_text(encoding="utf-8")
    brain = (REPO / "create-tess/src/brain.js").read_text(encoding="utf-8")
    assert "(${preset})" not in journey and "(${c.preset})" not in journey
    assert journey.count("presetLabel(") == 2
    assert "'solo-consultant': 'working on your own'" in brain
