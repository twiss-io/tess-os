"""1.0.0 (section 2, operator decision 22 Oct): peer consults are review-only and
count toward the budget of at most three agents per task.

Review-only (the nested-agent rule, SECURITY.md "Nested agent CLIs"): without
asking, only a provably read-only, non-interactive peer run is allowed; a
write-capable or approval-bypassing run asks or is refused; a peer cannot
start another agent (TESS_CONSULT_DEPTH, or a runtime inside a runtime).

The budget (new): every Agent/Task/spawn_agent dispatch, every agent-CLI run
(not --help/--version) and every `tessctl run` counts; a call that would take
the task past three agents asks (Claude Code) or is refused (Codex). A task is
a Codex turn, or in Claude Code the span after each operator prompt (the
UserPromptSubmit hook `tess-gate.py --task-start`). The counter lives under
~/.config/tess/agent-budget (agents are refused that folder). On c80f6a3 the
fourth, fifth, ... consult in a task was allowed.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys

import pytest

from test_v1_n1_n3 import ALLOW, ASK, DENY, G, GATE, REPO, _all, _env, proj  # noqa: F401

CONSULT = "codex exec -s read-only 'review the diff in src/ and report problems'"
PLAN = "claude -p --permission-mode plan 'review this change'"


def _call(proj, tool, tin, sid, codex=False, turn="t1", mode="default"):
    data = {"tool_name": tool, "cwd": str(proj[0]), "tool_input": tin, "session_id": sid}
    if codex:
        data["turn_id"] = turn
    else:
        data["permission_mode"] = mode
    return G.decide(data, proj[0], "codex" if codex else "claude")[0] or "allow"


def _bash(proj, cmd, sid, **kw):
    return _call(proj, "Bash", {"command": cmd}, sid, **kw)


@pytest.fixture
def sid(request):
    s = "sess-" + request.node.name
    G.task_start({"session_id": s})
    return s


# ---------------------------------------------------------------- review-only
@pytest.mark.parametrize("cmd,want", [
    (CONSULT, ALLOW),
    (PLAN, ALLOW),
    ("codex exec -s workspace-write 'fix it'", DENY),
    ("codex exec --dangerously-bypass-approvals-and-sandbox 'fix it'", DENY),
    ("claude -p --dangerously-skip-permissions 'fix it'", DENY),
    ("claude -p 'fix it'", ASK),
    ("claude", ASK),
])
def test_a_peer_may_only_review(proj, cmd, want):
    assert _all(proj, cmd) == want


def test_a_peer_cannot_start_another_agent(proj, monkeypatch):
    monkeypatch.setenv("TESS_CONSULT_DEPTH", "1")
    assert _all(proj, CONSULT) == DENY
    assert _all(proj, "./tessctl run m1") == DENY


# ---------------------------------------------------------------- the budget
def test_three_agents_per_task_then_ask(proj, sid):
    assert [_bash(proj, CONSULT, sid) for _ in range(3)] == ["allow"] * 3
    assert _bash(proj, CONSULT, sid) == "ask"
    assert _bash(proj, PLAN, sid) == "ask"


def test_dispatches_and_consults_share_the_budget(proj, sid):
    assert _call(proj, "Agent", {"prompt": "build x", "subagent_type": "ada"}, sid) == "allow"
    assert _call(proj, "Task", {"prompt": "test x"}, sid) == "allow"
    assert _bash(proj, CONSULT, sid) == "allow"
    assert _call(proj, "Agent", {"prompt": "one more"}, sid) == "ask"
    assert _bash(proj, CONSULT, sid) == "ask"


def test_a_new_prompt_starts_a_new_budget(proj, sid):
    for _ in range(3):
        _bash(proj, CONSULT, sid)
    assert _bash(proj, CONSULT, sid) == "ask"
    G.task_start({"session_id": sid})
    assert _bash(proj, CONSULT, sid) == "allow"


def test_without_a_prompt_mark_the_whole_session_counts(proj):
    s = "sess-unmarked"
    path = G._budget_file(s)
    if os.path.exists(path):
        os.unlink(path)
    assert [_bash(proj, CONSULT, s) for _ in range(4)] == ["allow"] * 3 + ["ask"]


def test_codex_counts_per_turn_and_refuses_past_the_budget(proj):
    s = "codex-sess"
    got = [_bash(proj, CONSULT, s, codex=True, turn="t1") for _ in range(4)]
    assert got == ["allow"] * 3 + ["deny"]
    assert _call(proj, "spawn_agent", {"message": "x"}, s, codex=True, turn="t1") == "deny"
    assert _bash(proj, CONSULT, s, codex=True, turn="t2") == "allow"


def test_no_prompt_modes_refuse_past_the_budget(proj, sid):
    for _ in range(3):
        _bash(proj, CONSULT, sid, mode="bypassPermissions")
    assert _bash(proj, CONSULT, sid, mode="bypassPermissions") == "deny"


def test_help_and_refused_calls_are_not_counted(proj, sid):
    for _ in range(5):
        assert _bash(proj, "codex --help", sid) == "allow"
    for _ in range(5):
        assert _bash(proj, "claude -p --dangerously-skip-permissions 'x'", sid) == "deny"
    assert [_bash(proj, CONSULT, sid) for _ in range(3)] == ["allow"] * 3


def test_tessctl_run_counts(proj, sid):
    for _ in range(3):
        _bash(proj, CONSULT, sid)
    reason = G.decide({"tool_name": "Bash", "cwd": str(proj[0]), "session_id": sid,
                       "permission_mode": "default", "tool_input": {"command": "./tessctl run m1"}},
                      proj[0], "claude")[1]
    assert "3-agent budget" in reason


def test_counter_is_private_and_unreadable_counter_asks(proj, sid):
    _bash(proj, CONSULT, sid)
    path = G._budget_file(sid)
    assert stat.S_IMODE(os.lstat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.lstat(os.path.dirname(path)).st_mode) == 0o700
    doc = json.loads(open(path).read())
    assert doc["used"] == 1 and doc["task"].startswith("prompt:")
    with open(path, "w") as fh:
        fh.write("not json")
    assert _bash(proj, CONSULT, sid) == "ask", "an unreadable counter counts the budget as spent"


def test_agents_cannot_reset_the_counter(proj):
    for cmd in ("rm -rf ~/.config/tess/agent-budget", "echo '{}' > ~/.config/tess/agent-budget/x.json",
                "cat ~/.config/tess/agent-budget/x.json"):
        assert _all(proj, cmd) == DENY, cmd


def test_no_session_id_is_not_a_runtime_call(proj):
    for _ in range(5):
        assert _all(proj, CONSULT) == ALLOW


def test_task_start_hook_prints_nothing_and_never_blocks(proj, tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CODEX_THREAD_ID")}
    for payload in ('{"session_id": "hook-sess", "prompt": "hi"}', "not json", "{}"):
        r = subprocess.run([sys.executable, "-I", "-B", str(GATE), "--runtime", "claude", "--task-start"],
                           input=payload, capture_output=True, text=True, env=env, timeout=30)
        assert r.returncode == 0 and r.stdout == "", (payload, r.stdout, r.stderr)


def test_settings_wire_the_task_mark_and_route_dispatches_to_the_gate():
    for rel in (".claude/settings.json", ".tess/core/settings-core.json"):
        doc = json.loads((REPO / rel).read_text())
        hooks = doc["hooks"]
        prompt = [h["command"] for b in hooks["UserPromptSubmit"] for h in b["hooks"]]
        assert any("tess-gate.py --runtime claude --task-start" in c and "--on-fail warn" in c for c in prompt)
        disp = [h for b in hooks["PreToolUse"] if b.get("matcher") == "^(Task|Agent)$" for h in b["hooks"]]
        gate = [h for h in disp if h["command"].endswith("tess-gate.py --runtime claude")]
        assert gate and gate[0].get("onFailure") == "block" and "--on-fail block" in gate[0]["command"]


def test_doctrine_states_the_budget():
    text = (REPO / "conductor" / "orchestration-budget.md").read_text()
    assert "three agents per task" in text and "peer" in text and "review only" in text
