"""
v0.2.1 (2026-09-29 security review, MEDIUM x2): hooks run only pinned
scripts; the dispatch lock dir is per-user; the dispatch secret scan fails
closed.

Every test runs the REAL hook command lines from .claude/settings.json,
through `sh -c` exactly as Claude Code does, against a copy of the shipped
files in a temp project, then tampers with that copy the way an agent could.
Each "not run" case uses a script that would write a sentinel file if it ran,
so the assertion is on behaviour (did it execute), not on a message.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SETTINGS = json.loads((REPO / ".claude" / "settings.json").read_text())
HAS_JQ = shutil.which("jq") is not None


def _cmds() -> dict:
    """{label: command} for every hook command in the shipped settings."""
    out = {}
    for event, groups in SETTINGS["hooks"].items():
        for group in groups:
            for hook in group["hooks"]:
                out[f"{event}:{group.get('matcher', '')}:{hook['command'][-60:]}"] = hook["command"]
    return out


def _cmd_for(fragment: str) -> str:
    hits = [c for c in _cmds().values() if fragment in c]
    assert hits, fragment
    return hits[0]


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "proj"
    for rel in (".tess/tess.lock", ".tess/core/pinned-scripts.sha256"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    shutil.copytree(REPO / ".claude" / "hooks", root / ".claude" / "hooks")
    shutil.copytree(REPO / "scripts" / "brain", root / "scripts" / "brain",
                    ignore=shutil.ignore_patterns("__pycache__"))
    return root


def _run(root, command, payload="{}", path=None, extra_env=None):
    env = {"CLAUDE_PROJECT_DIR": str(root), "HOME": str(root / "home"),
           "PATH": path or os.environ["PATH"], **(extra_env or {})}
    return subprocess.run(["sh", "-c", command], input=payload, capture_output=True,
                          text=True, env=env, timeout=30)


def _sentinel_script(root, rel, sentinel, shell=False):
    p = root / rel
    if shell:
        p.write_text(f'#!/usr/bin/env bash\ntouch "{sentinel}"\n')
    else:
        p.write_text(f"open({str(sentinel)!r}, 'w').write('ran')\n")


# --- static wiring --------------------------------------------------------

def test_every_hook_command_goes_through_the_pinned_launcher():
    for label, cmd in _cmds().items():
        assert ".claude/hooks/run-pinned.py" in cmd, label


def test_tessbrain_ships_and_is_wired_only_through_the_launcher():
    """v1.0: the learning tool ships, so hooks may run it, but only via the pinned launcher."""
    assert (REPO / "scripts" / "brain" / "tessbrain.py").is_file()
    cmds = [h["command"] for groups in SETTINGS["hooks"].values() for g in groups for h in g["hooks"]
            if "tessbrain" in h["command"]]
    assert len(cmds) == 4
    for cmd in cmds:
        assert cmd.startswith('python3 -I -B "$CLAUDE_PROJECT_DIR/.claude/hooks/run-pinned.py" --on-fail warn '
                              '--closure scripts/brain -- scripts/brain/tessbrain.py hook '), cmd


def test_every_hook_target_is_pinned_today(proj):
    """The shipped tree passes its own check (no false alarm on a clean install)."""
    import runpy
    m = runpy.run_path(str(REPO / ".claude" / "hooks" / "run-pinned.py"))
    for cmd in _cmds().values():
        args = cmd.split(" -- ", 1)[1].rstrip("'").split()
        closure = "scripts/brain" if "--closure scripts/brain" in cmd else None
        assert m["verify"](proj, args[0], closure).is_file(), args[0]


def test_pins_file_is_current():
    """Fails when a pinned script changed without `run-pinned.py --regen-pins` + lock re-pin."""
    import runpy
    m = runpy.run_path(str(REPO / ".claude" / "hooks" / "run-pinned.py"))
    entries = m["_lock_entries"](REPO)
    pins = m["_pins"](REPO, entries)
    rels = list(m["PIN_SET_FILES"]) + [r for t in m["PIN_SET_TREES"] for r in m["_tree_py"](REPO, t)]
    assert sorted(pins) == sorted(rels)
    for rel in rels:
        assert m["_sha256"](REPO / rel) == pins[rel], (
            f"{rel} changed; run: python3 .claude/hooks/run-pinned.py --regen-pins && "
            "./tessctl lock --regen --only .tess/core/pinned-scripts.sha256")


def test_hook_paths_are_security_tier_in_policy():
    policy = (REPO / "core" / "policy" / "policy.yaml").read_text()
    rule = policy.split("id: tess-os-security-tier-doctrine", 1)[1].split("\n    - id:", 1)[0]
    for glob in ("scripts/brain/**", ".claude/hooks/**", ".tess/core/hooks/**",
                 ".claude/settings.json", ".tess/core/pinned-scripts.sha256"):
        assert f"- {glob}\n" in rule, glob
    assert (REPO / ".tess/core/policy/policy.yaml").read_bytes() == (REPO / "core/policy/policy.yaml").read_bytes()


# --- behaviour: pristine runs, tampered does not ---------------------------

def test_pristine_onboarding_hook_runs(proj):
    r = _run(proj, _cmd_for("scripts/brain/onboard.py"))
    assert r.returncode == 0, r.stderr
    assert "TESS HOOK NOT RUN" not in r.stdout + r.stderr


def test_edited_onboard_script_is_not_run(proj, tmp_path):
    flag = tmp_path / "ran"
    _sentinel_script(proj, "scripts/brain/onboard.py", flag)
    r = _run(proj, _cmd_for("scripts/brain/onboard.py"))
    assert not flag.exists(), "tampered onboard.py executed"
    assert r.returncode == 0
    assert "TESS HOOK NOT RUN" in json.loads(r.stdout)["systemMessage"]


def test_edited_imported_module_blocks_the_onboarding_hook(proj, tmp_path):
    flag = tmp_path / "ran"
    mod = proj / "scripts/brain/oobe/hook.py"
    mod.write_text(mod.read_text() + f"\nopen({str(flag)!r}, 'w').write('ran')\n")
    _run(proj, _cmd_for("scripts/brain/onboard.py"))
    assert not flag.exists()


def test_planted_stdlib_shadow_module_blocks_the_onboarding_hook(proj, tmp_path):
    flag = tmp_path / "ran"
    _sentinel_script(proj, "scripts/brain/json.py", flag)
    r = _run(proj, _cmd_for("scripts/brain/onboard.py"))
    assert not flag.exists()
    assert "scripts/brain/json.py is not pinned" in r.stderr


def test_planted_tessbrain_is_never_run(proj, tmp_path):
    flag = tmp_path / "ran"
    _sentinel_script(proj, "scripts/brain/tessbrain.py", flag)
    for cmd in _cmds().values():
        _run(proj, cmd, payload=json.dumps({"tool_name": "Agent", "tool_input": {"prompt": "hi"}}))
    assert not flag.exists()


@pytest.mark.parametrize("hook", ["dispatch-guard.sh", "task-lock-set.sh", "utc-local-context.sh"])
def test_edited_shell_hook_is_not_run(proj, tmp_path, hook):
    flag = tmp_path / "ran"
    _sentinel_script(proj, f".claude/hooks/{hook}", flag, shell=True)
    r = _run(proj, _cmd_for(hook))
    assert not flag.exists()
    assert r.returncode == 0 and "TESS HOOK NOT RUN" in r.stderr


def test_symlinked_hook_is_not_run(proj, tmp_path):
    flag = tmp_path / "ran"
    evil = tmp_path / "evil.sh"
    evil.write_text(f'#!/usr/bin/env bash\ntouch "{flag}"\n')
    target = proj / ".claude/hooks/utc-local-context.sh"
    target.unlink()
    target.symlink_to(evil)
    _run(proj, _cmd_for("utc-local-context.sh"))
    assert not flag.exists()


def test_repinning_the_pin_list_without_the_lock_is_refused(proj, tmp_path):
    """Editing a script AND its line in pinned-scripts.sha256 is not enough: tess.lock pins the list."""
    import hashlib
    flag = tmp_path / "ran"
    _sentinel_script(proj, "scripts/brain/onboard.py", flag)
    pins = proj / ".tess/core/pinned-scripts.sha256"
    new = hashlib.sha256((proj / "scripts/brain/onboard.py").read_bytes()).hexdigest()
    pins.write_text("\n".join(
        (f"{new}  scripts/brain/onboard.py" if l.endswith("scripts/brain/onboard.py") else l)
        for l in pins.read_text().splitlines()) + "\n")
    r = _run(proj, _cmd_for("scripts/brain/onboard.py"))
    assert not flag.exists()
    assert "pinned-scripts.sha256 does not match" in r.stderr


# --- vault dispatch scan: fail closed ---------------------------------------

VAULT = ".claude/hooks/vault-dispatch-scan.py"


def test_vault_scan_allows_a_clean_dispatch(proj):
    r = _run(proj, _cmd_for("vault-dispatch-scan.py"),
             payload=json.dumps({"tool_name": "Agent", "tool_input": {"prompt": "summarise the brief"}}))
    assert r.returncode == 0, r.stderr


def test_vault_scan_blocks_a_secret(proj):
    token = "ghp_" + "A" * 36
    r = _run(proj, _cmd_for("vault-dispatch-scan.py"),
             payload=json.dumps({"tool_name": "Agent", "tool_input": {"prompt": f"use {token}"}}))
    assert r.returncode == 2


@pytest.mark.parametrize("payload", ["not json", "[1, 2]", ""])
def test_vault_scan_blocks_when_it_cannot_read_the_call(proj, payload):
    r = _run(proj, _cmd_for("vault-dispatch-scan.py"), payload=payload)
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "could not run" in r.stderr


def test_tampered_vault_scan_blocks_the_dispatch(proj, tmp_path):
    flag = tmp_path / "ran"
    _sentinel_script(proj, VAULT, flag)
    r = _run(proj, _cmd_for("vault-dispatch-scan.py"),
             payload=json.dumps({"tool_name": "Agent", "tool_input": {"prompt": "x"}}))
    assert r.returncode == 2 and not flag.exists()


def test_vault_scan_blocks_when_python3_is_missing(proj, tmp_path):
    empty = tmp_path / "nobin"
    empty.mkdir()
    r = subprocess.run(["/bin/sh", "-c", _cmd_for("vault-dispatch-scan.py")], input="{}",  # no python3 on PATH
                       capture_output=True, text=True,
                       env={"CLAUDE_PROJECT_DIR": str(proj), "PATH": str(empty)})
    assert r.returncode == 2 and "python3 was not found" in r.stderr


# --- dispatch lock dir is per-user ------------------------------------------

def test_no_shipped_hook_uses_the_shared_tmp_lock_dir():
    for base in (".claude/hooks", ".tess/core/hooks"):
        for p in (REPO / base).iterdir():
            if not p.is_file():
                continue  # e.g. a __pycache__ left by a local import of run-pinned.py
            for line in p.read_text().splitlines():
                if line.startswith("LOCK_DIR="):
                    assert "/tmp" not in line, (p, line)


@pytest.mark.skipif(not HAS_JQ, reason="jq required by the lock hooks")
def test_lock_set_creates_a_private_per_user_dir(proj):
    payload = json.dumps({"session_id": "s1", "hook_event_name": "PreToolUse"})
    r = _run(proj, _cmd_for("task-lock-set.sh"), payload=payload,
             extra_env={"XDG_CACHE_HOME": str(proj / "cache")})
    assert r.returncode == 0, r.stderr
    d = proj / "cache" / "tess" / "dispatch-locks"
    assert (d / "s1.lock").read_text().strip() == "1"
    assert stat.S_IMODE(d.stat().st_mode) == 0o700


@pytest.mark.skipif(not HAS_JQ, reason="jq required by dispatch-guard")
def test_guard_ignores_locks_in_a_group_or_world_writable_dir(proj):
    d = proj / "shared-locks"
    d.mkdir()
    (d / "planted.lock").write_text("1")
    os.chmod(d, 0o777)
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf build"}})
    r = _run(proj, _cmd_for("dispatch-guard.sh"), payload=payload, extra_env={"TESS_LOCK_DIR": str(d)})
    assert "RULE ZERO WARNING" in r.stdout, "planted lock in a shared dir silenced the guard"
    os.chmod(d, 0o700)
    r = _run(proj, _cmd_for("dispatch-guard.sh"), payload=payload, extra_env={"TESS_LOCK_DIR": str(d)})
    assert "RULE ZERO WARNING" not in r.stdout, "a genuine private lock should still suppress the warning"
