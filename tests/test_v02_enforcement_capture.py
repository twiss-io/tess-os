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
