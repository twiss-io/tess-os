"""
v0.2 engine safety B, review round 3: `tessctl capture` / `tessctl override`
must never keep a hook-stripped .claude/settings.json.

eng-b made write_render_output honour locally-modified / patch-override /
held. Before eng-b (5c2d698) render ignored them for settings.json, so the
next render/restore/init/update rewrote the hooks. With the statuses
honoured, an agent (or an operator following doctor's advice) could strip the
hooks, `tessctl capture` them (normal tier: no TTY, rationale or approval),
and render, restore and doctor stayed silent for good.

  (a) strip hooks, capture   -> refused (single path and bulk scan)
  (b) strip hooks, override  -> refused
  (c) a pre-existing capture/override/held status on settings.json (an older
      install) is ignored: render / restore / doctor --fix re-pin the hooks
      and clear the status
  (d) doctor FAILs on an enforcement output that lacks the rendered hooks or
      carries a capture/override status

All guards FAIL on eng-b 4df1798.
"""

from __future__ import annotations

import json

import pytest

import test_v02_render_outputs as tro
from conftest import ns
from test_v02_render_outputs import SETTINGS_KEY, build, render

SETTINGS_REL = ".claude/settings.json"
HOOKED_SETTINGS = json.dumps({
    "root": "{{TESS_ROOT}}",
    "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": "{{TESS_ROOT}}/.claude/hooks/guard.sh"}]}]},
}) + "\n"
STRIPPED_SETTINGS = '{"hooks": {}}\n'


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("TESS_ROOT", raising=False)
    monkeypatch.setattr(tro, "SETTINGS", HOOKED_SETTINGS)
    yield


def _rc(fn, *args):
    try:
        fn(*args)
        return 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (1 if e.code else 0)


def _setup(project, engine):
    root = build(project)
    render(engine, root)
    expected = engine.render_settings_json(root).encode("utf-8")
    assert b"guard.sh" in expected
    assert (root / SETTINGS_REL).read_bytes() == expected
    (root / SETTINGS_REL).write_text(STRIPPED_SETTINGS, encoding="utf-8")
    return root, expected


def _settings_status(engine, root):
    return engine.load_lock(root)["files"][SETTINGS_KEY].get("status", "core-managed")


def _doctor_rc(engine, root, fix=False):
    return _rc(engine.cmd_doctor, ns(fix=fix, json_out=False, path=None), root)


# (a) ------------------------------------------------------------------------

def test_capture_refuses_hook_stripped_settings(project, engine):
    root, _expected = _setup(project, engine)
    rc = _rc(engine.cmd_capture, ns(path=SETTINGS_REL, all=False, dry_run=False,
                                    rationale="", source="manual"), root)
    assert rc != 0, "capture accepted a hook-stripped .claude/settings.json"
    assert _settings_status(engine, root) == "core-managed"
    assert _doctor_rc(engine, root) != 0, "doctor is silent about stripped hooks"


def test_bulk_capture_never_captures_settings(project, engine):
    root, _expected = _setup(project, engine)
    _rc(engine.cmd_capture, ns(path=None, all=True, dry_run=False,
                               rationale="", source="manual"), root)
    assert _settings_status(engine, root) == "core-managed", \
        "capture --all captured a hook-stripped .claude/settings.json"


# (b) ------------------------------------------------------------------------

def test_override_refuses_hook_stripped_settings(project, engine):
    root, _expected = _setup(project, engine)
    rc = _rc(engine.cmd_override, ns(path=SETTINGS_REL), root)
    assert rc != 0, "override accepted a hook-stripped .claude/settings.json"
    assert _settings_status(engine, root) == "core-managed"
    assert "override_diff" not in engine.load_lock(root)["files"][SETTINGS_KEY]


# (c) ------------------------------------------------------------------------

def _plant_status(engine, root, status):
    lock = engine.load_lock(root)
    lock["files"][SETTINGS_KEY]["status"] = status
    if status == "patch-override":
        lock["files"][SETTINGS_KEY]["override_diff"] = "--- a\n+++ b\n"
    engine.save_lock(root, lock)


@pytest.mark.parametrize("status", ["locally-modified", "patch-override", "held"])
@pytest.mark.parametrize("how", ["render", "restore", "doctor-fix"])
def test_preexisting_status_is_ignored_and_hooks_restored(project, engine, status, how):
    root, expected = _setup(project, engine)
    _plant_status(engine, root, status)

    if how == "render":
        render(engine, root)
    elif how == "restore":
        engine.cmd_restore(ns(dry_run=False), root)
    else:
        _doctor_rc(engine, root, fix=True)

    assert (root / SETTINGS_REL).read_bytes() == expected, \
        f"{how} kept a hook-stripped settings.json with status {status}"
    assert _settings_status(engine, root) == "core-managed", \
        f"{how} left the ignored {status} status on settings.json"
    assert _doctor_rc(engine, root) == 0


# (d) ------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["locally-modified", "patch-override", "held", "user-published"])
def test_doctor_fails_on_stripped_enforcement_output(project, engine, status, capsys):
    root, _expected = _setup(project, engine)
    _plant_status(engine, root, status)
    capsys.readouterr()
    assert _doctor_rc(engine, root) != 0, \
        f"doctor passed a hook-stripped settings.json with status {status}"
    out = capsys.readouterr().out
    assert "ENFORCEMENT BYPASS" in out and "settings.local.json" in out
    js = _rc(engine.cmd_doctor, ns(fix=False, json_out=True, path=None), root)
    assert js != 0, "doctor --json passed a hook-stripped settings.json"


def test_doctor_fails_on_captured_status_even_with_hooks_intact(project, engine):
    root, expected = _setup(project, engine)
    (root / SETTINGS_REL).write_bytes(expected)
    _plant_status(engine, root, "locally-modified")
    assert _doctor_rc(engine, root) != 0


# review round 4 ---------------------------------------------------------------
# An UNCAPTURED hook strip is re-pinned (self-healing, as on main): render,
# restore, doctor --fix and the first render on a v0.1.x lock all restore the
# hooks, snapshot the stripped bytes, and doctor passes afterwards.

def _assert_repinned(engine, root, expected):
    assert (root / SETTINGS_REL).read_bytes() == expected, "the hook strip survived"
    snaps = list((root / engine.SNAPSHOTS_DIR).glob("*/.claude/settings.json"))
    assert any(p.read_text(encoding="utf-8") == STRIPPED_SETTINGS for p in snaps), \
        "the replaced (stripped) bytes were not snapshotted"
    assert _doctor_rc(engine, root) == 0


@pytest.mark.parametrize("how", ["render", "restore", "doctor-fix"])
def test_uncaptured_strip_is_repinned(project, engine, how, capsys):
    root, expected = _setup(project, engine)
    claude_edit = (root / "CLAUDE.md").read_text(encoding="utf-8") + "\nHAND EDIT\n"
    (root / "CLAUDE.md").write_text(claude_edit, encoding="utf-8")
    capsys.readouterr()
    if how == "render":
        render(engine, root)
    elif how == "restore":
        engine.cmd_restore(ns(dry_run=False), root)
    else:
        _doctor_rc(engine, root, fix=True)
    out = capsys.readouterr().out
    assert "RE-PINNED" in out and "snapshots" in out
    # CLAUDE.md is not enforcement config: its hand edit is still KEPT.
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == claude_edit
    (root / "CLAUDE.md").write_bytes(engine.render_claude_md(root).encode("utf-8"))
    _assert_repinned(engine, root, expected)


def test_uncaptured_strip_repinned_by_first_render_on_v01x_lock(project, engine):
    project.framework["version"] = "0.1.1"
    project.framework["upstream_ref"] = "v0.1.1"
    root = build(project)
    expected = engine.render_settings_json(root).encode("utf-8")
    assert "render_outputs" not in engine.load_lock(root)
    (root / SETTINGS_REL).write_text(STRIPPED_SETTINGS, encoding="utf-8")
    render(engine, root)
    _assert_repinned(engine, root, expected)


def test_seed_never_lists_enforcement_outputs_as_hand_edited(project, engine):
    project.framework["version"] = "0.1.1"
    root = build(project)
    (root / SETTINGS_REL).write_text(STRIPPED_SETTINGS, encoding="utf-8")
    lock = engine.load_lock(root)
    out = engine.seed_render_output_records(root, lock)
    assert SETTINGS_REL not in out["hand_edited"]


def test_doctor_fails_on_disable_all_hooks_in_settings_local(project, engine, capsys):
    root = build(project)
    render(engine, root)
    assert _doctor_rc(engine, root) == 0
    (root / ".claude" / "settings.local.json").write_text(
        '{"disableAllHooks": true}\n', encoding="utf-8")
    capsys.readouterr()
    assert _doctor_rc(engine, root) != 0, "doctor passed disableAllHooks in settings.local.json"
    assert "disableAllHooks" in capsys.readouterr().out


@pytest.mark.parametrize("sel", [dict(path=SETTINGS_REL, tag=None),
                                 dict(path=SETTINGS_KEY, tag=None),
                                 dict(path=None, tag="settings")])
def test_publish_refuses_claude_settings(project, engine, sel):
    root, _expected = _setup(project, engine)
    rc = _rc(engine.cmd_publish, ns(force=False, **sel), root)
    assert rc != 0, "publish accepted .claude/settings.json"
    assert _settings_status(engine, root) == "core-managed"


def test_reset_clears_user_published_settings(project, engine):
    root, expected = _setup(project, engine)
    _plant_status(engine, root, "user-published")
    assert _rc(engine.cmd_reset, ns(path=SETTINGS_REL), root) == 0
    assert (root / SETTINGS_REL).read_bytes() == expected
    assert _settings_status(engine, root) == "core-managed"
    assert _doctor_rc(engine, root) == 0
