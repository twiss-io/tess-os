"""
restore + rollback.

  * restore re-syncs a modified live file from core
  * restore refuses to silently discard a locally-modified file (warn + skip)
  * restore is skip-not-abort: a symlinked/never_touch live path is skipped with
    a WARN while the rest of the run completes (BLOCKER-1)
  * rollback restores the live tree (and tess.lock) from a snapshot
"""

from __future__ import annotations

import pytest

from conftest import ns


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------

def test_restore_resyncs_modified_live(project):
    project.add("conductor/r.md", "core content\n", status="core-managed")
    project.write()
    project.write_live("conductor/r.md", "drifted away\n")
    counts = project.mod._do_restore(project.root, verbose=False)
    assert project.read_live("conductor/r.md") == "core content\n"
    assert counts["updated"] >= 1


def test_restore_skips_locally_modified_without_discarding(project, capsys):
    project.add("conductor/lm.md", "core\n", status="locally-modified")
    project.write()
    project.write_live("conductor/lm.md", "precious local edit\n")
    counts = project.mod._do_restore(project.root, verbose=False)
    # The captured edit must NOT be silently discarded.
    assert project.read_live("conductor/lm.md") == "precious local edit\n"
    assert counts["skipped_locally_modified"] == 1


def test_restore_skip_not_abort_on_symlinked_path(project):
    """A live path that traverses a symlink dir is skipped — the run continues."""
    (project.root / "kb").mkdir()  # a never_touch zone
    # A normal file that genuinely needs restoring.
    project.add("conductor/normal.md", "norm core\n", status="core-managed")
    project.write_live("conductor/normal.md", "drifted\n")
    # A poisoned entry whose live path traverses a symlink into kb/.
    project.add("conductor/linked/g.md", "g core\n",
                core_key=".tess/core/conductor/linked-g.md",
                status="core-managed", render_live=False)
    project.write()
    # conductor/ already exists (created above); plant the symlink component.
    (project.root / "conductor" / "linked").symlink_to(project.root / "kb")

    counts = project.mod._do_restore(project.root, verbose=False)
    # Skipped, not aborted: the normal file still got restored.
    assert counts["skipped_gate"] == 1
    assert project.read_live("conductor/normal.md") == "norm core\n"


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------

def test_rollback_restores_from_latest_snapshot(project, capsys):
    project.add("conductor/snap.md", "original\n", status="core-managed")
    lock = project.write()
    # Take a full snapshot of the pristine tree.
    project.mod.snapshot_live_tree(project.root, lock)
    # Corrupt the live file after snapshotting.
    project.write_live("conductor/snap.md", "corrupted later\n")

    project.mod.cmd_rollback(ns(to=None), project.root)
    assert project.read_live("conductor/snap.md") == "original\n"


def test_rollback_to_named_snapshot(project):
    project.add("conductor/snap.md", "v-snap\n", status="core-managed")
    lock = project.write()
    ts = project.mod.snapshot_live_tree(project.root, lock)
    project.write_live("conductor/snap.md", "later edit\n")

    project.mod.cmd_rollback(ns(to=ts), project.root)
    assert project.read_live("conductor/snap.md") == "v-snap\n"


def test_rollback_restores_lock_snapshot(project):
    project.add("conductor/snap.md", "x\n", status="core-managed")
    lock = project.write()
    ts = project.mod.snapshot_live_tree(project.root, lock)
    # Mutate the on-disk lock after snapshot.
    mutated = project.mod.load_lock(project.root)
    mutated["framework"]["version"] = "9.9.9"
    project.mod.save_lock(project.root, mutated)

    project.mod.cmd_rollback(ns(to=ts), project.root)
    restored = project.mod.load_lock(project.root)
    assert restored["framework"]["version"] == "2.0.0"


def test_rollback_on_fresh_scaffold_fails_cleanly_not_false_success(project):
    """Regression: .tess/snapshots/.gitkeep is a scaffold placeholder FILE
    (present on every real, freshly-scaffolded Tess OS project — see
    tess-os .tess/snapshots/.gitkeep), not a snapshot. Before the fix,
    Path.iterdir() picked it up as a candidate, rollback treated it as the
    "most recent full snapshot", restored 0 files, and exited 0 — a false
    success. It must now fail loudly instead."""
    (project.root / ".tess" / "snapshots" / ".gitkeep").write_bytes(b"")

    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_rollback(ns(to=None), project.root)
    msg = str(ei.value)
    assert "no snapshots exist" in msg.lower()
    # sys.exit(<non-empty str>) is a non-zero exit for the process.
    assert ei.value.code not in (0, None)


def test_rollback_ignores_gitkeep_and_uses_real_snapshot(project):
    """A stray .gitkeep sitting alongside a real snapshot must never be
    selected — the real (mtime-latest) full snapshot always wins."""
    (project.root / ".tess" / "snapshots" / ".gitkeep").write_bytes(b"")
    project.add("conductor/snap.md", "original\n", status="core-managed")
    lock = project.write()
    project.mod.snapshot_live_tree(project.root, lock)
    project.write_live("conductor/snap.md", "corrupted later\n")

    project.mod.cmd_rollback(ns(to=None), project.root)
    assert project.read_live("conductor/snap.md") == "original\n"


def test_rollback_warns_when_zero_files_restored(project, capsys):
    """An empty-but-real snapshot dir (has the tess.lock.snapshot marker,
    but the tracked live file no longer exists to copy) must warn loudly
    about restoring 0 files rather than silently reporting success."""
    project.add("conductor/gone.md", "will be deleted\n", status="core-managed")
    lock = project.write()
    ts = project.mod.snapshot_live_tree(project.root, lock)
    # Delete the live file so the snapshot dir itself ends up holding only
    # the tess.lock.snapshot marker (0 restorable content files).
    (project.root / ".tess" / "snapshots" / ts / "conductor" / "snap.md").unlink(missing_ok=True)
    for f in (project.root / ".tess" / "snapshots" / ts).rglob("*"):
        if f.is_file() and f.name != "tess.lock.snapshot":
            f.unlink()

    project.mod.cmd_rollback(ns(to=ts), project.root)
    out = capsys.readouterr().out
    assert "0 files restored" in out
    assert "WARN" in out
