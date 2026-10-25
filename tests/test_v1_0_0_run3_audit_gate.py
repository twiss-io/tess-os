"""1.0.0: the run-3 audit's gate-side items (folded into the a769130 fix).

C4      Tess's dashboard launcher (gui/bin/tess-gui.mjs, the `tess-gui` bin,
        `npm start` in gui/) starts headless claude agents without a shell, so
        starting it is judged like `tessctl run`: it asks in Claude Code, is
        refused in Codex, in the no-prompt modes and inside a peer call or a
        nested session, and counts one agent against the task's budget.
unit 2  A nested `claude -p` is read-only only when `--tools` limits the tools
        it has to read tools AND it starts inside the project; the
        pre-approve-only forms (`--allowed-tools`, plan mode) ask.
unit 3  A hook-skipping variable reaching a `tessctl run` (or a direct call
        through an earlier export) is refused.
unit 4  `tessctl gate pre-push` with a caller-chosen --base/--head asks.
unit 5  `.tess/` control files are protected at any depth; the Codex hook runs
        only when the nearest lock is at the top of its repository.

Decisions: (claude default, claude acceptEdits, codex).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from test_v1_n1_n3 import ALLOW, ASK, DENY, G, REPO, _all, _env, proj  # noqa: F401


def _call(proj, cmd, sid, mode="default", codex=False, turn="t1"):
    data = {"tool_name": "Bash", "cwd": str(proj[0]), "tool_input": {"command": cmd}, "session_id": sid}
    if codex:
        data["turn_id"] = turn
    else:
        data["permission_mode"] = mode
    return G.decide(data, proj[0], "codex" if codex else "claude")[0] or "allow"


@pytest.fixture
def gui(proj):
    d = proj[0] / "gui" / "bin"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tess-gui.mjs").write_text("#!/usr/bin/env node\n")
    (proj[0] / "gui" / "package.json").write_text('{"scripts": {"start": "node bin/tess-gui.mjs"}}\n')
    return proj


# ================================================================ C4: tess-gui
GUI_LAUNCHES = [
    "node gui/bin/tess-gui.mjs",
    "node gui/bin/tess-gui.mjs --print-token --dir .",
    "node gui/bin/tess-gu?.mjs",
    "gui/bin/tess-gui.mjs",
    "./gui/bin/tess-gui.mjs",
    "tess-gui",
    "npx tess-gui",
    "npm exec tess-gui",
    "cd gui && npm start",
    "cd gui && npm run start",
    "cd gui && pnpm start",
    "cd gui && yarn start",
    "cd gui && node --run start",
    "npm --prefix gui start",
    "npm --prefix=gui run start",
]


@pytest.mark.parametrize("cmd", GUI_LAUNCHES)
def test_c4_starting_the_dashboard_launcher_asks_and_codex_refuses(gui, cmd):
    assert _all(gui, cmd) == ASK


@pytest.mark.parametrize("cmd", [
    "TESS_CONSULT_DEPTH=1 node gui/bin/tess-gui.mjs",
    "CLAUDE_CODE_SIMPLE=1 node gui/bin/tess-gui.mjs",
])
def test_c4_refused_inside_a_peer_call_or_with_hooks_skipped(gui, cmd):
    assert _all(gui, cmd) == DENY


def test_c4_refused_when_this_session_is_a_peer(gui, monkeypatch):
    monkeypatch.setenv("TESS_CONSULT_DEPTH", "1")
    assert _all(gui, "node gui/bin/tess-gui.mjs") == DENY


def test_c4_refused_when_nested(gui, monkeypatch):
    monkeypatch.setattr(G, "_ancestry", lambda limit=40: ["claude", "zsh", "claude", "zsh", "login"],
                        raising=False)
    G._STATE.pop("nested", None)
    assert _all(gui, "cd gui && npm start") == DENY
    G._STATE.pop("nested", None)


@pytest.mark.parametrize("mode", ["bypassPermissions", "dontAsk"])
def test_c4_refused_in_the_no_prompt_modes(gui, mode):
    assert _call(gui, "node gui/bin/tess-gui.mjs", "sess-c4-" + mode, mode=mode) == "deny"


def test_c4_counts_one_agent_against_the_budget(gui):
    s = "sess-c4-budget"
    G.task_start({"session_id": s})
    consult = "codex exec -s read-only 'review the diff in src/'"
    assert [_call(gui, consult, s) for _ in range(2)] == ["allow"] * 2
    assert _call(gui, "node gui/bin/tess-gui.mjs", s) == "ask"     # third agent
    assert _call(gui, consult, s) == "ask"                          # the budget is used up


@pytest.mark.parametrize("cmd", [
    "cd gui && npm test",
    "npm --prefix gui test",
    "npm start",                      # not the gui folder
    "cat gui/bin/tess-gui.mjs",
    "node -e 'console.log(1)'",
])
def test_c4_neighbours_are_unchanged(gui, cmd):
    assert _all(gui, cmd) == ALLOW


# ===================================================== unit 2: read-only claude
@pytest.mark.parametrize("cmd", [
    "claude -p hi --tools Read",
    "claude -p hi --tools ''",
    "cd src && claude -p hi --tools Read,Grep",
])
def test_u2_a_tool_limited_run_inside_the_project_stays_allowed(proj, cmd):
    (proj[0] / "src").mkdir(exist_ok=True)
    assert _all(proj, cmd) == ALLOW


@pytest.mark.parametrize("cmd", [
    "claude -p hi --allowed-tools Read",                        # pre-approves, does not limit
    "claude -p hi --permission-mode plan",
    "claude -p hi --allowed-tools Read --permission-mode plan",
    "cd /tmp && claude -p hi --tools Read",                      # outside the project
    "cd $UNKNOWN_DIR && claude -p hi --tools Read",              # folder only known at run time
])
def test_u2_other_nested_claude_runs_ask(proj, cmd):
    assert _all(proj, cmd) == ASK


# =========================================== unit 3: hook-skipping environment
@pytest.mark.parametrize("cmd", [
    "CLAUDE_CODE_SIMPLE=1 ./tessctl run m1",
    "export CLAUDE_CODE_SAFE_MODE=1; ./tessctl run m1",
    "CODEX_HOME=/tmp/x ./tessctl run m1 --driver codex",
    "export CLAUDE_CODE_SIMPLE=1; claude -p hi --tools Read",
])
def test_u3_a_hook_skipping_variable_reaching_the_child_is_refused(proj, cmd):
    assert _all(proj, cmd) == DENY


def test_u3_tessctl_run_without_it_still_asks(proj):
    assert _all(proj, "./tessctl run m1") == ASK
    assert _all(proj, "./tessctl run m1 --driver fake") == ALLOW


# ===================================================== unit 4: pre-push bases
@pytest.mark.parametrize("cmd", [
    "./tessctl gate pre-push --base abc --head def",
    "./tessctl gate pre-push --head def",
    "./tessctl gate pre-push --bas abc",
    "./tessctl gate pre-push $ARGS",
])
def test_u4_a_chosen_ship_check_base_asks(proj, cmd):
    assert _all(proj, cmd) == ASK


def test_u4_the_plain_hook_form_is_unchanged(proj):
    assert _all(proj, "./tessctl gate pre-push") == ALLOW


# ================================================= unit 5: nested control folder
@pytest.mark.parametrize("cmd", [
    "mkdir -p sub/.tess && cp .tess/tess.lock sub/.tess/tess.lock",
    "echo x > sub/deeper/.tess/tess.lock",
    "cp src/a.py sub/.tess/bin/tessctl",
    "cd sub && echo x > .tess/tess.lock",
])
def test_u5_a_nested_tess_control_file_is_protected(proj, cmd):
    (proj[0] / "sub").mkdir(exist_ok=True)
    assert _all(proj, cmd) == DENY


@pytest.mark.parametrize("cmd", ["echo x > sub/tess.lock", "echo x > sub/notes.md", "mkdir -p sub/tess"])
def test_u5_neighbours_are_unchanged(proj, cmd):
    (proj[0] / "sub").mkdir(exist_ok=True)
    assert _all(proj, cmd) == ALLOW


def _codex_hook_command() -> str:
    text = (REPO / ".codex" / "config.toml").read_text(encoding="utf-8")
    m = re.search(r'^command = "(sh -c \'d=\$\(pwd -P\).*)"$', text, re.MULTILINE)
    assert m, "the Codex PreToolUse hook command"
    return m.group(1).replace('\\"', '"')


def test_u5_codex_hook_refuses_a_nested_lock_below_the_repository_top(tmp_path):
    git = shutil.which("git")
    if not git:
        pytest.skip("git is not installed")
    top = tmp_path / "proj"
    for d in (top, top / "sub"):
        (d / ".tess").mkdir(parents=True)
        (d / ".tess" / "tess.lock").write_text("x\n")
        (d / ".claude" / "hooks").mkdir(parents=True)
        (d / ".claude" / "hooks" / "run-pinned.py").write_text("import sys\nprint('RAN', sys.argv[0])\n")
    subprocess.run([git, "init", "-q", str(top)], check=True, capture_output=True)
    cmd = _codex_hook_command()
    nested = subprocess.run(["/bin/sh", "-c", cmd], cwd=str(top / "sub"), capture_output=True, text=True,
                            stdin=subprocess.DEVNULL)
    assert nested.returncode == 2 and "TESS GATE NOT RUN" in nested.stderr and "RAN" not in nested.stdout
    at_top = subprocess.run(["/bin/sh", "-c", cmd], cwd=str(top / "sub" / ".."), capture_output=True,
                            text=True, stdin=subprocess.DEVNULL)
    assert at_top.returncode == 0 and "RAN" in at_top.stdout, at_top.stderr
    # the rendered template says the same
    tpl = (REPO / ".tess" / "core" / "templates" / "agents-md" / "codex-config.toml.tpl").read_text("utf-8")
    assert "is not the top of its repository" in tpl
