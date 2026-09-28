"""v0.2.1 Codex parity: roles, onboarding, brain capture.

Pins what the live Codex runs (codex-cli 0.145, gpt-5.5) depended on:

* AGENTS.md names every INSTALLED role (the list Codex answered with) and
  tells the top-level session how to spawn one as a Codex custom agent
  (`spawn_agent` + `agent_type`, no full-history fork, wait before close),
  and never to pass a generic agent off as a role.
* The roster line is computed, so a benched role drops out of AGENTS.md.
* `.codex/config.toml` carries the SessionStart onboarding hook (inline, so
  an operator's own `.codex/hooks.json` stays theirs) and keeps the shipped
  approval/sandbox defaults.
* The onboarding hook adds a task-first clarifier for Codex only; Claude's
  text is unchanged.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import _brain_oobe_helpers as h

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.9/3.10 CI leg
    tomllib = None

REPO = Path(__file__).resolve().parent.parent
ROLE_FILES = sorted((REPO / ".tess" / "core" / "agents-dispatch").glob("*.md"))


def test_agents_md_names_every_installed_role(engine):
    roles = engine._installed_role_names(REPO)
    assert roles, "the shipped roster has installed roles"
    text = engine.render_agents_md(REPO)
    line = engine._worker_roles_line(REPO)
    assert line in text
    for role in roles:
        assert f"`{role}` " in line
        assert (REPO / ".codex" / "agents" / f"{role}.toml").is_file()
    assert "`leah` Researcher" in line and "`reid` Code reviewer" in line
    assert "{{WORKER_ROLES}}" not in text


def test_agents_md_spawn_guidance_matches_codex_tool_contract(engine):
    text = engine.render_agents_md(REPO)
    for needle in ("spawn_agent", "`agent_type` set to the role name", "fork_context",
                   "`wait_agent` for its result before any `close_agent`",
                   "never start a generic agent and call it that role",
                   "never spawn or re-delegate"):
        assert needle in text, needle
    # The old blanket ban is what made Codex answer "I cannot dispatch roles".
    assert "Do not try to dispatch, delegate or spawn nested agents" not in text


def test_benched_role_drops_out_of_the_roster_line(engine, monkeypatch):
    roles = engine._installed_role_names(REPO)
    monkeypatch.setattr(engine, "_installed_role_names", lambda root: roles[1:])
    line = engine._worker_roles_line(REPO)
    assert f"`{roles[0]}` " not in line and f"`{roles[1]}` " in line
    monkeypatch.setattr(engine, "_installed_role_names", lambda root: [])
    assert engine._worker_roles_line(REPO) == "none installed"


def test_roster_titles_come_from_role_frontmatter(engine):
    line = engine._worker_roles_line(REPO)
    for path in ROLE_FILES:
        desc = next(l for l in path.read_text().splitlines() if l.startswith("description:"))
        title = desc.split(":", 1)[1].strip().split(". ", 1)[0].rstrip(".")
        assert f"`{path.stem}` {title}" in line


def test_committed_codex_config_equals_render(engine):
    assert (REPO / ".codex" / "config.toml").read_text() == engine.render_codex_config_toml(REPO)


@pytest.mark.skipif(tomllib is None, reason="tomllib needs Python 3.11+")
def test_codex_config_has_onboarding_session_start_hook(engine):
    cfg = tomllib.loads(engine.render_codex_config_toml(REPO))
    assert cfg["approval_policy"] == "on-request" and cfg["sandbox_mode"] == "workspace-write"
    groups = cfg["hooks"]["SessionStart"]
    assert len(groups) == 1 and groups[0]["matcher"] == "startup|resume|clear|compact"
    handler, brain = groups[0]["hooks"]  # v1.0: onboarding first, then the learning-loop snapshot
    assert handler["type"] == "command" and handler["timeout"] == 5
    cmd = handler["command"]
    assert "scripts/brain/onboard.py" in cmd and "--runtime codex" in cmd
    assert "git rev-parse --show-toplevel" in cmd and "|| exit 0" in cmd
    assert '"$l" --on-fail warn --closure scripts/brain -- scripts/brain/onboard.py' in cmd  # pinned launcher
    assert "scripts/brain/tessbrain.py hook session-start --runtime codex" in brain["command"]


@pytest.mark.skipif(tomllib is None, reason="tomllib needs Python 3.11+")
def test_rendered_codex_hook_command_runs_from_a_subdirectory(engine, tmp_path):
    """Codex runs hook commands with the session cwd, which can be a
    subdirectory: the command must find the repo root itself."""
    cfg = tomllib.loads(engine.render_codex_config_toml(REPO))
    cmd = cfg["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    root = h.mini_instance(tmp_path)
    import shutil  # v1.0: the hook runs through the pinned launcher, so the instance carries it and its pins
    for rel in (".claude/hooks/run-pinned.py", ".tess/tess.lock", ".tess/core/pinned-scripts.sha256"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(REPO / rel), str(root / rel))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    sub = root / "docs" / "deep"
    sub.mkdir(parents=True)
    done = subprocess.run(["sh", "-c", cmd], cwd=str(sub), input="{}", capture_output=True,
                          text=True, env=h.env({}), timeout=60)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    ctx = out["additionalContext"]
    assert ctx.startswith("ONBOARDING PENDING (step 1/7)")
    assert "do the task first with the tools it needs" in ctx
    assert "without running a tool first" in ctx


def test_rendered_codex_onboarding_hook_refuses_an_edited_script(engine, tmp_path):
    """v1.0.0: the Codex onboarding hook has the same run-pinned hash check as
    Claude's: an onboard.py whose bytes are not the pinned release is never
    run (the launcher warns and the hook exits 0, so the turn is not blocked)."""
    if tomllib is None:
        pytest.skip("tomllib (Python 3.11+) required")
    cfg = tomllib.loads(engine.render_codex_config_toml(REPO))
    cmd = cfg["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "scripts/brain/onboard.py" in cmd
    root = h.mini_instance(tmp_path)
    import shutil
    for rel in (".claude/hooks/run-pinned.py", ".tess/tess.lock", ".tess/core/pinned-scripts.sha256"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(REPO / rel), str(root / rel))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    marker = tmp_path / "tampered-code-ran"
    script = root / "scripts" / "brain" / "onboard.py"
    script.write_text(script.read_text() + f"\nopen({str(marker)!r}, 'w').write('x')\n")
    done = subprocess.run(["sh", "-c", cmd], cwd=str(root), input="{}", capture_output=True,
                          text=True, env=h.env({}), timeout=60)
    assert done.returncode == 0, done.stderr
    assert not marker.exists(), "an edited onboard.py ran from the Codex hook"
    assert "ONBOARDING PENDING" not in done.stdout
    assert "onboard.py" in done.stderr + done.stdout  # the launcher names what it refused


def test_rendered_codex_hook_is_silent_outside_an_instance(engine, tmp_path):
    if tomllib is None:
        pytest.skip("tomllib needs Python 3.11+")
    cmd = tomllib.loads(engine.render_codex_config_toml(REPO))["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    done = subprocess.run(["sh", "-c", cmd], cwd=str(tmp_path), input="{}", capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0 and done.stdout == ""


def test_claude_hook_text_has_no_codex_clarifier(tmp_path):
    root = h.mini_instance(tmp_path)
    done = h.onboard(root, "hook", "session-start", "--runtime", "claude", stdin="{}", extra_env={})
    ctx = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "do the task first with the tools it needs" not in ctx
