"""
Phase 0.3 — `tessctl memory adopt`, the cross-harness MEMORY LINK (MEMORY
ADOPT region, a sibling of TASK LEDGER — tests/test_task_store.py is this
file's own rigor precedent: real CLI via subprocess, then re-read the
filesystem back).

Coverage:
  * Dry-run is the default and is 100% side-effect-free (no directory,
    symlink, or manifest is ever created by a dry-run call).
  * A real (--yes) adopt: bootstrap (source doesn't exist yet) and the
    genuine "move real files" case — moved files verified byte-identical,
    the manifest's `source_files`/`newly_copied_files`, the symlink
    actually resolving to the canonical store, and the post-adopt
    round-trip check.
  * Idempotency: re-running adopt against an already-adopted source is a
    clean no-op (dry-run AND --yes), never an error.
  * Refusals (every one asserted to leave NO mutation behind):
      - an existing symlink pointing somewhere else entirely,
      - a source that exists but is not a directory,
      - a source directory containing a non-file entry,
      - a non-empty target without --merge (source non-empty),
      - a real filename+content conflict during --merge.
  * A non-empty target WITHOUT --merge is fine for a bootstrap call (no
    source content at all) — only refused when there is real content that
    would need merging.
  * `--merge` with identical-content files across source/target: skipped
    cleanly, not treated as a conflict.
  * `--revert`: restores exactly the manifest's own `source_files` (not the
    store's current full contents — a second harness's own separately
    adopted file, or ordinary post-adopt content, is left untouched);
    refuses with no manifest; refuses with a drifted symlink; refuses
    (asks for --harness) when more than one harness's manifest is present.
  * A round-trip-check failure triggers an automatic full rollback (no
    half-adopted state survives) — proven by monkeypatching the check to
    fail.
  * `tessctl doctor`'s memory-link check: not-adopted (non-fatal, exit 0),
    adopted+clean, adopted+broken-symlink (still non-fatal, exit 0), and
    MEMORY.md index-coherence gaps (broken links / unindexed files).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ENGINE_SRC


@pytest.fixture
def troot(tmp_path):
    """A minimal synthetic Tess OS root: `tessctl memory adopt` only needs
    tess.manifest.json (find_tess_root()) — no tess.lock, no contracts."""
    root = tmp_path / "os"
    root.mkdir()
    (root / "tess.manifest.json").write_text(
        json.dumps({"schema": 1, "owned_globs": [], "never_touch": [".tess/state/**"]}),
        encoding="utf-8",
    )
    bin_dir = root / ".tess" / "bin"
    bin_dir.mkdir(parents=True)
    dst_engine = bin_dir / "tessctl"
    shutil.copy2(ENGINE_SRC, dst_engine)
    os.chmod(dst_engine, 0o755)
    return root


@pytest.fixture
def harness_home(tmp_path):
    """A throwaway harness-private memory directory, deliberately OUTSIDE
    `troot` (mirrors the real ~/.claude/projects/<flattened>/memory/
    separation from the project tree)."""
    d = tmp_path / "harness-home" / "memory"
    d.mkdir(parents=True)
    return d


def _run(root, *args):
    env = {**os.environ, "TESS_ROOT": str(root)}
    return subprocess.run(
        [sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
        cwd=str(root), env=env, capture_output=True, text=True,
    )


def _seed(harness_home, **files):
    for name, content in files.items():
        (harness_home / name).write_text(content, encoding="utf-8")


def _to_dir(root):
    return root / ".tess" / "state" / "memory"


def _manifest(root, harness="claude-code"):
    return json.loads(
        (_to_dir(root) / f".tess-memory-adopt.{harness}.json").read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# Dry-run — the default, and side-effect-free
# ---------------------------------------------------------------------------

def test_dry_run_is_default_and_touches_nothing(troot, harness_home):
    _seed(harness_home, **{"MEMORY.md": "# Memory Index\n", "feedback_x.md": "content\n"})
    r = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(_to_dir(troot)))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "DRY RUN" in r.stdout
    assert "Re-run with --yes" in r.stdout

    # Nothing moved, no symlink, no manifest, no --to directory created.
    assert harness_home.is_dir() and not harness_home.is_symlink()
    assert sorted(p.name for p in harness_home.iterdir()) == ["MEMORY.md", "feedback_x.md"]
    assert not _to_dir(troot).exists()


def test_dry_run_json_shape(troot, harness_home):
    _seed(harness_home, **{"a.md": "1\n"})
    r = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(_to_dir(troot)), "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(r.stdout)
    assert obj["action"] == "adopt"
    assert obj["dry_run"] is True
    assert obj["files_to_copy"] == ["a.md"]


# ---------------------------------------------------------------------------
# A real adopt (--yes)
# ---------------------------------------------------------------------------

def test_real_adopt_bootstrap_no_source_dir(troot, tmp_path):
    """--from doesn't exist at all yet — nothing to move, just wires up the
    symlink so future harness writes land in the canonical store."""
    ghost_from = tmp_path / "harness-home-2" / "memory"
    assert not ghost_from.exists()
    to_dir = _to_dir(troot)
    r = _run(troot, "memory", "adopt", "--from", str(ghost_from), "--to", str(to_dir), "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert ghost_from.is_symlink()
    assert ghost_from.resolve() == to_dir.resolve()
    manifest = _manifest(troot)
    assert manifest["source_files"] == []
    assert manifest["newly_copied_files"] == []


def test_real_adopt_moves_files_and_symlinks(troot, harness_home):
    _seed(harness_home, **{
        "MEMORY.md": "# Memory Index\n- [X](feedback_x.md) note\n",
        "feedback_x.md": "some learning\n",
    })
    to_dir = _to_dir(troot)
    r = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "round-trip check: OK" in r.stdout

    assert harness_home.is_symlink()
    assert harness_home.resolve() == to_dir.resolve()

    moved = (to_dir / "feedback_x.md").read_text(encoding="utf-8")
    assert moved == "some learning\n"
    assert (to_dir / "MEMORY.md").exists()

    manifest = _manifest(troot)
    assert sorted(manifest["source_files"]) == ["MEMORY.md", "feedback_x.md"]
    assert sorted(manifest["newly_copied_files"]) == ["MEMORY.md", "feedback_x.md"]
    assert manifest["harness"] == "claude-code"
    assert manifest["to_path"] == str(to_dir.resolve())

    # Reading THROUGH the symlink reaches the same canonical bytes.
    assert (harness_home / "feedback_x.md").read_text(encoding="utf-8") == "some learning\n"


def test_real_adopt_json_shape(troot, harness_home):
    _seed(harness_home, **{"a.md": "1\n"})
    to_dir = _to_dir(troot)
    r = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    obj = json.loads(r.stdout)
    assert obj["action"] == "adopt"
    assert obj["dry_run"] is False
    assert obj["roundtrip_ok"] is True
    assert obj["newly_copied_files"] == ["a.md"]


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_idempotent_reraopt_dry_run_is_noop(troot, harness_home):
    _seed(harness_home, **{"a.md": "1\n"})
    to_dir = _to_dir(troot)
    r1 = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r1.returncode == 0, r1.stdout + r1.stderr

    r2 = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir))
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "already adopted" in r2.stdout


def test_idempotent_reraopt_yes_is_noop(troot, harness_home):
    _seed(harness_home, **{"a.md": "1\n"})
    to_dir = _to_dir(troot)
    r1 = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    before_mtime = (to_dir / "a.md").stat().st_mtime

    r2 = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "already adopted" in r2.stdout
    assert (to_dir / "a.md").stat().st_mtime == before_mtime  # untouched, no rewrite


# ---------------------------------------------------------------------------
# Refusals — every one must leave NO mutation behind
# ---------------------------------------------------------------------------

def test_refuses_existing_symlink_pointing_elsewhere(troot, harness_home, tmp_path):
    other_target = tmp_path / "some-other-dir"
    other_target.mkdir()
    harness_home.rmdir()
    harness_home.symlink_to(other_target)

    to_dir = _to_dir(troot)
    r = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r.returncode != 0
    assert "already a symlink" in (r.stdout + r.stderr)
    assert harness_home.resolve() == other_target.resolve()  # untouched
    assert not to_dir.exists()


def test_refuses_source_that_is_a_file_not_a_directory(troot, tmp_path):
    bogus = tmp_path / "not-a-dir"
    bogus.write_text("oops\n", encoding="utf-8")
    to_dir = _to_dir(troot)
    r = _run(troot, "memory", "adopt", "--from", str(bogus), "--to", str(to_dir), "--yes")
    assert r.returncode != 0
    assert "not a directory" in (r.stdout + r.stderr)
    assert bogus.read_text(encoding="utf-8") == "oops\n"


def test_refuses_nonfile_entry_in_source(troot, harness_home):
    (harness_home / "subdir").mkdir()
    to_dir = _to_dir(troot)
    r = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r.returncode != 0
    assert "non-file entries" in (r.stdout + r.stderr)
    assert not to_dir.exists()


def test_refuses_nonempty_target_without_merge(troot, harness_home):
    _seed(harness_home, **{"a.md": "1\n"})
    to_dir = _to_dir(troot)
    to_dir.mkdir(parents=True)
    (to_dir / "preexisting.md").write_text("already here\n", encoding="utf-8")

    r = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r.returncode != 0
    assert "--merge" in (r.stdout + r.stderr)
    # No mutation: source untouched, target unchanged, no manifest/symlink.
    assert harness_home.is_dir() and not harness_home.is_symlink()
    assert (to_dir / "preexisting.md").read_text(encoding="utf-8") == "already here\n"
    assert not (to_dir / "a.md").exists()


def test_bootstrap_allowed_even_when_target_nonempty(troot, tmp_path):
    """No --merge needed when there's no source content at all — nothing is
    being merged, only a symlink is wired up for future writes."""
    to_dir = _to_dir(troot)
    to_dir.mkdir(parents=True)
    (to_dir / "preexisting.md").write_text("already here\n", encoding="utf-8")
    ghost_from = tmp_path / "harness-home-3" / "memory"

    r = _run(troot, "memory", "adopt", "--from", str(ghost_from), "--to", str(to_dir), "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert ghost_from.is_symlink()


def test_merge_skips_identical_content_no_conflict(troot, harness_home):
    to_dir = _to_dir(troot)
    to_dir.mkdir(parents=True)
    (to_dir / "same.md").write_text("identical\n", encoding="utf-8")
    _seed(harness_home, **{"same.md": "identical\n", "new.md": "new one\n"})

    r = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes", "--merge")
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = _manifest(troot)
    assert sorted(manifest["source_files"]) == ["new.md", "same.md"]
    assert manifest["newly_copied_files"] == ["new.md"]  # same.md was already there, skipped


def test_merge_refuses_real_content_conflict(troot, harness_home):
    to_dir = _to_dir(troot)
    to_dir.mkdir(parents=True)
    (to_dir / "clash.md").write_text("store version\n", encoding="utf-8")
    _seed(harness_home, **{"clash.md": "harness version\n", "clean.md": "no conflict\n"})

    r = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes", "--merge")
    assert r.returncode != 0
    assert "DIFFERENT content" in (r.stdout + r.stderr)
    assert "clash.md" in (r.stdout + r.stderr)
    # No partial merge: clean.md must NOT have been copied either (all-or-nothing).
    assert not (to_dir / "clean.md").exists()
    assert (to_dir / "clash.md").read_text(encoding="utf-8") == "store version\n"
    assert harness_home.is_dir() and not harness_home.is_symlink()


# ---------------------------------------------------------------------------
# `--revert`
# ---------------------------------------------------------------------------

def test_revert_restores_real_directory_and_removes_manifest(troot, harness_home):
    _seed(harness_home, **{"MEMORY.md": "# idx\n", "a.md": "1\n"})
    to_dir = _to_dir(troot)
    r1 = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    assert harness_home.is_symlink()

    r2 = _run(troot, "memory", "adopt", "--revert", "--from", str(harness_home), "--to", str(to_dir))
    assert r2.returncode == 0, r2.stdout + r2.stderr

    assert harness_home.is_dir() and not harness_home.is_symlink()
    assert sorted(p.name for p in harness_home.iterdir()) == ["MEMORY.md", "a.md"]
    assert (harness_home / "a.md").read_text(encoding="utf-8") == "1\n"
    # The manifest is gone and the file moved OUT of the canonical store.
    assert not list(to_dir.glob(".tess-memory-adopt.*.json"))
    assert not (to_dir / "a.md").exists()


def test_revert_leaves_unrelated_store_content_untouched(troot, harness_home):
    """A second harness's own separately-merged file (never part of THIS
    harness's manifest) must survive a revert of the first harness."""
    _seed(harness_home, **{"a.md": "1\n"})
    to_dir = _to_dir(troot)
    r1 = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r1.returncode == 0, r1.stdout + r1.stderr

    (to_dir / "unrelated.md").write_text("belongs to someone else\n", encoding="utf-8")

    r2 = _run(troot, "memory", "adopt", "--revert", "--from", str(harness_home), "--to", str(to_dir))
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert (to_dir / "unrelated.md").exists()  # untouched
    assert not (harness_home / "unrelated.md").exists()  # never exported into the harness dir


def test_revert_refuses_with_no_manifest(troot, tmp_path):
    to_dir = _to_dir(troot)
    to_dir.mkdir(parents=True)
    r = _run(troot, "memory", "adopt", "--revert", "--to", str(to_dir))
    assert r.returncode != 0
    assert "nothing to revert" in (r.stdout + r.stderr)


def test_revert_refuses_drifted_symlink(troot, harness_home, tmp_path):
    _seed(harness_home, **{"a.md": "1\n"})
    to_dir = _to_dir(troot)
    r1 = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r1.returncode == 0, r1.stdout + r1.stderr

    # Simulate manual drift: someone replaced the symlink with a real dir.
    harness_home.unlink()
    harness_home.mkdir()

    r2 = _run(troot, "memory", "adopt", "--revert", "--from", str(harness_home), "--to", str(to_dir))
    assert r2.returncode != 0
    assert "not currently a symlink" in (r2.stdout + r2.stderr)
    # Manifest untouched — refusal, not a silent skip.
    assert list(to_dir.glob(".tess-memory-adopt.*.json"))


def test_revert_multiple_harnesses_requires_disambiguation(troot, harness_home, tmp_path):
    _seed(harness_home, **{"a.md": "1\n"})
    to_dir = _to_dir(troot)
    r1 = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r1.returncode == 0, r1.stdout + r1.stderr

    other_home = tmp_path / "harness-home-other" / "memory"
    other_home.mkdir(parents=True)
    (other_home / "b.md").write_text("2\n", encoding="utf-8")
    r2 = _run(
        troot, "memory", "adopt", "--harness", "codex",
        "--from", str(other_home), "--to", str(to_dir), "--yes", "--merge",
    )
    assert r2.returncode == 0, r2.stdout + r2.stderr

    r3 = _run(troot, "memory", "adopt", "--revert", "--to", str(to_dir))
    assert r3.returncode != 0
    assert "--harness" in (r3.stdout + r3.stderr)

    r4 = _run(troot, "memory", "adopt", "--revert", "--harness", "codex", "--to", str(to_dir))
    assert r4.returncode == 0, r4.stdout + r4.stderr
    assert other_home.is_dir() and not other_home.is_symlink()
    # The FIRST harness's own adoption is untouched by reverting the second.
    assert harness_home.is_symlink()


# ---------------------------------------------------------------------------
# Round-trip failure -> automatic full rollback (direct import, not subprocess
# — needs to monkeypatch the round-trip check itself).
# ---------------------------------------------------------------------------

def test_roundtrip_failure_triggers_automatic_rollback(engine, tmp_path, monkeypatch):
    root = tmp_path / "os"
    root.mkdir()
    from_dir = tmp_path / "harness-home" / "memory"
    from_dir.mkdir(parents=True)
    (from_dir / "a.md").write_text("1\n", encoding="utf-8")
    to_dir = root / ".tess" / "state" / "memory"

    def _boom(_from_dir, _to_dir):
        raise engine.MemoryAdoptError("synthetic round-trip failure for this test")

    monkeypatch.setattr(engine, "_memory_adopt_roundtrip_check", _boom)

    with pytest.raises(engine.MemoryAdoptError, match="automatically rolled back"):
        engine._memory_adopt(
            root, from_dir=from_dir, to_dir=to_dir, harness="claude-code",
            merge=False, dry_run=False,
        )

    # Fully undone: from_dir is a real directory again with its file back,
    # no manifest, no leftover copy in the canonical store.
    assert from_dir.is_dir() and not from_dir.is_symlink()
    assert (from_dir / "a.md").read_text(encoding="utf-8") == "1\n"
    assert not list(to_dir.glob(".tess-memory-adopt.*.json")) if to_dir.exists() else True
    assert not (to_dir / "a.md").exists() if to_dir.exists() else True


# ---------------------------------------------------------------------------
# Default `--harness claude-code` path resolution
# ---------------------------------------------------------------------------

def test_default_claude_code_path_uses_root_not_cwd(engine, tmp_path, monkeypatch):
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    root = tmp_path / "some" / "project"
    root.mkdir(parents=True)

    expected_flattened = str(root.resolve()).replace(os.sep, "-")
    resolved = engine._default_harness_memory_dir("claude-code", root)
    assert resolved == fake_home / ".claude" / "projects" / expected_flattened / "memory"


def test_unknown_harness_has_no_invented_default(engine, tmp_path):
    with pytest.raises(engine.MemoryAdoptError, match="no well-known default"):
        engine._default_harness_memory_dir("some-future-harness", tmp_path)


# ---------------------------------------------------------------------------
# `tessctl doctor`'s memory-link check — non-fatal in every case
# ---------------------------------------------------------------------------

def test_doctor_reports_not_adopted_and_stays_green(troot):
    _seed_lock(troot)
    r = _run(troot, "doctor")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "not adopted (optional)" in r.stdout


def test_doctor_reports_adopted_clean(troot, harness_home):
    _seed_lock(troot)
    _seed(harness_home, **{"MEMORY.md": "# idx\n- [X](a.md) note\n", "a.md": "1\n"})
    to_dir = _to_dir(troot)
    r1 = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r1.returncode == 0, r1.stdout + r1.stderr

    r2 = _run(troot, "doctor")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "memory-link  ok — claude-code adopted" in r2.stdout
    assert "index coherent" in r2.stdout


def test_doctor_reports_broken_symlink_but_stays_green(troot, harness_home):
    _seed_lock(troot)
    _seed(harness_home, **{"a.md": "1\n"})
    to_dir = _to_dir(troot)
    r1 = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r1.returncode == 0, r1.stdout + r1.stderr

    # Simulate breakage: someone deleted the symlink and dropped a real dir.
    harness_home.unlink()
    harness_home.mkdir()

    r2 = _run(troot, "doctor")
    assert r2.returncode == 0, r2.stdout + r2.stderr  # non-fatal, even broken
    assert "ISSUE (non-fatal)" in r2.stdout
    assert "missing or not a symlink" in r2.stdout


def test_doctor_reports_index_coherence_gaps(troot, harness_home):
    _seed_lock(troot)
    _seed(harness_home, **{
        "MEMORY.md": "# idx\n- [X](a.md) note\n- [Y](ghost.md) missing\n",
        "a.md": "1\n",
        "orphan.md": "not indexed\n",
    })
    to_dir = _to_dir(troot)
    r1 = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r1.returncode == 0, r1.stdout + r1.stderr

    r2 = _run(troot, "doctor")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "ghost.md" in r2.stdout
    assert "orphan.md" in r2.stdout


def _seed_lock(root):
    """`tessctl doctor` refuses to run at all without a tess.lock — a
    minimal, empty-files one is enough (this suite never touches
    core-managed content, only the memory-link check bolted onto doctor's
    own summary)."""
    (root / ".tess" / "tess.lock").write_text(
        "schema: 1\n"
        "framework:\n"
        "  track: v2\n"
        "  version: 0.0.0\n"
        "  channel: stable\n"
        "  upstream: https://github.com/twiss-io/tess-os.git\n"
        "  upstream_ref: v0.0.0\n"
        "  upstream_commit: null\n"
        "  upstream_digest: null\n"
        "  trusted_key_fingerprint: null\n"
        "  last_updated: '2026-01-01T00:00:00Z'\n"
        "files: {}\n",
        encoding="utf-8",
    )
