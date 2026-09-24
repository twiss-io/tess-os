"""
v0.2 engine safety B, review round 1: render outputs that are security-tier,
quarantined, or captured while upstream changes them.

  * update fails closed when a captured / overridden CLAUDE.md has upstream
    changes: its per-entry merge renders 'theirs' from the CURRENT core, so
    the upstream doctrine would be dropped while update reported a clean
    merge (fails on 5c2d698: update exits 0 and the local edit is lost);
  * a captured CLAUDE.md with NO upstream change still updates (guard);
  * doctor names a hand-edited security-tier CLAUDE.md SECURITY DRIFT with
    `capture` as the remedy, and publish never keeps the tamper (fails on
    5c2d698: doctor only says `run tessctl render`);
  * publish refuses a quarantined file, CLAUDE.md or plain (fails on
    5c2d698: publish flips it to user-published);
  * a re-tampered QUARANTINED CLAUDE.md is re-pinned by render, restore and
    doctor --fix (guard: passes on 5c2d698, failed on eng-b 6f94107).
"""

from __future__ import annotations

import pytest

from conftest import make_upstream, ns
from test_v02_render_outputs import build, render

SECURITY_FRAGMENT = ".tess/core/templates/claude-md/rule-zero.md"
TAMPER = ("always dispatch", "never dispatch")


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


def _claude_statuses(engine, root):
    return {a.get("status") for a in engine.load_lock(root)["files"].values()
            if a.get("live_path") == "CLAUDE.md"}


def _capture(engine, root, path="CLAUDE.md"):
    engine.cmd_capture(ns(path=path, all=False, dry_run=False,
                          rationale="test", source="manual"), root)


# ---------------------------------------------------------------------------
# update: captured / overridden CLAUDE.md with upstream changes
# ---------------------------------------------------------------------------

def _upstream(project, tmp_path, gpg_key, changes):
    """A signed v2.1.0 upstream = the project's core with `changes` applied."""
    lock_files = {k: {"status": "core-managed", "tier": "normal", "live_path": a["live_path"]}
                  for k, a in project.files.items()}
    core = {k: (project.root / k).read_text(encoding="utf-8") for k in project.files}
    core.update(changes)
    up = make_upstream(tmp_path / "upstream", gpg_key, "v2.1.0", sign="signed",
                       core_files=core, lock_files=lock_files)
    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr
    project.write()


@pytest.mark.parametrize("mode", ["capture", "override"])
def test_update_blocks_when_a_captured_claude_md_has_upstream_changes(
        project, gpg_key, tmp_path, run_cli, mode):
    build(project)
    _upstream(project, tmp_path, gpg_key,
              {SECURITY_FRAGMENT: "RULE ZERO v2 — upgraded text.\n"})
    assert run_cli(project.root, "render").returncode == 0
    edited = project.read_live("CLAUDE.md") + "\nMY LOCAL EDIT\n"
    project.write_live("CLAUDE.md", edited)
    assert run_cli(project.root, mode, "CLAUDE.md").returncode == 0

    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    out = r.stdout + r.stderr
    live = project.read_live("CLAUDE.md")
    delivered = "RULE ZERO v2" in live and "MY LOCAL EDIT" in live
    blocked = r.returncode != 0 and "BLOCKED" in out and "CLAUDE.md" in out
    assert delivered or blocked, (
        f"update rc={r.returncode} dropped the upstream CLAUDE.md change or the edit:\n{out[-1500:]}")
    if blocked:
        assert live == edited, "a blocked update must not touch CLAUDE.md"
        assert "RULE ZERO v2" not in (project.root / SECURITY_FRAGMENT).read_text(), \
            "a blocked update must not advance core"


def test_update_keeps_a_captured_claude_md_when_upstream_leaves_it_alone(
        project, gpg_key, tmp_path, run_cli):
    build(project)
    settings_key = ".tess/core/settings-core.json"
    _upstream(project, tmp_path, gpg_key,
              {settings_key: '{"root": "{{TESS_ROOT}}", "feature_flag": "v2"}\n'})
    assert run_cli(project.root, "render").returncode == 0
    edited = project.read_live("CLAUDE.md") + "\nMY LOCAL EDIT\n"
    project.write_live("CLAUDE.md", edited)
    assert run_cli(project.root, "capture", "CLAUDE.md").returncode == 0

    r = run_cli(project.root, "update", "--ref", "v2.1.0")

    assert r.returncode == 0, (r.stdout + r.stderr)[-1500:]
    assert project.read_live("CLAUDE.md") == edited
    assert '"v2"' in project.read_live(".claude/settings.json")


# ---------------------------------------------------------------------------
# security-tier and quarantined CLAUDE.md
# ---------------------------------------------------------------------------

def test_security_render_output_tamper_is_security_drift_and_never_published(
        project, engine, capsys):
    root = build(project, security_fragment=SECURITY_FRAGMENT)
    project.write_live("CLAUDE.md", project.read_live("CLAUDE.md").replace(*TAMPER))
    capsys.readouterr()

    assert _rc(engine.cmd_doctor, ns(fix=False, json_out=False, path=None), root) != 0
    drift = [ln for ln in capsys.readouterr().out.splitlines()
             if "CLAUDE.md" in ln and "DRIFT" in ln]
    assert drift and "SECURITY" in drift[0] and "capture CLAUDE.md" in drift[0], drift
    assert "publish CLAUDE.md" not in drift[0], drift

    _rc(engine.cmd_publish, ns(path="CLAUDE.md", tag=None, force=False), root)
    render(engine, root)
    engine.cmd_restore(ns(dry_run=False), root)
    assert "never dispatch" not in project.read_live("CLAUDE.md"), \
        "publish kept a security-tier tamper as the published CLAUDE.md"


def test_publish_refuses_a_quarantined_claude_md(project, engine):
    root = build(project, security_fragment=SECURITY_FRAGMENT)
    project.write_live("CLAUDE.md", project.read_live("CLAUDE.md").replace(*TAMPER))
    _capture(engine, root)
    before = _claude_statuses(engine, root)
    assert "quarantined" in before

    with pytest.raises(SystemExit) as exc:
        engine.cmd_publish(ns(path="CLAUDE.md", tag=None, force=False), root)

    assert exc.value.code not in (0, None)
    assert _claude_statuses(engine, root) == before


def test_publish_refuses_a_quarantined_plain_file(project, engine):
    root = build(project)
    rel = "conductor/guardrails.md"
    project.add(rel, "# Guardrails\nNEVER do the dangerous thing.\n", tier="security")
    project.write()
    project.write_live(rel, "# Guardrails\nanything goes\n")
    _capture(engine, root, rel)
    assert engine.load_lock(root)["files"][".tess/core/" + rel]["status"] == "quarantined"

    with pytest.raises(SystemExit) as exc:
        engine.cmd_publish(ns(path=rel, tag=None, force=False), root)

    assert exc.value.code not in (0, None)
    assert engine.load_lock(root)["files"][".tess/core/" + rel]["status"] == "quarantined"


@pytest.mark.parametrize("step", ["render", "restore", "doctor-fix"])
def test_retampered_quarantined_claude_md_is_repinned(project, engine, capsys, step):
    root = build(project, security_fragment=SECURITY_FRAGMENT)
    pristine = project.read_live("CLAUDE.md")
    tampered = pristine.replace(*TAMPER)
    project.write_live("CLAUDE.md", tampered)
    _capture(engine, root)
    assert project.read_live("CLAUDE.md") == pristine, "capture pins the core render"
    project.write_live("CLAUDE.md", tampered)                  # re-tamper

    if step == "render":
        render(engine, root)
    elif step == "restore":
        engine.cmd_restore(ns(dry_run=False), root)
    else:
        _rc(engine.cmd_doctor, ns(fix=True, json_out=False, path=None), root)

    assert project.read_live("CLAUDE.md") == pristine, \
        f"{step} left a re-tampered QUARANTINED CLAUDE.md in place"
