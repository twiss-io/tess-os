"""
Phase 0.2 hardening (Cyra M2, PR #113 review — issue #114): `_prune_stale_
locks`'s TOCTOU fix.

The ORIGINAL implementation unlinked a `.tess/state/locks/*.lock` file
purely on mtime, with a comment claiming this "can never un-protect an
in-flight critical section." That is wrong: if a THIRD process opens the
SAME path while a live holder's flock is still held on the (about to be
unlinked) OLD inode, the two never exclude each other, and two writers can
run their critical sections concurrently — the exact lost-update race the
per-task/per-shard lock exists to prevent.

Coverage:
  * A genuinely orphaned (stale, unheld) lock file IS still pruned — the
    common case must keep working.
  * A lock file that is CURRENTLY HELD by another real OS process is NEVER
    pruned, even with its mtime forced arbitrarily stale (ttl_seconds=0) —
    proves the non-blocking-flock-first gate.
  * Once the holder releases, a later prune pass DOES clean it up.
  * A fresh (non-stale) lock file is left alone regardless of hold state.
  * The inode-mismatch branch itself, isolated via a monkeypatched
    `os.fstat` (simulating a path that got unlinked-and-recreated between
    our own `open()` and the recheck) — the candidate must be skipped, not
    deleted.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest


@pytest.fixture
def sroot(tmp_path):
    """A minimal root — `_prune_stale_locks` only needs `.tess/state/locks/`
    to exist; it has no dependency on tess.manifest.json or any contract."""
    root = tmp_path / "os"
    (root / ".tess" / "state" / "locks").mkdir(parents=True)
    return root


def _locks_dir(root):
    return root / ".tess" / "state" / "locks"


def test_prune_deletes_a_genuinely_orphaned_stale_lock(engine, sroot):
    lock_path = _locks_dir(sroot) / "task-orphan.lock"
    lock_path.write_text("")
    old = time.time() - 999_999
    os.utime(lock_path, (old, old))

    pruned = engine._prune_stale_locks(sroot, ttl_seconds=3600)
    assert pruned == 1
    assert not lock_path.exists()


def test_prune_leaves_a_fresh_lock_alone_regardless_of_hold_state(engine, sroot):
    lock_path = _locks_dir(sroot) / "task-fresh.lock"
    lock_path.write_text("")  # mtime is "now" — not stale

    pruned = engine._prune_stale_locks(sroot, ttl_seconds=3600)
    assert pruned == 0
    assert lock_path.exists()


def test_prune_never_deletes_a_currently_held_lock_even_with_ttl_zero(engine, sroot):
    """The core Cyra M2 guarantee: staleness (an old mtime, or here — a
    ttl_seconds=0 forcing EVERYTHING to look stale) is necessary but not
    sufficient. A real, separate OS process holds an exclusive flock on
    this lock file for the duration of the test; `_prune_stale_locks` must
    refuse to delete it no matter how stale its mtime looks."""
    lock_path = _locks_dir(sroot) / "task-held.lock"
    lock_path.write_text("")
    old = time.time() - 999_999
    os.utime(lock_path, (old, old))

    holder_script = (
        "import fcntl, sys, time\n"
        "f = open(sys.argv[1], 'a+')\n"
        "fcntl.flock(f, fcntl.LOCK_EX)\n"
        "print('LOCKED', flush=True)\n"
        "time.sleep(4)\n"
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", holder_script, str(lock_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        # Wait for the holder to actually acquire the flock before pruning.
        line = holder.stdout.readline()
        assert line.strip() == "LOCKED", f"holder failed to lock: {line}{holder.stdout.read()}"

        pruned = engine._prune_stale_locks(sroot, ttl_seconds=0)
        assert pruned == 0
        assert lock_path.exists(), (
            "a lock file HELD by a live process must never be unlinked, "
            "even when every mtime-based staleness check would flag it"
        )
    finally:
        holder.wait(timeout=10)

    # Now that the holder has released and exited, a later pass DOES reap it
    # (still stale by mtime — the holder never wrote to it, so mtime is
    # unchanged).
    pruned_after = engine._prune_stale_locks(sroot, ttl_seconds=0)
    assert pruned_after == 1
    assert not lock_path.exists()


def test_prune_inode_mismatch_skips_deletion(monkeypatch, engine, sroot):
    """Isolates the inode-recheck branch itself: `os.fstat(fd).st_ino` (the
    inode OUR open() actually locked) is monkeypatched to report a value
    that differs from the path's CURRENT (real) inode — simulating a
    concurrent unlink+recreate that raced our own open()+flock(). The
    candidate must be skipped, not deleted, and the file must survive
    untouched."""
    lock_path = _locks_dir(sroot) / "task-race.lock"
    lock_path.write_text("")
    old = time.time() - 999_999
    os.utime(lock_path, (old, old))

    real_fstat = os.fstat

    class _FakeStat:
        def __init__(self, st_ino):
            self.st_ino = st_ino

    def fake_fstat(fd):
        real = real_fstat(fd)
        return _FakeStat(real.st_ino + 999_999)  # deliberately wrong

    monkeypatch.setattr(os, "fstat", fake_fstat)

    pruned = engine._prune_stale_locks(sroot, ttl_seconds=0)
    assert pruned == 0
    assert lock_path.exists(), "an apparent open-fd/path inode mismatch must never be deleted"
