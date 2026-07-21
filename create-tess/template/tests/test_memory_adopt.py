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

PR #117 two-reviewer REJECT remediation (Cyra + Reid — see this file's
"PR #117 review fixes" section below for the full list):
  * H1/CRITICAL: --from == --to (or one nested inside the other) is
    refused BEFORE any mutation — the self-destruct (rmtree + self-
    referential symlink loop + uncaught crash) is closed.
  * HIGH: the rmtree -> symlink -> manifest-write critical region is
    crash-safe — any OSError becomes a typed MemoryAdoptError, and a
    monkeypatched mid-operation failure never leaves the source deleted
    with no symlink/manifest (proven fully-intact, not half-adopted).
  * MEDIUM (M1): --revert only removes files THIS adopt itself copied
    (`newly_copied_files`) from the store; a byte-identical file another
    still-adopted harness depends on is copied back but left in the
    store.
  * MEDIUM: the manifest filename folds in a hash of the source path, not
    just the harness slug, so two --harness names that slugify identically
    (`Claude-Code` / `claude_code`) never clobber each other's manifest.
  * MEDIUM: `--revert` is dry-run by default and requires `--yes` to
    mutate, symmetric with forward-adopt.
  * LOW: a symlinked source entry is refused, not silently dereferenced.
  * LOW: `read_bytes()` during planning is guarded — a permission/IO
    failure surfaces as a typed refusal, not a raw traceback.

Cyra re-verification of 18a3fea — two holes remained after the above
round (see this file's "Cyra re-verification of 18a3fea" section below):
  * HOLE 1/HIGH: the self-destruct guard compared resolved path STRINGS,
    which `.resolve()` leaves as-typed-case — bypassable on a
    case-insensitive filesystem (macOS APFS / Windows NTFS, the real
    deployment FS for `.tess/state/memory` and
    `~/.claude/projects/.../memory`), where `STORE` and `store` are the
    SAME directory but compared unequal. Fixed with INODE IDENTITY
    (`os.path.samefile`), walked across ancestors for the nesting case
    too, with a case-fold-aware string fallback only when a path doesn't
    yet exist (samefile requires both sides to exist).
  * HOLE 2/MEDIUM: the M1 fix above only protected a shared file in ONE
    direction (the harness that DEDUPED reverting). Reversed — the
    harness that ORIGINALLY OWNED the file reverting, while a second,
    still-live harness had since deduped against it — the file was
    unconditionally removed from the store. Fixed by checking, for every
    `newly_copied_files` candidate, whether any OTHER still-live
    harness's manifest also references that filename in its own
    `source_files`; if so, it is copied back but left in the store, same
    as the already-established M1 invariant.

Issue #147 (inode-vs-string audit sweep, same class as #117/#140/#145):
  * HOLE 3/MEDIUM-HIGH: `_memory_adopt_other_live_source_files`'s own
    "is this OTHER manifest's harness still live" test used a raw
    `other_from.resolve() != to_dir_resolved` string comparison — the
    exact same bug SHAPE as HOLE 1 above, just in a different call site
    the #117 fix never reached. A case/normalization-divergent but
    otherwise identical store path (`.../STORE` vs `.../store`, the real
    macOS APFS / Windows NTFS deployment case) was wrongly judged
    "not live", so that harness's shared file was silently deleted by a
    second harness's `--revert`. Fixed the same way as HOLE 1: routed
    through `_paths_are_same_location` (inode identity). See
    `test_revert_other_harness_case_divergent_live_file_not_deleted`
    below — deliberately FS-INDEPENDENT (does not rely on the test
    runner's filesystem actually being case-insensitive, unlike the
    HOLE 1 tests above, which skip on a case-sensitive host).
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
    # The manifest filename is `.tess-memory-adopt.<slug>.<path-hash>.json`
    # (the path-hash disambiguates two --harness names that slugify to the
    # same string but adopt from different --from paths — see PR #117
    # review, Reid/MEDIUM) — glob by slug prefix rather than hardcoding
    # the exact name.
    matches = sorted(_to_dir(root).glob(f".tess-memory-adopt.{harness}.*.json"))
    assert len(matches) == 1, f"expected exactly one manifest for harness {harness!r}, found {matches}"
    return json.loads(matches[0].read_text(encoding="utf-8"))


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

    r2 = _run(troot, "memory", "adopt", "--revert", "--from", str(harness_home), "--to", str(to_dir), "--yes")
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

    r2 = _run(troot, "memory", "adopt", "--revert", "--from", str(harness_home), "--to", str(to_dir), "--yes")
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

    r4 = _run(troot, "memory", "adopt", "--revert", "--harness", "codex", "--to", str(to_dir), "--yes")
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


# ---------------------------------------------------------------------------
# PR #117 review fixes — Cyra (security) + Reid (quality), both REJECT.
# Every test below reproduces the exact finding first (see the PR #117
# review comments for the original live repro), then proves the fix
# closes it.
# ---------------------------------------------------------------------------

_IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


# --- H1/CRITICAL (Cyra + Reid) — --from == --to self-destruct ---------------

def test_refuses_from_equals_to_self_destruct(troot):
    """The exact reproduction from both reviews: --from and --to are the
    SAME directory, with --merge (the flag that bypasses the plain
    non-empty-target check). Before the fix this shutil.rmtree()'d the
    directory, replaced it with a self-referential symlink loop, and
    crashed with an uncaught FileExistsError — permanently destroying the
    only copy of the content with no manifest to recover from."""
    store = _to_dir(troot)
    store.mkdir(parents=True)
    (store / "a.md").write_text("the only copy of this content\n", encoding="utf-8")

    r = _run(troot, "memory", "adopt", "--from", str(store), "--to", str(store), "--yes", "--merge")
    assert r.returncode != 0
    assert "resolve to the same path" in (r.stdout + r.stderr)
    assert "Traceback" not in (r.stdout + r.stderr)  # typed refusal, never a raw crash

    # Content fully intact: still a real directory, not a symlink, not a
    # symlink loop, original bytes unchanged.
    assert store.is_dir() and not store.is_symlink()
    assert (store / "a.md").read_text(encoding="utf-8") == "the only copy of this content\n"
    # No manifest was ever written (nothing to "recover" — nothing was lost).
    assert not list(store.glob(".tess-memory-adopt.*.json"))


def test_refuses_to_nested_inside_from(troot):
    """The "one is a prefix of the other" variant Cyra/Reid both called
    out alongside the exact-equal case: --to is a subdirectory of
    --from."""
    from_dir = _to_dir(troot)
    to_dir = from_dir / "sub"
    from_dir.mkdir(parents=True)
    to_dir.mkdir(parents=True)
    (from_dir / "x.md").write_text("nested-hazard content\n", encoding="utf-8")

    r = _run(troot, "memory", "adopt", "--from", str(from_dir), "--to", str(to_dir), "--yes", "--merge")
    assert r.returncode != 0
    assert "resolve to the same path or one is nested inside the other" in (r.stdout + r.stderr)
    assert (from_dir / "x.md").read_text(encoding="utf-8") == "nested-hazard content\n"


def test_refuses_from_nested_inside_to(troot):
    """The reverse nesting: --from is a subdirectory of --to."""
    to_dir = _to_dir(troot)
    from_dir = to_dir / "sub"
    from_dir.mkdir(parents=True)
    (from_dir / "y.md").write_text("nested-hazard content 2\n", encoding="utf-8")

    r = _run(troot, "memory", "adopt", "--from", str(from_dir), "--to", str(to_dir), "--yes", "--merge")
    assert r.returncode != 0
    assert "resolve to the same path or one is nested inside the other" in (r.stdout + r.stderr)
    assert (from_dir / "y.md").read_text(encoding="utf-8") == "nested-hazard content 2\n"


# --- HIGH (Reid) — crash-safety of the rmtree->symlink->manifest region ----

def test_symlink_creation_failure_leaves_source_fully_intact(engine, tmp_path, monkeypatch):
    """Injects a failure in the FIRST half of the swap (creating the
    verified temp symlink, before from_dir is touched at all). Before the
    fix, an equivalent failure anywhere in this region (mkdir/rmtree/
    symlink) was a raw, unguarded OSError with zero exception handling."""
    root = tmp_path / "os"
    root.mkdir()
    from_dir = tmp_path / "harness-home" / "memory"
    from_dir.mkdir(parents=True)
    (from_dir / "a.md").write_text("original content\n", encoding="utf-8")
    to_dir = root / ".tess" / "state" / "memory"

    real_symlink = engine.os.symlink

    def _boom_symlink(src, dst, *a, **kw):
        if Path(dst).name.startswith(".tessctl-memory-adopt-tmp-"):
            raise OSError("synthetic symlink-creation failure for this test")
        return real_symlink(src, dst, *a, **kw)

    monkeypatch.setattr(engine.os, "symlink", _boom_symlink)

    with pytest.raises(engine.MemoryAdoptError, match="could not create a symlink"):
        engine._memory_adopt(
            root, from_dir=from_dir, to_dir=to_dir, harness="claude-code",
            merge=False, dry_run=False,
        )

    # FULLY INTACT, never half: from_dir is still the original real
    # directory, never partially deleted, never replaced.
    assert from_dir.is_dir() and not from_dir.is_symlink()
    assert (from_dir / "a.md").read_text(encoding="utf-8") == "original content\n"
    # Bonus: even though the swap failed, content + manifest are already
    # safely duplicated in the store — nothing is unrecoverable.
    assert (to_dir / "a.md").read_text(encoding="utf-8") == "original content\n"
    assert list(to_dir.glob(".tess-memory-adopt.*.json"))
    # No leftover temp symlink debris.
    assert list(from_dir.parent.glob(".tessctl-memory-adopt-tmp-*")) == []


def test_rmtree_failure_during_swap_leaves_source_fully_intact(engine, tmp_path, monkeypatch):
    """Injects a failure in the SECOND half of the swap (removing the
    original from_dir after the temp symlink was already verified good)
    — the exact failure window Reid's HIGH finding singles out: "if it
    fails after rmtree but before symlink, the original directory is
    already gone... no manifest was written yet". With this fix the
    manifest is already durable by this point, and the mocked failure
    fires before any real deletion happens, so from_dir survives
    untouched."""
    root = tmp_path / "os"
    root.mkdir()
    from_dir = tmp_path / "harness-home" / "memory"
    from_dir.mkdir(parents=True)
    (from_dir / "a.md").write_text("original content\n", encoding="utf-8")
    to_dir = root / ".tess" / "state" / "memory"

    real_rmtree = engine.shutil.rmtree

    def _boom_rmtree(path, *a, **kw):
        if str(path) == str(from_dir):
            raise OSError("synthetic rmtree failure for this test")
        return real_rmtree(path, *a, **kw)

    monkeypatch.setattr(engine.shutil, "rmtree", _boom_rmtree)

    with pytest.raises(engine.MemoryAdoptError, match="failed to replace"):
        engine._memory_adopt(
            root, from_dir=from_dir, to_dir=to_dir, harness="claude-code",
            merge=False, dry_run=False,
        )

    # FULLY INTACT, never half: the mocked rmtree raised before deleting
    # anything, so from_dir is still the original real directory.
    assert from_dir.is_dir() and not from_dir.is_symlink()
    assert (from_dir / "a.md").read_text(encoding="utf-8") == "original content\n"
    assert (to_dir / "a.md").read_text(encoding="utf-8") == "original content\n"
    assert list(to_dir.glob(".tess-memory-adopt.*.json"))


def test_copy_loop_os_error_is_typed_not_raw(engine, tmp_path, monkeypatch):
    """The copy loop (immediately upstream of the flagged critical
    region, same "mutate for real" block) must also never leak a raw
    OSError — a source file vanishing mid-copy is converted to a typed
    MemoryAdoptError, and the copy loop's own rollback still fires."""
    root = tmp_path / "os"
    root.mkdir()
    from_dir = tmp_path / "harness-home" / "memory"
    from_dir.mkdir(parents=True)
    (from_dir / "a.md").write_text("1\n", encoding="utf-8")
    (from_dir / "b.md").write_text("2\n", encoding="utf-8")
    to_dir = root / ".tess" / "state" / "memory"

    real_copy2 = engine.shutil.copy2

    def _boom_copy2(src, dst, *a, **kw):
        if Path(src).name == "b.md":
            raise OSError("synthetic copy failure for this test")
        return real_copy2(src, dst, *a, **kw)

    monkeypatch.setattr(engine.shutil, "copy2", _boom_copy2)

    with pytest.raises(engine.MemoryAdoptError, match="failed while copying b.md"):
        engine._memory_adopt(
            root, from_dir=from_dir, to_dir=to_dir, harness="claude-code",
            merge=False, dry_run=False,
        )

    # Rollback undid the one file that DID get copied before the failure —
    # no orphan partial content left in the store, source untouched.
    assert not to_dir.exists() or list(to_dir.iterdir()) == []
    assert from_dir.is_dir() and not from_dir.is_symlink()
    assert (from_dir / "a.md").read_text(encoding="utf-8") == "1\n"
    assert (from_dir / "b.md").read_text(encoding="utf-8") == "2\n"


# --- MEDIUM M1 (Cyra) — revert must not remove a shared already-present ----
# --- file a second harness still depends on ---------------------------------

def test_revert_two_harnesses_shared_file_preserved(troot, tmp_path):
    """The exact M1 reproduction: harness A adopts shared.md. Harness B
    --merge-adopts a BYTE-IDENTICAL shared.md (skipped as already-present,
    never copied by B) plus its own b_only.md. Reverting B must NOT remove
    shared.md from the store — harness A is still symlinked to it."""
    harness_a = tmp_path / "harness-a" / "memory"
    harness_b = tmp_path / "harness-b" / "memory"
    harness_a.mkdir(parents=True)
    harness_b.mkdir(parents=True)
    (harness_a / "shared.md").write_text("shared content\n", encoding="utf-8")
    (harness_b / "shared.md").write_text("shared content\n", encoding="utf-8")
    (harness_b / "b_only.md").write_text("only B\n", encoding="utf-8")

    to_dir = _to_dir(troot)
    ra = _run(troot, "memory", "adopt", "--harness", "harness-a", "--from", str(harness_a), "--to", str(to_dir), "--yes")
    assert ra.returncode == 0, ra.stdout + ra.stderr
    rb = _run(troot, "memory", "adopt", "--harness", "harness-b", "--from", str(harness_b), "--to", str(to_dir), "--yes", "--merge")
    assert rb.returncode == 0, rb.stdout + rb.stderr

    manifest_b = _manifest(troot, harness="harness-b")
    assert manifest_b["newly_copied_files"] == ["b_only.md"]  # shared.md was already-present, not copied by B

    # Dry-run first: must show shared.md as "copy back, kept in store".
    dry = _run(troot, "memory", "adopt", "--revert", "--harness", "harness-b", "--to", str(to_dir))
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert "DRY RUN" in dry.stdout
    assert "kept in the store" in dry.stdout
    assert "shared.md" in dry.stdout
    assert (to_dir / "shared.md").exists()  # dry-run touched nothing

    # Real revert of B.
    r2 = _run(troot, "memory", "adopt", "--revert", "--harness", "harness-b", "--to", str(to_dir), "--yes")
    assert r2.returncode == 0, r2.stdout + r2.stderr

    # shared.md survives IN THE STORE (harness A still reads it via its
    # own symlink) and b_only.md was removed (it was only ever B's copy).
    assert (to_dir / "shared.md").exists()
    assert not (to_dir / "b_only.md").exists()
    assert harness_a.is_symlink() and harness_a.resolve() == to_dir.resolve()
    assert (harness_a / "shared.md").read_text(encoding="utf-8") == "shared content\n"

    # Harness B got BOTH files back into its own restored private dir.
    assert harness_b.is_dir() and not harness_b.is_symlink()
    assert (harness_b / "shared.md").read_text(encoding="utf-8") == "shared content\n"
    assert (harness_b / "b_only.md").read_text(encoding="utf-8") == "only B\n"


# --- MEDIUM (Reid) — harness-slug collision must not clobber manifests -----

def test_harness_slug_collision_does_not_clobber_manifests(troot, tmp_path):
    """_slugify("Claude-Code-X") and _slugify("claude_code_x") both
    collide on the same slug — before the fix, the SECOND adopt's
    manifest write would silently overwrite the FIRST's, leaving the
    first harness's own --revert with no manifest to recover from."""
    home_1 = tmp_path / "home-1" / "memory"
    home_2 = tmp_path / "home-2" / "memory"
    home_1.mkdir(parents=True)
    home_2.mkdir(parents=True)
    (home_1 / "one.md").write_text("harness one\n", encoding="utf-8")
    (home_2 / "two.md").write_text("harness two\n", encoding="utf-8")

    to_dir = _to_dir(troot)
    r1 = _run(troot, "memory", "adopt", "--harness", "Claude-Code-X", "--from", str(home_1), "--to", str(to_dir), "--yes")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    r2 = _run(troot, "memory", "adopt", "--harness", "claude_code_x", "--from", str(home_2), "--to", str(to_dir), "--yes", "--merge")
    assert r2.returncode == 0, r2.stdout + r2.stderr

    # Both manifests exist — NOT clobbered into one.
    manifests = sorted(to_dir.glob(".tess-memory-adopt.claude-code-x.*.json"))
    assert len(manifests) == 2, manifests

    manifest_1 = json.loads(manifests[0].read_text(encoding="utf-8"))
    manifest_2 = json.loads(manifests[1].read_text(encoding="utf-8"))
    recorded_from = {manifest_1["from_path"], manifest_2["from_path"]}
    assert recorded_from == {str(home_1), str(home_2)}

    # Both source files present in the store, both harness symlinks live.
    assert (to_dir / "one.md").exists() and (to_dir / "two.md").exists()
    assert home_1.is_symlink() and home_2.is_symlink()

    # Reverting by the shared slug (either raw --harness spelling) is a
    # refused AMBIGUITY, not a guess at which manifest to use.
    r3 = _run(troot, "memory", "adopt", "--revert", "--harness", "Claude-Code-X", "--to", str(to_dir), "--yes")
    assert r3.returncode != 0
    assert "recorded adopt(s)" in (r3.stdout + r3.stderr)
    # Refusal, no mutation: both symlinks and both manifests still stand.
    assert home_1.is_symlink() and home_2.is_symlink()
    assert len(sorted(to_dir.glob(".tess-memory-adopt.claude-code-x.*.json"))) == 2


# --- MEDIUM (Reid) — --revert dry-run-by-default + --yes gate --------------

def test_revert_is_dry_run_by_default_and_requires_yes(troot, harness_home):
    _seed(harness_home, **{"a.md": "1\n"})
    to_dir = _to_dir(troot)
    r1 = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r1.returncode == 0, r1.stdout + r1.stderr

    # No --yes: dry-run only, touches nothing.
    r2 = _run(troot, "memory", "adopt", "--revert", "--from", str(harness_home), "--to", str(to_dir))
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "DRY RUN" in r2.stdout
    assert "Re-run with --yes" in r2.stdout
    assert harness_home.is_symlink()  # untouched — still adopted
    assert (to_dir / "a.md").exists()  # untouched
    assert list(to_dir.glob(".tess-memory-adopt.*.json"))  # manifest untouched

    # --yes: performs the revert for real.
    r3 = _run(troot, "memory", "adopt", "--revert", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r3.returncode == 0, r3.stdout + r3.stderr
    assert harness_home.is_dir() and not harness_home.is_symlink()
    assert (harness_home / "a.md").read_text(encoding="utf-8") == "1\n"
    assert not list(to_dir.glob(".tess-memory-adopt.*.json"))


def test_revert_dry_run_json_shape(troot, harness_home):
    _seed(harness_home, **{"a.md": "1\n"})
    to_dir = _to_dir(troot)
    r1 = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r1.returncode == 0, r1.stdout + r1.stderr

    r2 = _run(troot, "memory", "adopt", "--revert", "--from", str(harness_home), "--to", str(to_dir), "--json")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    obj = json.loads(r2.stdout)
    assert obj["action"] == "revert"
    assert obj["dry_run"] is True
    assert obj["would_move"] == ["a.md"]


# --- LOW (Cyra) — a symlinked source entry is refused, not dereferenced ----

def test_refuses_symlinked_source_file(troot, harness_home, tmp_path):
    outside = tmp_path / "outside-the-memory-dir"
    outside.mkdir()
    (outside / "secret.txt").write_text("TOP SECRET OUTSIDE FILE\n", encoding="utf-8")
    (harness_home / "secret.txt").symlink_to(outside / "secret.txt")

    to_dir = _to_dir(troot)
    r = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes")
    assert r.returncode != 0
    assert "non-file entries" in (r.stdout + r.stderr)
    assert "secret.txt" in (r.stdout + r.stderr)
    # No mutation: nothing copied into the store, source untouched — the
    # symlink entry is still exactly what it was, never dereferenced.
    assert not to_dir.exists()
    assert harness_home.is_dir() and not harness_home.is_symlink()
    assert (harness_home / "secret.txt").is_symlink()
    assert (harness_home / "secret.txt").resolve() == (outside / "secret.txt").resolve()


# --- LOW (Reid) — unguarded read_bytes() during planning -------------------

@pytest.mark.skipif(_IS_ROOT, reason="permission bits are not enforced for root")
def test_unreadable_target_file_during_planning_is_typed_not_raw(troot, harness_home):
    """Reproduces Reid's LOW finding: a target file that becomes
    unreadable (permission change) between source enumeration and the
    per-file byte comparison must surface as a typed MemoryAdoptError —
    not an uncaught PermissionError traceback."""
    _seed(harness_home, **{"clash.md": "harness version\n"})
    to_dir = _to_dir(troot)
    to_dir.mkdir(parents=True)
    (to_dir / "clash.md").write_text("store version\n", encoding="utf-8")
    os.chmod(to_dir / "clash.md", 0o000)
    try:
        r = _run(troot, "memory", "adopt", "--from", str(harness_home), "--to", str(to_dir), "--yes", "--merge")
    finally:
        os.chmod(to_dir / "clash.md", 0o644)  # restore so tmp_path cleanup can remove it

    assert r.returncode != 0
    assert "could not read" in (r.stdout + r.stderr)
    assert "clash.md" in (r.stdout + r.stderr)
    # Reid-LOW (#117 review, closed here): the attempt-3 delta silently
    # dropped this trailing assertion from this already-closed test; restore
    # it — the invariant it proves (a typed refusal, never a raw traceback)
    # is exactly what this test is FOR.
    assert "Traceback" not in (r.stdout + r.stderr)  # typed refusal, never a raw crash


# ---------------------------------------------------------------------------
# Cyra re-verification of 18a3fea (PR #117) — two holes remained after the
# first remediation round above. Each test below reproduces the exact
# finding from Cyra's re-verify comment first, then proves the fix closes
# it — same rigor precedent as the section above.
# ---------------------------------------------------------------------------

def _fs_is_case_insensitive(tmp_path) -> bool:
    """True if the filesystem backing `tmp_path` treats differently-cased
    names as the SAME file on disk — true of macOS APFS (default) and
    Windows NTFS (default), the actual deployment filesystem for both
    `.tess/state/memory` and `~/.claude/projects/<flattened>/memory`.
    Detected empirically (never assumed from `sys.platform`) since a
    case-SENSITIVE APFS volume is also a valid, if non-default, macOS
    format, and this repo's own CI runners are Linux (case-sensitive)."""
    probe = tmp_path / "case-fs-probe"
    probe.mkdir()
    (probe / "lower").write_text("x", encoding="utf-8")
    is_insensitive = (probe / "LOWER").exists()
    shutil.rmtree(probe)
    return is_insensitive


# --- HOLE 1 — HIGH (Cyra re-verify) — self-destruct guard bypassed on a ----
# --- case-insensitive filesystem --------------------------------------------

def test_refuses_case_divergent_same_dir_on_case_insensitive_fs(troot, tmp_path):
    """Cyra's exact fresh repro against 18a3fea: `--from .../STORE --to
    .../store` — differing ONLY in case. `Path.resolve()` preserves
    as-typed case, so on a case-insensitive filesystem (macOS APFS /
    Windows NTFS — this project's real deployment target for both
    `.tess/state/memory` and `~/.claude/projects/.../memory`) these two
    strings resolve to the SAME directory on disk, yet a string-equality
    guard says "different": the guard passed, `--merge` treated the
    directory's own file as "already present" (comparing it to itself),
    nothing was copied elsewhere, `shutil.rmtree()` deleted the only copy,
    and the store became a self-referential symlink loop. Skipped on a
    genuinely case-sensitive filesystem (this repo's own Linux CI
    runners), where `STORE` and `store` really are two distinct
    (nonexistent) directories and this exact repro cannot occur there —
    meaningful and exercised on macOS/Windows dev machines."""
    if not _fs_is_case_insensitive(tmp_path):
        pytest.skip("filesystem is case-sensitive — case-divergent same-dir repro does not apply here")

    store = _to_dir(troot)
    store.mkdir(parents=True)
    (store / "notes.md").write_text("IRREPLACEABLE\n", encoding="utf-8")

    store_divergent = store.parent / store.name.upper()
    assert store_divergent != store  # genuinely different strings...
    assert store_divergent.exists()  # ...but the SAME file on disk (case-insensitive FS)

    r = _run(troot, "memory", "adopt", "--from", str(store_divergent), "--to", str(store), "--yes", "--merge")
    assert r.returncode != 0
    assert "resolve to the same path" in (r.stdout + r.stderr)
    assert "Traceback" not in (r.stdout + r.stderr)  # typed refusal, never a raw crash

    # Content fully intact: still a real directory, not a symlink (loop or
    # otherwise), original bytes unchanged, no manifest ever written.
    assert store.is_dir() and not store.is_symlink()
    assert (store / "notes.md").read_text(encoding="utf-8") == "IRREPLACEABLE\n"
    assert not list(store.glob(".tess-memory-adopt.*.json"))


def test_refuses_nested_case_divergent_dirs_on_case_insensitive_fs(troot, tmp_path):
    """The NESTING variant of HOLE 1: --to is a real subdirectory of
    --from, but --from itself is passed with divergent case. A naive
    string-prefix match against the literal (as-typed-case) resolved
    --from path would miss this entirely, since the on-disk ancestor
    directory is spelled differently; walking ancestors with inode
    identity (`os.path.samefile`) catches it regardless of case."""
    if not _fs_is_case_insensitive(tmp_path):
        pytest.skip("filesystem is case-sensitive — case-divergent nesting repro does not apply here")

    from_dir = _to_dir(troot)
    to_dir = from_dir / "sub"
    from_dir.mkdir(parents=True)
    to_dir.mkdir(parents=True)
    (from_dir / "x.md").write_text("nested-case-hazard content\n", encoding="utf-8")

    from_dir_divergent = from_dir.parent / from_dir.name.upper()
    assert from_dir_divergent != from_dir
    assert from_dir_divergent.exists()

    r = _run(troot, "memory", "adopt", "--from", str(from_dir_divergent), "--to", str(to_dir), "--yes", "--merge")
    assert r.returncode != 0
    assert "resolve to the same path or one is nested inside the other" in (r.stdout + r.stderr)
    assert (from_dir / "x.md").read_text(encoding="utf-8") == "nested-case-hazard content\n"


# --- HOLE 2 — MEDIUM (Cyra re-verify) — reverse-direction 2-harness revert -
# --- deletes a still-depended-on file ---------------------------------------

def test_revert_reverse_direction_two_harnesses_shared_file_preserved(troot, tmp_path):
    """The REVERSE ordering of the already-closed M1 scenario
    (`test_revert_two_harnesses_shared_file_preserved` above). There,
    harness A owned shared.md and harness B deduped against it; here,
    harness B is the ORIGINAL OWNER (adopts first, so shared.md is in
    B's OWN `newly_copied_files`), and harness A adopts SECOND and dedupes
    against the byte-identical shared.md already in the store
    (already_present for A — in A's `source_files` but not A's
    `newly_copied_files`). B then reverts. Before the fix, revert only
    consulted THIS harness's own `newly_copied_files`, so shared.md —
    being B's own recorded copy — was unconditionally moved out of the
    store, silently breaking harness A, which is still live-symlinked to
    it. The fix must recognize that A's manifest still lists shared.md in
    its `source_files` and A is still live, and copy shared.md back into
    B's restored dir while LEAVING it in the store."""
    harness_b = tmp_path / "harness-b" / "memory"
    harness_a = tmp_path / "harness-a" / "memory"
    harness_b.mkdir(parents=True)
    harness_a.mkdir(parents=True)
    (harness_b / "shared.md").write_text("shared content\n", encoding="utf-8")
    (harness_b / "b_only.md").write_text("only B\n", encoding="utf-8")
    (harness_a / "shared.md").write_text("shared content\n", encoding="utf-8")

    to_dir = _to_dir(troot)
    rb = _run(troot, "memory", "adopt", "--harness", "harness-b", "--from", str(harness_b), "--to", str(to_dir), "--yes")
    assert rb.returncode == 0, rb.stdout + rb.stderr
    ra = _run(troot, "memory", "adopt", "--harness", "harness-a", "--from", str(harness_a), "--to", str(to_dir), "--yes", "--merge")
    assert ra.returncode == 0, ra.stdout + ra.stderr

    manifest_b = _manifest(troot, harness="harness-b")
    assert sorted(manifest_b["newly_copied_files"]) == ["b_only.md", "shared.md"]  # B is the original owner
    manifest_a = _manifest(troot, harness="harness-a")
    assert manifest_a["newly_copied_files"] == []  # A deduped — copied nothing
    assert manifest_a["source_files"] == ["shared.md"]

    # Dry-run first: B's revert must classify shared.md as "copy back, kept
    # in store" (NOT "moved out") — it's still A's dependency.
    dry = _run(troot, "memory", "adopt", "--revert", "--harness", "harness-b", "--to", str(to_dir))
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert "DRY RUN" in dry.stdout
    assert "kept in the store" in dry.stdout
    assert "shared.md" in dry.stdout
    assert (to_dir / "shared.md").exists()  # dry-run touched nothing

    # Real revert of B.
    r2 = _run(troot, "memory", "adopt", "--revert", "--harness", "harness-b", "--to", str(to_dir), "--yes")
    assert r2.returncode == 0, r2.stdout + r2.stderr

    # shared.md SURVIVES in the store — harness A still reads it, live,
    # through its own unbroken symlink.
    assert (to_dir / "shared.md").exists()
    assert not (to_dir / "b_only.md").exists()  # b_only.md was only ever B's — correctly removed
    assert harness_a.is_symlink() and harness_a.resolve() == to_dir.resolve()
    assert (harness_a / "shared.md").read_text(encoding="utf-8") == "shared content\n"

    # Harness B got its OWN copy of BOTH files back into its restored dir.
    assert harness_b.is_dir() and not harness_b.is_symlink()
    assert (harness_b / "shared.md").read_text(encoding="utf-8") == "shared content\n"
    assert (harness_b / "b_only.md").read_text(encoding="utf-8") == "only B\n"


# ---------------------------------------------------------------------------
# HOLE 3 — MEDIUM-HIGH (issue #147, inode-vs-string audit sweep) — an OTHER
# harness's manifest is wrongly judged "not live" on a case-divergent
# store spelling, so its shared file is deleted out from under it
# ---------------------------------------------------------------------------

def test_revert_other_harness_case_divergent_live_file_not_deleted(engine, tmp_path):
    """FS-INDEPENDENT reproduction of issue #147 — no monkeypatching of
    `os.path.samefile` needed, no dependency on the test runner's actual
    case-sensitivity in EITHER direction:
      * on a case-SENSITIVE host (this repo's own Linux/ext4 CI runners),
        harness A's symlink target below (`store`'s own name, upper-
        cased) genuinely does not exist as a separate directory, so
        `_paths_are_same_location`'s own EXISTING fallback — a
        case-fold string compare, used precisely because `os.path.
        samefile` requires both sides to exist — kicks in and correctly
        recognizes the two spellings as the same location;
      * on a case-INSENSITIVE host (macOS/APFS, default — also a real
        `tessctl` dev/CI target), that same upper-cased path IS already
        the identical real directory as `store` (case-insensitive
        lookup), so `_paths_are_same_location`'s PRIMARY path —
        `os.path.samefile` itself, unmocked — correctly recognizes it
        directly.
    Either way, deterministically, the FIX (`_paths_are_same_location`)
    recognizes the two spellings as one location, while the PRE-#147 raw
    `other_from.resolve() != to_dir_resolved` string comparison never
    would — `.resolve()` preserves the as-typed case of a symlink's
    recorded target (proven by the HOLE 1 tests above), so it returns the
    literal upper-cased string regardless of which host this runs on.

    Scenario, matching the issue exactly: ONE physical canonical store
    (`store`) that TWO harnesses' adopt manifests are co-located in — the
    real-world precondition for `_memory_adopt_other_live_source_files`
    to even consider a manifest as an "other" candidate at all (it globs
    manifests FROM `to_dir` itself, so both harnesses' manifests living
    in the identical physical directory is not a test artifact, it is
    exactly what happens on a real case-insensitive filesystem when two
    harnesses' `--to` arguments differ only by case). Harness B holds a
    REAL, full adopt (via the actual engine call: symlink, manifest, and
    copied content are all genuine). Harness A is a still-LIVE harness
    whose manifest is (as it always is on the real deployment
    filesystems) co-located in that same physical store, but whose
    recorded `from_path` symlink resolves to a spelling that differs from
    `store` ONLY in case — `_memory_adopt_other_live_source_files` never
    reads content from the OTHER harness's own directory (only its
    manifest JSON's `source_files` list), so this reproduces the exact
    liveness-check divergence without needing harness A's own directory
    to itself be a second real, separately-populated store.

    Harness B then reverts. Pre-#147, `shared.md` — recorded in B's OWN
    `newly_copied_files` (B's store started out empty) — would be
    `shutil.move()`d out of the store because harness A's still-live
    manifest was wrongly excluded from `other_live_source_files`, silently
    breaking harness A, which is still live-symlinked and reads shared.md
    through it. Post-#147, `shared.md` is copied back into B's restored
    directory but correctly LEFT in the store."""
    root = tmp_path / "os"
    root.mkdir()

    store = root / ".tess" / "state" / "store"

    # --- Harness B: a REAL, full adopt (the harness under revert) -------
    from_b = tmp_path / "harness-b-home" / "memory"
    from_b.mkdir(parents=True)
    (from_b / "shared.md").write_text("shared content\n", encoding="utf-8")
    (from_b / "b_only.md").write_text("only B\n", encoding="utf-8")
    result_b = engine._memory_adopt(
        root, from_dir=from_b, to_dir=store, harness="harness-b",
        merge=False, dry_run=False,
    )
    assert result_b["action"] == "adopt"
    assert sorted(result_b["newly_copied_files"]) == ["b_only.md", "shared.md"]
    assert from_b.is_symlink()
    assert (store / "shared.md").exists()

    # --- Harness A: still-live, case-divergent recorded from_path -------
    # from_a itself must NOT be a real directory — it becomes the symlink
    # directly (mirroring the real post-adopt state: from_dir is replaced
    # BY the symlink, never coexists with one).
    from_a = tmp_path / "harness-a-home" / "memory"
    from_a.parent.mkdir(parents=True)
    case_divergent_target = store.parent / store.name.upper()
    assert str(case_divergent_target) != str(store)  # genuinely different STRINGS
    from_a.symlink_to(case_divergent_target)
    assert from_a.is_symlink()

    manifest_a_path = engine._memory_adopt_manifest_path(store, "harness-a", from_a)
    manifest_a_path.write_text(json.dumps({
        "harness": "harness-a",
        "from_path": str(from_a),
        "to_path": str(case_divergent_target),
        "adopted_at": "2026-01-01T00:00:00.000000Z",
        "source_files": ["shared.md"],
        "newly_copied_files": ["shared.md"],
    }, indent=2), encoding="utf-8")
    assert manifest_a_path.exists()

    manifest_b_path = next(store.glob(".tess-memory-adopt.harness-b.*.json"))
    assert manifest_b_path != manifest_a_path

    # The function directly responsible for the bug: with the fix, harness
    # A's still-live, case-divergent manifest must protect shared.md.
    protected = engine._memory_adopt_other_live_source_files(store, manifest_b_path)
    assert "shared.md" in protected, (
        "harness A's still-live shared.md must be protected from removal "
        "by harness B's revert — a case-divergent store spelling must not "
        "defeat the liveness check (issue #147)"
    )

    # Full revert of B, end to end — proves the outer guarantee actually
    # holds, not just the inner helper's return value.
    dry = engine._memory_adopt_revert(root, store, harness="harness-b", dry_run=True)
    assert "shared.md" in dry["would_copy_back"]
    assert "shared.md" not in dry["would_move"]
    assert "b_only.md" in dry["would_move"]

    result = engine._memory_adopt_revert(root, store, harness="harness-b", dry_run=False)
    assert sorted(result["restored_files"]) == ["b_only.md", "shared.md"]

    # THE assertion this test exists for: harness A's live shared file
    # survives in the store — it is NOT deleted by B's revert.
    assert (store / "shared.md").exists()
    assert (store / "shared.md").read_text(encoding="utf-8") == "shared content\n"
    # b_only.md, uniquely B's own, is correctly removed from the store.
    assert not (store / "b_only.md").exists()

    # Harness A's own manifest and symlink are completely untouched by B's
    # revert.
    assert manifest_a_path.exists()
    assert from_a.is_symlink()

    # Harness B's own directory is restored with both files back.
    assert from_b.is_dir() and not from_b.is_symlink()
    assert (from_b / "shared.md").read_text(encoding="utf-8") == "shared content\n"
    assert (from_b / "b_only.md").read_text(encoding="utf-8") == "only B\n"
