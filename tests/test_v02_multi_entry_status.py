"""
v0.2 engine safety B — bug 8: one live file, several tess.lock entries.

CLAUDE.md is backed by 6 lock entries (the .tpl plus 5 fragments). Before
v0.2 every status command acted on the FIRST matching entry and stopped, so
restore/render kept overwriting the live file through the others, and doctor
said OK. These tests pin the fixed behaviour:

  * publish / override / capture / reset act on every entry of the live path;
  * capture of a live file that has ANY security-tier entry quarantines all of
    them (no half-quarantined, half-captured CLAUDE.md);
  * restore and render use the EFFECTIVE status (most protective wins);
  * doctor FAILS on a lock whose entries disagree (human and --json), and
    update's Step 1 gate blocks on it.

The first eight tests fail on 5c2d698 by assertion. The last two exercise the
new helpers directly.
"""

from __future__ import annotations

import json

import pytest

from conftest import ns
from test_v02_render_outputs import FRAGMENTS, TPL_KEY, build, render

CLAUDE_KEYS = [TPL_KEY, *FRAGMENTS]
SECURITY_FRAGMENT = ".tess/core/templates/claude-md/rule-zero.md"


@pytest.fixture(autouse=True)
def _tess_root_env(monkeypatch):
    monkeypatch.delenv("TESS_ROOT", raising=False)
    yield


def statuses(engine, root):
    files = engine.load_lock(root)["files"]
    return {k: files[k].get("status", "core-managed") for k in CLAUDE_KEYS}


def test_publish_flips_every_entry_of_the_live_path(project, engine):
    root = build(project)
    engine.cmd_publish(ns(path="CLAUDE.md", tag=None, force=False), root)
    st = statuses(engine, root)
    assert set(st.values()) == {"user-published"}, st


def test_publish_by_tag_entry_point_covers_the_fragments(project, engine):
    root = build(project)
    engine.cmd_publish(ns(path=None, tag="entry-point", force=False), root)
    st = statuses(engine, root)
    assert set(st.values()) == {"user-published"}, st


def test_published_claude_md_edit_survives_restore(project, engine):
    root = build(project)
    engine.cmd_publish(ns(path="CLAUDE.md", tag=None, force=False), root)
    edited = project.read_live("CLAUDE.md") + "\nMY-PUBLISHED-EDIT\n"
    project.write_live("CLAUDE.md", edited)

    engine.cmd_restore(ns(dry_run=False), root)

    assert project.read_live("CLAUDE.md") == edited, "restore overwrote a published CLAUDE.md"


def test_doctor_fails_on_mixed_status_lock(project, engine, capsys):
    root = build(project)
    lock = engine.load_lock(root)
    lock["files"][TPL_KEY]["status"] = "user-published"      # the v0.1.x publish result
    engine.save_lock(root, lock)
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc:
        engine.cmd_doctor(ns(fix=False, json_out=False, path=None), root)
    assert exc.value.code not in (0, None)
    assert "MIXED" in capsys.readouterr().out

    with pytest.raises(SystemExit) as exc:
        engine.cmd_doctor(ns(fix=False, json_out=True, path=None), root)
    assert exc.value.code == 1
    rows = json.loads(capsys.readouterr().out)
    assert any(r.get("live_path") == "CLAUDE.md" and r.get("lock_status") == "mixed" for r in rows)


def test_capture_with_a_security_fragment_quarantines_every_entry(project, engine):
    root = build(project, security_fragment=SECURITY_FRAGMENT)
    pristine = project.read_live("CLAUDE.md")
    project.write_live("CLAUDE.md", pristine + "\nWEAKEN THE RULES\n")

    engine.cmd_capture(ns(path="CLAUDE.md", all=False, dry_run=False,
                          rationale="test", source="manual"), root)

    st = statuses(engine, root)
    assert set(st.values()) == {"quarantined"}, st
    assert project.read_live("CLAUDE.md") == pristine, "quarantine must pin the authoritative render"


def test_override_marks_every_entry(project, engine):
    root = build(project)
    project.write_live("CLAUDE.md", project.read_live("CLAUDE.md") + "\nPATCH LINE\n")
    engine.cmd_override(ns(path="CLAUDE.md"), root)
    st = statuses(engine, root)
    assert set(st.values()) == {"patch-override"}, st


def test_reset_repins_every_entry(project, engine):
    root = build(project)
    project.write_live("CLAUDE.md", project.read_live("CLAUDE.md") + "\nCAPTURED\n")
    engine.cmd_capture(ns(path="CLAUDE.md", all=False, dry_run=False,
                          rationale="", source="manual"), root)
    assert set(statuses(engine, root).values()) == {"locally-modified"}

    engine.cmd_reset(ns(path="CLAUDE.md"), root)

    assert set(statuses(engine, root).values()) == {"core-managed"}
    assert project.read_live("CLAUDE.md") == engine.render_claude_md(root)


def test_held_fragment_entry_protects_claude_md_from_render(project, engine):
    root = build(project, fragment_status={SECURITY_FRAGMENT: "held"})
    edited = project.read_live("CLAUDE.md") + "\nHELD EDIT\n"
    project.write_live("CLAUDE.md", edited)

    render(engine, root)

    assert project.read_live("CLAUDE.md") == edited, "render ignored a held entry of CLAUDE.md"


def test_update_gate_blocks_on_mixed_status(project, engine, capsys):
    root = build(project)
    lock = engine.load_lock(root)
    lock["files"][TPL_KEY]["status"] = "locally-modified"
    engine.save_lock(root, lock)
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc:
        engine.cmd_update(ns(dry_run=True, check=False, to=None), root)
    assert exc.value.code not in (0, None)
    assert "disagree on status" in capsys.readouterr().out


def test_status_helpers(engine):
    lock = {"files": {
        "a": {"live_path": "X.md", "status": "core-managed"},
        "b": {"live_path": "X.md", "status": "locally-modified"},
        "c": {"live_path": "X.md", "status": "user-published"},
        "d": {"live_path": "Y.md", "status": "core-managed"},
        "e": {"live_path": None, "status": "held"},
    }}
    assert [k for k, _a in engine._entries_for_live_path(lock, "X.md")] == ["a", "b", "c"]
    assert engine.effective_live_status(lock, "X.md") == "user-published"
    assert engine.effective_live_status(lock, "Y.md") == "core-managed"
    assert engine.effective_live_status(lock, "absent.md") == "core-managed"
    assert engine.render_output_status(lock, "X.md") == "user-published"
    assert engine.render_output_status(lock, "Y.md") == "rendered"
    lock["render_outputs"] = {"Y.md": {"target": "t", "status": "held", "rendered_sha": "sha256:0"}}
    assert engine.render_output_status(lock, "Y.md") == "held"
    # quarantine outranks a captured edit: a quarantined security edit stays pinned
    q = {"files": {"a": {"live_path": "Z", "status": "locally-modified"},
                   "b": {"live_path": "Z", "status": "quarantined"}}}
    assert engine.effective_live_status(q, "Z") == "quarantined"
    findings = engine._lock_status_consistency_findings(lock)
    assert [f["live_path"] for f in findings] == ["X.md"]


def test_capture_counts_one_live_file_once(project, engine, capsys):
    root = build(project)
    project.write_live("CLAUDE.md", project.read_live("CLAUDE.md") + "\nONE FILE\n")
    capsys.readouterr()
    engine.cmd_capture(ns(path="CLAUDE.md", all=False, dry_run=False,
                          rationale="", source="manual"), root)
    assert "capture: captured 1 file(s)" in capsys.readouterr().out
