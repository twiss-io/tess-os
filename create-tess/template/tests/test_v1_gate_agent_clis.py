"""
v1.0.0: the gate governs nested agent CLIs.

At 4e06a26 `claude`, `codex`, `gemini` and `agy` were in neither the gated
program set nor the REPL table, so every call below was ALLOWED in Claude
(default and acceptEdits) and in Codex: an in-session agent could start an
ungoverned child agent that writes anything, and flags such as `--bare`,
`--safe-mode`, `--ignore-rules` and `--dangerously-bypass-hook-trust` keep
Tess's hooks out of the child. The rule now (SECURITY.md, "Nested agent
CLIs"):

  * refused in both runtimes: approval bypasses, hook- or settings-skipping
    flags unless the child has no tools, secret-shaped prompts, and any
    agent-CLI call made inside a peer call;
  * allowed: --help/--version and provably read-only, non-interactive runs;
  * everything else asks in Claude Code and is refused in Codex.

Lists named CONTROLS were already decided that way at 4e06a26 or are the
allow-controls the fix must keep (the gate-arena verifier, the heartbeat
classifier, `codex exec -s read-only`).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / ".claude" / "hooks" / "tess-gate.py"
HAS_GIT = shutil.which("git") is not None


def _gate():
    sys.dont_write_bytecode = True  # never leave __pycache__ in .claude/hooks
    spec = importlib.util.spec_from_file_location("tess_gate_agent_clis", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _gate()


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    """A Tess instance copy (lock, pins, hooks) with a fake HOME."""
    tmp = tmp_path_factory.mktemp("agentcli")
    root = tmp / "proj"
    for rel in (".tess/tess.lock", ".tess/core/pinned-scripts.sha256", "tessctl",
                "tess.manifest.json", "conductor/guardrails.md", "CLAUDE.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    for tree in (".claude/hooks", "scripts/brain", ".tess/bin", ".tess/vendor"):
        shutil.copytree(REPO / tree, root / tree, ignore=shutil.ignore_patterns("__pycache__"))
    (root / ".claude" / "settings.json").write_text("{}\n")
    (root / "empty_mcp_config.json").write_text(json.dumps({"mcpServers": {}}))
    (root / "busy_mcp_config.json").write_text(json.dumps({"mcpServers": {"x": {"command": "x"}}}))
    home = tmp / "home"
    (home / ".config").mkdir(parents=True)
    return root, home


@pytest.fixture(autouse=True)
def _env(proj, monkeypatch):
    monkeypatch.setenv("HOME", str(proj[1]))
    for k in ("XDG_CONFIG_HOME", "TESS_BRAIN_PROVENANCE_DIR", "GIT_DIR", "GIT_WORK_TREE",
              "TESS_CONSULT_DEPTH"):
        monkeypatch.delenv(k, raising=False)
    # The process ancestry of the test runner is not the gate's: a developer
    # may run the suite from inside an agent session.
    monkeypatch.setattr(G, "_ancestry", lambda limit=40: ["python3", "zsh", "login"], raising=False)


def _decide(proj, cmd, runtime="claude", mode="default"):
    root = proj[0]
    data = {"tool_name": "Bash", "cwd": str(root), "tool_input": {"command": cmd}}
    if runtime == "codex":
        data["turn_id"] = "t"
    else:
        data["permission_mode"] = mode
    return G.decide(data, root, runtime)


def _all(proj, cmd):
    """(claude default, claude acceptEdits, codex) decisions."""
    return tuple(_decide(proj, cmd, rt, mode)[0] or "allow"
                 for rt, mode in (("claude", "default"), ("claude", "acceptEdits"), ("codex", None)))


# ------------------------------------------------------------------ refused in both runtimes

DENIED = [
    # the finding, verbatim
    "claude --dangerously-skip-permissions -p 'rewrite conductor/guardrails.md'",
    "codex --dangerously-bypass-approvals-and-sandbox",
    'codex exec --sandbox workspace-write "rewrite conductor/guardrails.md"',
    "gemini --yolo",
    # claude bypasses
    "claude --allow-dangerously-skip-permissions -p x",
    "claude -p x --permission-mode bypassPermissions",
    "claude -p x --permission-mode dontAsk",
    "claude -p x --permission-mode=auto",
    "claude --permission-mode bypassPermissions",
    "claude -p x --tools '' --dangerously-skip-permissions",
    # claude flags that skip Tess's hooks or settings while the child has tools
    "claude --bare -p x",
    "claude --safe-mode -p x",
    "claude -p x --safe-mode --permission-mode plan",
    "claude -p x --restricted",
    "claude -p x --settings /tmp/other-settings.json",
    "claude -p x --settings '{\"disableAllHooks\": true}'",
    "claude -p x --setting-sources user",
    "CLAUDE_CODE_SIMPLE=1 claude -p x",
    "env CLAUDE_CODE_SAFE_MODE=1 claude -p x --allowed-tools Read",
    # --tools takes every word up to the next option: the prompt is a tool name
    "claude -p --safe-mode --tools '' 'review this'",
    # codex bypasses, sandbox and config
    "codex --yolo",
    "codex exec --yolo x",
    "codex exec --full-auto x",
    "codex exec --approve-for-me x",
    "codex exec -s read-only --dangerously-bypass-hook-trust x",
    "codex exec -s read-only --ignore-rules x",
    "codex exec -s danger-full-access x",
    "codex exec --sandbox=workspace-write x",
    "codex exec -sworkspace-write x",
    "codex -s workspace-write",
    "codex exec -s read-only -c sandbox_mode=danger-full-access x",
    "codex exec -s read-only -c 'sandbox_mode=\"workspace-write\"' x",
    "codex exec --ignore-user-config x",
    "codex --ignore-user-config",
    "CODEX_HOME=/tmp/elsewhere codex exec x",
    # gemini (documented flags, unverified)
    "gemini -y -p x",
    "gemini -p x --approval-mode yolo",
    "gemini -p x --approval-mode auto_edit",
    "gemini --approval-mode=yolo",
    # the other agent CLIs: bypass-shaped options
    "agy --yolo",
    "aider --yes-always",
    "aider --yes --message x",
    "cursor-agent -f -p x",
    "cursor-agent --force -p x",
    "amp --dangerously-allow-all -x x",
    "copilot --allow-all-tools -p x",
    "qwen -y -p x",
    "opencode run --dangerously-skip-permissions x",
    "droid exec --skip-permissions-unsafe x",
    "GOOSE_MODE=auto goose run -t x",
    # through wrappers, runners, paths, variables and shells
    "npx -y @anthropic-ai/claude-code --dangerously-skip-permissions -p x",
    "npx @openai/codex@latest exec --yolo x",
    "bunx @google/gemini-cli --yolo",
    "/usr/local/bin/claude --dangerously-skip-permissions -p x",
    "~/.local/bin/claude --permission-mode bypassPermissions -p x",
    "env -i claude --dangerously-skip-permissions -p x",
    "nohup codex exec --full-auto x &",
    "timeout 600 codex exec -s workspace-write x",
    "C=claude; $C --dangerously-skip-permissions -p x",
    "M=bypassPermissions; claude -p x --permission-mode \"$M\"",
    "S=workspace-write; codex exec -s $S x",
    "bash -c 'claude --dangerously-skip-permissions -p x'",
    "sh -c \"codex exec --yolo x\"",
    "f() { codex exec --yolo \"$@\"; }; f x",
    "echo hi && claude --bare -p x",
    "{ codex exec -s danger-full-access x; }",
    "claude --dangerously-skip-perm -p x",
    # a prompt carrying a secret-shaped value (the dispatch scanner's set)
    "claude -p 'use token=abcdefghijklmnopqrstuvwxyz123456' --tools ''",
    "codex exec -s read-only 'push with ghp_abcdefghijklmnopqrstuvwxyz0123456789AB'",
    "codex exec -s read-only - <<'EOF'\npassword: abcdefghijklmnopqrstuvwxyz0123\nEOF",
    # TESS_CONSULT_DEPTH is the drivers' to set
    "TESS_CONSULT_DEPTH=0 codex exec -s read-only x",
    "env TESS_CONSULT_DEPTH=0 claude -p x --tools ''",
]


@pytest.mark.parametrize("cmd", DENIED)
def test_agent_cli_payload_is_denied(proj, cmd):
    assert _all(proj, cmd) == ("deny", "deny", "deny"), (cmd, _decide(proj, cmd)[1])


# ------------------------------------------------------------------ asked in Claude Code, refused in Codex

ASKED = [
    # bare interactive TUIs
    "claude",
    "codex",
    "gemini",
    "agy",
    "opencode",
    "aider",
    "cursor-agent",
    "amp",
    "goose",
    "claude 'fix the failing test'",
    "codex 'fix the failing test'",
    "codex resume --last",
    "gemini -i 'start here'",
    # headless runs that are not provably read-only
    "claude -p x",
    "claude -p x --allowed-tools 'Read Bash'",
    "claude -p x --allowed-tools Edit",
    "claude -p x --permission-mode acceptEdits",
    "claude -p x --allowed-tools Read --permission-mode acceptEdits",
    "claude -p x --tools Bash",
    "claude -p x --allowed-tools ''",
    # 1.0.0 run-3 audit (unit 2): these pre-approve or gate tools but do not
    # limit the tools the child has (only --tools does), so they ask now
    "claude -p x --permission-mode plan",
    "claude -p x --allowed-tools Read,Grep,Glob",
    "claude -p x --allowed-tools 'Read Grep'",
    "claude -p x --allowed-tools 'Read(src/**)' --output-format json",
    "claude -p x --tools '' --mcp-config busy_mcp_config.json",
    "claude -p x --tools '' --agent writer",
    "claude -p x --tools '' --plugin-dir ./plugins",
    "claude -p x --tools '' --bg",
    "claude -p x --tools '' --worktree",
    "claude -p x --tools '' --made-up-flag",
    "claude mcp add evil -- node evil.js",
    "claude plugin install x",
    "codex exec x",
    "codex exec -s read-only -p work x",
    "codex exec -s read-only --add-dir /tmp x",
    "codex exec -s read-only --enable some_feature x",
    "codex exec -s read-only -c shell_environment_policy.inherit=all x",
    "codex exec -s read-only --made-up-flag x",
    "codex -s read-only exec x",
    "codex exec resume --last",
    "codex review --uncommitted",
    "codex apply",
    "codex sandbox macos -- touch x",
    "codex mcp add x -- y",
    "gemini -p x",
    "gemini 'one shot'",
    "gemini -p x --approval-mode plan --allowed-tools run_shell_command",
    "gemini -p x --approval-mode plan -e evil",
    "gemini extensions install https://example.com/x",
    "opencode run x",
    "aider --message x",
    "agy -p x",
    "goose run -t x",
    # a word only known at run time that could be an option
    "claude -p \"$PROMPT\" --tools ''",
    "codex exec -s \"$MODE\" x",
    "claude $FLAGS -p x",
    # xargs adds arguments Tess cannot see
    "echo --yolo | xargs codex exec -s read-only",
    # a program named only at run time with an agent's bypass flag
    "$X --dangerously-skip-permissions -p x",
    "\"$AGENT\" exec --yolo x",
]


@pytest.mark.parametrize("cmd", ASKED)
def test_agent_cli_payload_asks_in_claude_and_is_denied_in_codex(proj, cmd):
    claude, accept, codex = _all(proj, cmd)
    assert (claude, accept, codex) == ("ask", "ask", "deny"), (cmd, _decide(proj, cmd)[1])


@pytest.mark.parametrize("cmd", ["claude -p x", "codex", "codex exec x"])
def test_agent_cli_ask_is_a_deny_in_the_no_prompt_modes(proj, cmd):
    for mode in ("bypassPermissions", "dontAsk", "auto", None):
        assert _decide(proj, cmd, "claude", mode)[0] == "deny", (cmd, mode)


# ------------------------------------------------------------------ allowed: provably read-only

ALLOWED = [
    "claude --version",
    "claude -v",
    "claude --help",
    "claude mcp list",
    "claude auth status",
    "codex --version",
    "codex --help",
    "codex exec --help",
    "codex mcp list",
    "codex login status",
    "gemini --version",
    "agy --help",
    "opencode --version",
    "claude -p x --tools ''",
    "claude -p x --tools=",
    "claude -p x --tools Read,Grep,Glob",
    "claude -p x --tools Read --permission-mode plan",
    "claude --print x --tools '' --output-format stream-json --verbose",
    "claude -p x --tools '' --settings .claude/settings.json",
    "claude -p \"Review $FILE and report\" --tools ''",
    "echo 'summarise this' | claude -p --tools '' --model sonnet",
    "codex exec -s read-only x",
    "codex exec --sandbox read-only x",
    "codex exec --sandbox=read-only --ephemeral x",
    "codex exec -s read-only --json -m gpt-5.5 x </dev/null",
    "codex exec -s read-only -c model=o3 x",
    "codex exec -s read-only -o /tmp/last-message.txt x",
    "codex e -s read-only x",
    "npx @openai/codex exec -s read-only x",
    "gemini -p x --approval-mode plan",
    "gemini --prompt x --approval-mode=plan --output-format json",
    "git status && codex exec -s read-only 'review the diff'",
]

CONTROLS_ALLOWED = [
    # gate-arena/enforcement/run_verifier.py, as its argv is written
    "claude -p 'review this diff' --model opus --safe-mode --tools '' --output-format json "
    "--no-session-persistence",
    # scripts/heartbeat/tier2_classify.py: --tools "" --allowed-tools "" with an empty MCP config
    "claude -p 'classify' --model haiku --output-format json --tools '' --allowed-tools '' "
    "--strict-mcp-config --mcp-config empty_mcp_config.json",
    "claude -p x --tools '' --allowed-tools ''",
    # tests/smoke/brain_*_live.sh
    "codex exec -m gpt-5.5 -s read-only x </dev/null",
    "codex exec --ephemeral --ignore-user-config -m gpt-5.5 -s read-only x </dev/null",
    # 1.0.x (Cyra B-1): `CODEX_HOME=... codex exec ...` now asks; tests/test_v1_0_x_brain_b1_b2.py
    # hook-skipping with no tools at all
    "claude --bare -p x --tools ''",
]


@pytest.mark.parametrize("cmd", ALLOWED + CONTROLS_ALLOWED)
def test_read_only_agent_cli_is_allowed(proj, cmd):
    assert _all(proj, cmd) == ("allow", "allow", "allow"), (cmd, _decide(proj, cmd)[1])


def test_a_writing_option_still_hits_the_protected_list(proj):
    for cmd in ("codex exec -s read-only -o CLAUDE.md x",
                "codex exec -s read-only --output-last-message .claude/hooks/tess-gate.py x",
                "claude -p x --tools '' --debug-file .tess/tess.lock"):
        assert _all(proj, cmd) == ("deny", "deny", "deny"), cmd
        assert "protected Tess path" in _decide(proj, cmd)[1], cmd


# ------------------------------------------------------------------ recursion

READ_ONLY_FORMS = ["claude -p x --tools ''", "codex exec -s read-only x",
                   "gemini -p x --approval-mode plan", "claude -p 'review' --safe-mode --tools ''"]


@pytest.mark.parametrize("depth", ["1", "2", "garbage"])
@pytest.mark.parametrize("cmd", READ_ONLY_FORMS)
def test_inside_a_peer_call_every_agent_cli_is_denied(proj, monkeypatch, cmd, depth):
    monkeypatch.setenv("TESS_CONSULT_DEPTH", depth)
    assert _all(proj, cmd) == ("deny", "deny", "deny"), cmd
    assert "peer call" in _decide(proj, cmd)[1]


def test_depth_zero_and_info_calls_inside_a_peer_call(proj, monkeypatch):
    monkeypatch.setenv("TESS_CONSULT_DEPTH", "0")
    assert _all(proj, "codex exec -s read-only x") == ("allow", "allow", "allow")
    monkeypatch.setenv("TESS_CONSULT_DEPTH", "1")
    assert _all(proj, "codex --version") == ("allow", "allow", "allow")
    assert _all(proj, "git status") == ("allow", "allow", "allow")


def test_a_runtime_started_inside_another_session_cannot_start_an_agent(proj, monkeypatch):
    monkeypatch.setattr(G, "_ancestry",
                        lambda limit=40: ["python3", "sh", "codex", "zsh", "claude", "zsh", "login"])
    for cmd in READ_ONLY_FORMS:
        decision, reason = _decide(proj, cmd)
        assert decision == "deny" and "a codex session started from inside a claude session" in reason
    monkeypatch.setattr(G, "_ancestry", lambda limit=40: ["python3", "sh", "claude", "claude", "zsh"])
    assert _all(proj, READ_ONLY_FORMS[0]) == ("allow", "allow", "allow")


def test_nested_runtime_matches_the_brain_rule():
    sys.path.insert(0, str(REPO / "scripts" / "brain"))
    try:
        from brainlib.hooks import nested_runtime
    finally:
        sys.path.pop(0)
    cases = [[], ["zsh", "claude", "zsh", "login"], ["sh", "codex", "codex", "zsh"],
             ["sh", "codex", "zsh", "claude"], ["python3", "gemini", "bash", "codex", "zsh", "claude"]]
    for names in cases:
        G._STATE["nested"] = None
        orig = G._ancestry
        G._ancestry = lambda limit=40, n=names: n
        try:
            assert G._nested_runtime() == nested_runtime(names), names
        finally:
            G._ancestry = orig
            G._STATE["nested"] = None


def test_agent_names_resolve_through_package_spellings():
    for name, want in (("claude", "claude"), ("claude-code", "claude"), ("claude-code@latest", "claude"),
                       ("codex@0.158.0", "codex"), ("gemini-cli", "gemini"), ("CLAUDE", "claude"),
                       ("codex.exe", "codex"), ("cursor-agent", "cursor-agent"), ("git", None),
                       ("claudette", None), ("cursor", None)):
        assert G._agent_name(name) == want, name


@pytest.mark.parametrize("cmd", [
    "/nonexistent/cl?ude --dangerously-skip-permissions -p x",
    "/nonexistent/c[o]dex --dangerously-bypass-approvals-and-sandbox",
    "/nonexistent/gem*ni --yolo",
    "/nonexistent/CL[A]UDE --bare -p x",
])
def test_a_globbed_agent_program_word_is_judged_as_the_agent(proj, cmd):
    # A globbed program word is judged as every gated program it can match,
    # whatever is on disk; the agent CLIs are among those programs.
    assert _all(proj, cmd) == ("deny", "deny", "deny"), cmd


# ------------------------------------------------------------------ the gate run as the hook

def test_gate_hook_process_denies_and_allows(proj):
    root = proj[0]
    env = {k: v for k, v in os.environ.items() if k != "TESS_CONSULT_DEPTH"}
    env.update(CLAUDE_PROJECT_DIR=str(root), HOME=str(proj[1]))

    def run(cmd, extra=None):
        payload = {"tool_name": "Bash", "cwd": str(root), "tool_input": {"command": cmd},
                   "turn_id": "t"}
        r = subprocess.run([sys.executable, str(root / ".claude/hooks/tess-gate.py"), "--runtime", "codex"],
                           input=json.dumps(payload), capture_output=True, text=True,
                           env={**env, **(extra or {})}, timeout=120)
        out = r.stdout.strip()
        return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else "allow"

    assert run("codex exec --sandbox workspace-write 'rewrite conductor/guardrails.md'") == "deny"
    assert run("claude --dangerously-skip-permissions -p x") == "deny"
    assert run("codex exec -s read-only x", {"TESS_CONSULT_DEPTH": "1"}) == "deny"


# ------------------------------------------------------------------ flag names against the installed CLIs

@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_claude_flag_names_exist_in_claude_help():
    text = subprocess.run(["claude", "--help"], capture_output=True, text=True, timeout=60).stdout
    for flag in list(G._CLAUDE_BYPASS) + ["--bare", "--safe-mode", "--restricted", "--settings",
                                          "--setting-sources", "--tools", "--allowed-tools",
                                          "--permission-mode", "--strict-mcp-config", "--mcp-config"]:
        assert flag in text, flag
    for mode in ("bypassPermissions", "dontAsk", "auto", "plan", "acceptEdits"):
        assert mode in text, mode


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not installed")
def test_codex_flag_names_exist_in_codex_help():
    text = subprocess.run(["codex", "exec", "--help"], capture_output=True, text=True, timeout=60,
                          stdin=subprocess.DEVNULL).stdout
    hidden = {"--yolo", "--full-auto"}  # a hidden alias (0.158) and a removed flag (older releases)
    for flag in sorted(G._CODEX_BYPASS - hidden) + ["--ignore-user-config", "--sandbox", "--ephemeral",
                                                   "--output-last-message", "--json"]:
        assert flag in text, flag
    for mode in ("read-only", "workspace-write", "danger-full-access"):
        assert mode in text, mode


# ------------------------------------------------------------------ tessctl's dispatch drivers

def _brief(tmp_path, contract):
    return {"objective": "x", "output_contract": "x", "tools_sources_constraints": "x",
            "not_responsible_for": "x", "milestones": [], "escalation_trigger": "x",
            "_task_id": "t", "_mission_id": "m", "_contract_type": contract,
            "_return_manifest_path": "missions/m/returns/t.json", "_root": str(tmp_path)}


class _Done:
    returncode = 0
    stdout = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "ok"}) + "\n"
    stderr = ""


def _capture(engine, monkeypatch, linked=False):
    calls = []
    real_run = engine.subprocess.run

    def fake_run(cmd, **kw):
        if cmd[:1] == ["git"]:
            return real_run(cmd, **kw)
        calls.append((cmd, kw))
        return _Done()

    monkeypatch.setattr(engine.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(engine.subprocess, "run", fake_run)
    return calls


@pytest.mark.parametrize("contract", ["verdict", "return-manifest"])
def test_codex_driver_outside_a_linked_worktree_runs_read_only(engine, tmp_path, monkeypatch, contract):
    monkeypatch.setenv("TESS_CONSULT_DEPTH", "0")
    calls = _capture(engine, monkeypatch)
    engine.CodexExecDriver(cwd=tmp_path).dispatch(_brief(tmp_path, contract), output_schema={"type": "object"})
    cmd, kw = calls[0]
    assert cmd[:2] == ["codex", "exec"] or cmd[1] == "exec"
    assert cmd[cmd.index("-s") + 1] == "read-only"
    assert "workspace-write" not in cmd and "--full-auto" not in cmd
    # v1.0 run-escalation (Cyra F3): -o goes to a private folder outside the
    # project; tessctl installs the file itself (tests/test_v1_run_escalation.py).
    out = cmd[cmd.index("-o") + 1]
    assert not os.path.realpath(out).startswith(os.path.realpath(str(tmp_path)) + os.sep)
    assert os.path.basename(out) == "t.json"
    assert kw["stdin"] is subprocess.DEVNULL
    assert kw["env"]["TESS_DISPATCHED"] == "1" and kw["env"]["TESS_CONSULT_DEPTH"] == "1"
    assert "TESS_HEADLESS" not in kw["env"]
    assert "read-only" in cmd[-1]  # the prompt tells the child how to hand back its artifact


@pytest.mark.skipif(not HAS_GIT, reason="git not installed")
def test_codex_driver_never_gets_workspace_write_even_in_a_linked_worktree(engine, tmp_path, monkeypatch):
    # v1.0 run-escalation (Cyra F1): the driver's cwd is the Tess root, so the
    # old linked-worktree test granted workspace-write over the whole project
    # whenever the Tess checkout itself was a linked worktree.
    main = tmp_path / "main"
    subprocess.run(["git", "init", "-q", "-b", "main", str(main)], check=True)
    subprocess.run(["git", "-C", str(main), "-c", "user.email=t@t", "-c", "user.name=t", "-c",
                    "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "i"], check=True)
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", "-b", "task", str(wt)], check=True)
    monkeypatch.setenv("TESS_CONSULT_DEPTH", "0")
    calls = _capture(engine, monkeypatch)
    for cwd in (wt, main):
        for contract in ("return-manifest", "verdict"):
            engine.CodexExecDriver(cwd=cwd).dispatch(_brief(cwd, contract))
    assert len(calls) == 4
    for cmd, kw in calls:
        assert cmd[cmd.index("-s") + 1] == "read-only" and "workspace-write" not in cmd and "-o" in cmd
        assert kw["env"]["TESS_CONSULT_DEPTH"] == "1"
    # inside a peer call the driver refuses to dispatch at all
    monkeypatch.setenv("TESS_CONSULT_DEPTH", "2")
    with pytest.raises(engine.RunError, match="peer call"):
        engine.CodexExecDriver(cwd=wt).dispatch(_brief(wt, "return-manifest"))
    assert len(calls) == 4


def test_claude_driver_child_env_and_closed_stdin(engine, tmp_path, monkeypatch):
    monkeypatch.delenv("TESS_CONSULT_DEPTH", raising=False)
    monkeypatch.setenv("TESS_HEADLESS", "1")  # an inherited value does not reach the child
    calls = _capture(engine, monkeypatch)
    engine.ClaudeCliDriver(cwd=tmp_path).dispatch(_brief(tmp_path, "return-manifest"))
    cmd, kw = calls[0]
    assert "--dangerously-skip-permissions" not in cmd
    assert kw["stdin"] is subprocess.DEVNULL
    assert kw["env"]["TESS_DISPATCHED"] == "1" and kw["env"]["TESS_CONSULT_DEPTH"] == "1"
    assert "TESS_HEADLESS" not in kw["env"]
