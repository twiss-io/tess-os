"""
v0.2 snapshot + rollback safety (engine bugs a, b, b2, 12).

  * b   rollback never treats `.tess/snapshots/.gitkeep` as a snapshot; with no
        full snapshot, or a snapshot that restores nothing, it exits non-zero
        and never prints "rollback: complete".
  * b2  pruning lists snapshot DIRECTORIES only, so a `.gitkeep` older than
        five real snapshots is never handed to shutil.rmtree.
  * a   `render` (and every other lifecycle command) takes one consolidated
        snapshot that includes render-target outputs such as AGENTS.md and a
        hand-maintained `.codex/config.toml`, and rollback restores them.
  * 12  one snapshot per operation, whatever the wall clock does, so a long
        restore cannot fragment or prune its own pre-images.
"""

from __future__ import annotations

import datetime as _dt
import json
import os

import pytest

from conftest import ns


def _snaps(project):
    return project.root / ".tess" / "snapshots"


def _full_dirs(project):
    return sorted(
        p.name for p in _snaps(project).iterdir()
        if p.is_dir() and not p.name.endswith("-pre")
    )


def _set_enabled(project, names):
    mf_path = project.root / "tess.manifest.json"
    manifest = json.loads(mf_path.read_text(encoding="utf-8"))
    manifest.setdefault("render_targets", {})["enabled"] = list(names)
    mf_path.write_text(json.dumps(manifest), encoding="utf-8")


_AGENTS_TPL = "# AGENTS.md Fixture\n\n{{WORKER_HARD_FLOOR}}\n\n{{WORKER_GATE_COMPLIANCE}}\n\n{{HARNESS_NOTE}}\n"
_AGENTS_FRAGMENTS = {
    ".tess/core/templates/agents-md/worker-hard-floor.md": "HARD FLOOR FIXTURE\n",
    ".tess/core/templates/agents-md/gate-compliance.md": "GATE COMPLIANCE FIXTURE\n",
    ".tess/core/templates/agents-md/harness-note.md": "HARNESS NOTE FIXTURE\n",
}


def _seed_codex(project):
    """AGENTS.md + codex config inputs and one command (same shape as
    tests/test_render_targets_codex_generic.py's _seed_agents)."""
    project.add(None, _AGENTS_TPL, core_key=".tess/core/templates/agents-md/AGENTS.md.tpl",
                render_live=False)
    for core_key, content in _AGENTS_FRAGMENTS.items():
        project.add(None, content, core_key=core_key, render_live=False)
    project.add(None, 'approval_policy = "on-request"\n',
                core_key=".tess/core/templates/agents-md/codex-config.toml.tpl",
                render_live=False)
    project.add(".claude/commands/wake.md", "---\ndescription: wake\n---\n\n# /wake\n",
                core_key=".tess/core/commands/wake.md")


# ---------------------------------------------------------------------------
# _list_snapshot_dirs + bug b (rollback picks .gitkeep)
# ---------------------------------------------------------------------------

def test_list_snapshot_dirs_ignores_dotfiles_files_and_symlinks(project):
    project.write()
    snaps = _snaps(project)
    (snaps / ".gitkeep").write_text("")
    (snaps / "stray-file").write_text("x")
    (snaps / "2026-01-01T00-00-00Z").mkdir()
    (snaps / ".hidden-dir").mkdir()
    (snaps / "linked").symlink_to(snaps / "2026-01-01T00-00-00Z")
    names = [p.name for p in project.mod._list_snapshot_dirs(project.root)]
    assert names == ["2026-01-01T00-00-00Z"]


def test_rollback_default_never_picks_gitkeep(project, capsys):
    """Bug b: only a '-pre' directory plus a NEWER .gitkeep -> non-zero exit,
    no 'rollback: complete' (5c2d698 printed 'restored to .gitkeep', rc 0)."""
    project.add("conductor/a.md", "core\n")
    project.write()
    snaps = _snaps(project)
    pre = snaps / "2026-01-01T00-00-00Z-pre"
    (pre / "conductor").mkdir(parents=True)
    (pre / "conductor" / "a.md").write_text("pre-image\n")
    os.utime(pre, (1000, 1000))
    keep = snaps / ".gitkeep"
    keep.write_text("")
    os.utime(keep, (9_000_000_000, 9_000_000_000))  # newest entry by mtime

    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_rollback(ns(to=None), project.root)
    assert ei.value.code not in (None, 0)
    out = capsys.readouterr().out
    assert "rollback: complete" not in out
    assert ".gitkeep" not in out


def test_rollback_default_picks_real_snapshot_over_newer_gitkeep(project):
    project.add("conductor/a.md", "original\n")
    lock = project.write()
    snap_id = project.mod.snapshot_live_tree(project.root, lock)
    keep = _snaps(project) / ".gitkeep"
    keep.write_text("")
    os.utime(keep, (9_000_000_000, 9_000_000_000))
    project.write_live("conductor/a.md", "corrupted\n")

    project.mod.cmd_rollback(ns(to=None), project.root)
    assert project.read_live("conductor/a.md") == "original\n"
    assert (_snaps(project) / snap_id).is_dir()


def test_rollback_with_no_snapshots_exits_nonzero(project, capsys):
    project.write()
    (_snaps(project) / ".gitkeep").write_text("")
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_rollback(ns(to=None), project.root)
    assert ei.value.code not in (None, 0)
    assert "rollback: complete" not in capsys.readouterr().out


def test_rollback_of_empty_snapshot_exits_nonzero(project, capsys):
    """0 files restored is a failure, not 'complete'."""
    project.write()
    empty = _snaps(project) / "2026-01-01T00-00-00Z"
    empty.mkdir()
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_rollback(ns(to="2026-01-01T00-00-00Z"), project.root)
    assert ei.value.code not in (None, 0)
    assert "rollback: complete" not in capsys.readouterr().out


def test_rollback_to_rejects_non_directory_names(project):
    project.add("conductor/a.md", "x\n")
    lock = project.write()
    project.mod.snapshot_live_tree(project.root, lock)
    (_snaps(project) / ".gitkeep").write_text("")
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_rollback(ns(to=".gitkeep"), project.root)
    assert "not found" in str(ei.value.code)


# ---------------------------------------------------------------------------
# bug b2 (prune rmtree's .gitkeep)
# ---------------------------------------------------------------------------

def test_prune_with_old_gitkeep_and_five_snapshots_does_not_crash(project):
    """Bug b2: .gitkeep (mtime 1) + 5 snapshot dirs, then 3 more full
    snapshots: no exception, .gitkeep survives, at most 5 full dirs remain.
    On 5c2d698 the first prune raised NotADirectoryError."""
    project.add("conductor/a.md", "x\n")
    lock = project.write()
    snaps = _snaps(project)
    for i in range(5):
        d = snaps / f"2026-01-0{i + 1}T00-00-00Z"
        d.mkdir()
        (d / "marker").write_text(str(i))
        os.utime(d, (100 + i, 100 + i))
    keep = snaps / ".gitkeep"
    keep.write_text("")
    os.utime(keep, (1, 1))

    for _ in range(3):
        project.mod.snapshot_live_tree(project.root, lock)

    assert keep.is_file()
    assert len(_full_dirs(project)) <= project.mod.MAX_SNAPSHOTS


def test_prune_never_removes_an_active_snapshot(project):
    project.add("conductor/a.md", "x\n")
    lock = project.write()
    active = project.mod.snapshot_live_tree(project.root, lock)
    assert active in project.mod._ACTIVE_SNAPSHOTS
    os.utime(_snaps(project) / active, (1, 1))  # make it the OLDEST
    for i in range(project.mod.MAX_SNAPSHOTS + 2):
        d = _snaps(project) / f"2026-02-0{i + 1}T00-00-00Z"
        d.mkdir()
        os.utime(d, (1000 + i, 1000 + i))
    project.mod._prune_snapshots(project.root)
    assert (_snaps(project) / active).is_dir()
    assert len(_full_dirs(project)) == project.mod.MAX_SNAPSHOTS
    project.mod._finish_snapshot(project.root, active, verbose=False)
    assert active not in project.mod._ACTIVE_SNAPSHOTS


# ---------------------------------------------------------------------------
# snapshot_paths manifest + manifest-driven rollback
# ---------------------------------------------------------------------------

def test_snapshot_paths_manifest_shape_and_symlinks(project):
    project.write()
    project.write_live("conductor/real.md", "real bytes\n")
    os.chmod(project.root / "conductor" / "real.md", 0o640)
    (project.root / "conductor" / "link.md").symlink_to("real.md")
    snap_id = project.mod.snapshot_paths(
        project.root, ["conductor/real.md", "conductor/link.md", "conductor/absent.md"], "test")
    assert snap_id.endswith("-test")
    snap = _snaps(project) / snap_id
    manifest = json.loads((snap / "manifest.json").read_text())
    assert manifest["conductor/real.md"] == {
        "existed": True, "sha256": project.mod.sha256_bytes(b"real bytes\n"),
        "mode": 0o640, "is_symlink": False, "link_target": None,
    }
    assert manifest["conductor/link.md"]["is_symlink"] is True
    assert manifest["conductor/link.md"]["link_target"] == "real.md"
    assert manifest["conductor/absent.md"]["existed"] is False
    # copied with follow_symlinks=False: the pre-image of the link IS a link
    assert os.path.islink(snap / "conductor" / "link.md")
    assert (snap / "conductor" / "real.md").read_bytes() == b"real bytes\n"


def test_manifest_rollback_deletes_created_files_and_recreates_symlinks(project, capsys):
    project.write()
    project.write_live("conductor/real.md", "real\n")
    (project.root / "conductor" / "link.md").symlink_to("real.md")
    rels = ["conductor/real.md", "conductor/link.md", "conductor/new.md"]
    snap_id = project.mod.snapshot_paths(project.root, rels, "test")

    project.write_live("conductor/real.md", "clobbered\n")
    os.unlink(project.root / "conductor" / "link.md")
    project.write_live("conductor/link.md", "link replaced by a file\n")
    project.write_live("conductor/new.md", "created after the snapshot\n")

    project.mod.cmd_rollback(ns(to=snap_id), project.root)
    out = capsys.readouterr().out
    assert project.read_live("conductor/real.md") == "real\n"
    assert os.path.islink(project.root / "conductor" / "link.md")
    assert os.readlink(project.root / "conductor" / "link.md") == "real.md"
    assert not (project.root / "conductor" / "new.md").exists()
    assert "rollback: complete" in out


def test_manifest_rollback_refuses_tampered_payload(project, capsys):
    project.write()
    project.write_live("conductor/real.md", "real\n")
    snap_id = project.mod.snapshot_paths(project.root, ["conductor/real.md"], "test")
    (_snaps(project) / snap_id / "conductor" / "real.md").write_text("TAMPERED\n")
    project.write_live("conductor/real.md", "later\n")
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_rollback(ns(to=snap_id), project.root)
    assert ei.value.code not in (None, 0)
    assert project.read_live("conductor/real.md") == "later\n"
    assert "rollback: complete" not in capsys.readouterr().out


def test_finish_snapshot_discards_a_noop_snapshot(project):
    project.add("conductor/a.md", "x\n")
    lock = project.write()
    snap_id = project.mod.snapshot_live_tree(project.root, lock, label="render")
    assert project.mod._finish_snapshot(project.root, snap_id, verbose=False) is False
    assert not (_snaps(project) / snap_id).exists()

    snap_id = project.mod.snapshot_live_tree(project.root, lock, label="render")
    project.write_live("conductor/a.md", "changed\n")
    assert project.mod._finish_snapshot(project.root, snap_id, verbose=False) is True
    assert (_snaps(project) / snap_id).is_dir()


# ---------------------------------------------------------------------------
# bug a: render outputs get a pre-image
# ---------------------------------------------------------------------------

def _record_rendered(project, outputs, target="codex"):
    """Mark `outputs` as what Tess last rendered (tess.lock render_outputs),
    i.e. stale renders that `tessctl render` rewrites."""
    lock = project.mod.load_lock(project.root)
    lock["render_outputs"] = {
        rel: {"target": target, "status": "rendered",
              "rendered_sha": project.mod.sha256_bytes(data)}
        for rel, data in outputs.items()
    }
    project.mod.save_lock(project.root, lock)


def test_render_snapshot_restores_agents_md_and_codex_config(project):
    """Bug a acceptance: codex enabled, AGENTS.md and a .codex/config.toml
    holding an [mcp_servers.x] block that `render` overwrites (here: stale
    renders); `render` then `rollback --to <id>` restores both byte-for-byte.
    5c2d698's render took no snapshot at all, so both were lost."""
    _seed_codex(project)
    project.write()
    _set_enabled(project, ["codex"])
    agents = b"# my AGENTS.md\nhand-maintained\n"
    config = b'approval_policy = "never"\n\n[mcp_servers.x]\ncommand = "x-server"\n'
    project.write_live("AGENTS.md", agents)
    project.write_live(".codex/config.toml", config)
    _record_rendered(project, {"AGENTS.md": agents, ".codex/config.toml": config})
    before = set(_full_dirs(project))

    project.mod.cmd_render(ns(target=None, list_targets=False), project.root)
    assert (project.root / "AGENTS.md").read_bytes() != agents
    assert b"[mcp_servers.x]" not in (project.root / ".codex" / "config.toml").read_bytes()

    new = sorted(set(_full_dirs(project)) - before)
    assert len(new) == 1, new
    snap = _snaps(project) / new[0]
    assert (snap / "AGENTS.md").read_bytes() == agents
    assert (snap / ".codex" / "config.toml").read_bytes() == config

    project.mod.cmd_rollback(ns(to=new[0]), project.root)
    assert (project.root / "AGENTS.md").read_bytes() == agents
    assert (project.root / ".codex" / "config.toml").read_bytes() == config


def test_render_rollback_removes_outputs_that_did_not_exist(project):
    _seed_codex(project)
    project.write()
    _set_enabled(project, ["codex"])
    assert not (project.root / "AGENTS.md").exists()
    before = set(_full_dirs(project))
    project.mod.cmd_render(ns(target=None, list_targets=False), project.root)
    assert (project.root / "AGENTS.md").is_file()
    new = sorted(set(_full_dirs(project)) - before)
    assert len(new) == 1, new
    project.mod.cmd_rollback(ns(to=new[0]), project.root)
    assert not (project.root / "AGENTS.md").exists()
    assert not (project.root / ".codex" / "config.toml").exists()


def test_noop_render_leaves_no_snapshot(project):
    _seed_codex(project)
    project.write()
    _set_enabled(project, ["codex"])
    project.mod.cmd_render(ns(target=None, list_targets=False), project.root)
    first = set(_full_dirs(project))
    project.mod.cmd_render(ns(target=None, list_targets=False), project.root)
    assert set(_full_dirs(project)) == first
