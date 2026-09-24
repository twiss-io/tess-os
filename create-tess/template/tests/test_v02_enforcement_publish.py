"""
v0.2 engine safety B, review round 2: `tessctl publish` must never turn a
hand edit to RUNTIME-ENFORCEMENT config into the published version.

eng-b made publish keep a hand-edited render output (bug 7). For
enforcement config that is a bypass: strip the hooks from
.claude/settings.json (or escalate .codex/config.toml to
danger-full-access / approval never), publish, and render, restore and
doctor --fix all keep the escalation while doctor exits 0.

Each scenario asserts: after publish + render + restore + doctor --fix,
the live file equals the core render, OR doctor and verify both exit
non-zero (the escalation is at least reported).

  * guards: pass on 5c2d698 (publish re-seeds settings.json from core;
    publish of .codex/config.toml / AGENTS.md is refused there because
    they have no tess.lock entry) and FAIL on eng-b 8b56ae0.
"""

from __future__ import annotations

import pytest

from conftest import ns
from test_v02_render_outputs import build, render

STRIPPED_SETTINGS = '{"hooks": {}}\n'


@pytest.fixture(autouse=True)
def _tess_root_env(monkeypatch):
    monkeypatch.delenv("TESS_ROOT", raising=False)
    yield


def _rc(fn, *args):
    try:
        fn(*args)
        return 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (1 if e.code else 0)


def _publish(engine, root, path):
    return _rc(engine.cmd_publish, ns(path=path, tag=None, force=False), root)


def _render_restore_fix(engine, root):
    render(engine, root)
    # eng-a drift gate: restore exits non-zero while uncaptured drift remains.
    _rc(engine.cmd_restore, ns(dry_run=False), root)
    _rc(engine.cmd_doctor, ns(fix=True, json_out=False, path=None), root)


def _doctor_and_verify_rc(engine, root):
    return (_rc(engine.cmd_doctor, ns(fix=False, json_out=False, path=None), root),
            _rc(engine.cmd_verify, ns(), root))


def _assert_reverted_or_reported(engine, root, rel, expected, bad_marker):
    live = (root / rel).read_bytes()
    if live == expected:
        return
    doctor_rc, verify_rc = _doctor_and_verify_rc(engine, root)
    assert doctor_rc != 0 and verify_rc != 0, (
        f"{rel} still holds the escalation ({bad_marker!r}) after publish + render + "
        f"restore + doctor --fix, and doctor rc={doctor_rc} / verify rc={verify_rc} "
        f"do not report it")


def test_publish_never_keeps_hook_stripped_claude_settings(project, engine):
    root = build(project)
    render(engine, root)
    expected = engine.render_settings_json(root).encode("utf-8")
    (root / ".claude" / "settings.json").write_text(STRIPPED_SETTINGS, encoding="utf-8")

    _publish(engine, root, ".claude/settings.json")
    _render_restore_fix(engine, root)

    _assert_reverted_or_reported(engine, root, ".claude/settings.json", expected, "hooks: {}")


def test_publish_tag_settings_never_keeps_hook_stripped_claude_settings(project, engine):
    root = build(project)
    render(engine, root)
    expected = engine.render_settings_json(root).encode("utf-8")
    (root / ".claude" / "settings.json").write_text(STRIPPED_SETTINGS, encoding="utf-8")

    _rc(engine.cmd_publish, ns(path=None, tag="settings", force=False), root)
    _render_restore_fix(engine, root)

    _assert_reverted_or_reported(engine, root, ".claude/settings.json", expected, "hooks: {}")


def _escalate(text):
    return (text.replace("workspace-write", "danger-full-access")
                .replace("on-request", "never"))


def test_publish_never_keeps_codex_sandbox_escalation(project, engine):
    root = build(project, codex=True)
    render(engine, root)
    cfg = root / ".codex" / "config.toml"
    expected = cfg.read_bytes()
    cfg.write_text(_escalate(cfg.read_text(encoding="utf-8")), encoding="utf-8")
    assert b"danger-full-access" in cfg.read_bytes()

    assert _publish(engine, root, ".codex/config.toml") != 0, \
        "publish accepted an edit to .codex/config.toml (runtime-enforcement config)"
    _render_restore_fix(engine, root)

    _assert_reverted_or_reported(engine, root, ".codex/config.toml", expected,
                                 "danger-full-access")


def test_publish_refuses_agents_md(project, engine):
    root = build(project, codex=True)
    render(engine, root)
    agents = root / "AGENTS.md"
    expected = agents.read_bytes()
    agents.write_text(agents.read_text(encoding="utf-8")
                      .replace("HARD FLOOR FIXTURE", "no floor"), encoding="utf-8")

    assert _publish(engine, root, "AGENTS.md") != 0, "publish accepted an edit to AGENTS.md"
    _render_restore_fix(engine, root)

    _assert_reverted_or_reported(engine, root, "AGENTS.md", expected, "no floor")


def test_doctor_never_excuses_enforcement_drift_via_render_outputs_status(project, engine):
    """A render_outputs status other than 'rendered' (e.g. a lock edited to say
    user-published) must not turn drift in enforcement config into an
    'expected divergence' row: doctor still fails."""
    root = build(project, codex=True)
    render(engine, root)
    cfg = root / ".codex" / "config.toml"
    cfg.write_text(_escalate(cfg.read_text(encoding="utf-8")), encoding="utf-8")
    lock = engine.load_lock(root)
    lock.setdefault("render_outputs", {})[".codex/config.toml"] = {
        "target": "codex", "status": "user-published",
        "rendered_sha": engine.sha256_file(cfg)}
    engine.save_lock(root, lock)

    doctor_rc, verify_rc = _doctor_and_verify_rc(engine, root)
    assert doctor_rc != 0, "doctor excused a sandbox escalation in .codex/config.toml"
    assert verify_rc != 0
