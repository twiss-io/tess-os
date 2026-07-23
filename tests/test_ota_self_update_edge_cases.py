"""
Regression coverage for issue #22 (OTA upgrade regression tests) — self-update
edge cases not covered by test_self_update.py / test_fail_closed_first_use.py:

  * D1 explicitly treats `doctor` exit 0 OR 1 as "the new engine ran cleanly"
    (only codes outside {0, 1} are an engine-level crash). No existing test
    drives an install where the post-install doctor check genuinely exits 1
    (uncaptured drift) — only the crash-rollback (exit outside {0,1}) and the
    implicit-clean (exit 0) paths are exercised elsewhere.
  * The retained `.bak` is documented as "overwritten on every self-update" —
    untested across two successive hops.
  * A fresh install with no prior engine on disk (the "(no existing engine to
    backup)" branch) — untested.
  * Atomic-install failure (the tempfile-write-then-os.replace step itself
    fails) must roll back to the pre-upgrade engine, clean up its own temp
    file, and exit with a clear message — untested.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys

import pytest

from conftest import ENGINE_SRC, make_upstream, ns

ORIGINAL = ENGINE_SRC.read_bytes()


def _lock_upstream(project, up, ref="v2.0.0", fingerprint=None):
    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = ref
    if fingerprint is not None:
        project.framework["trusted_key_fingerprint"] = fingerprint


# ---------------------------------------------------------------------------
# doctor exit 1 (uncaptured drift, functional but not clean) → engine KEPT
# ---------------------------------------------------------------------------


def test_self_update_keeps_new_engine_when_post_install_doctor_exits_1(project, gpg_key, tmp_path):
    # A core-managed file whose live copy was hand-edited without capture —
    # doctor must report this as uncaptured drift (exit 1), not a crash.
    project.add("conductor/a.md", "alpha\n", status="core-managed")
    project.write_live("conductor/a.md", "uncaptured hand-edit — never ran tessctl capture\n")

    marker = b"\n# SU-DOCTOR-EXIT1-MARKER\n"
    up = make_upstream(
        tmp_path / "up_doctor1", gpg_key, "v2.0.1", sign="signed",
        core_files={".tess/core/conductor/guardrails.md": "g\n"},
        engine_bytes=ORIGINAL + marker,
    )
    _lock_upstream(project, up, fingerprint=gpg_key.fpr)
    project.write()

    engine_path = project.root / ".tess" / "bin" / "tessctl"

    # Sanity/non-tautology check: prove the fixture genuinely produces a
    # doctor exit 1 BEFORE self-update touches anything — otherwise this test
    # would pass for the wrong reason (doctor secretly exiting 0).
    pre = subprocess.run(
        [sys.executable, str(engine_path), "doctor"],
        cwd=str(project.root), env={**os.environ, "TESS_ROOT": str(project.root)},
        capture_output=True, text=True,
    )
    assert pre.returncode == 1, (
        f"fixture must produce a genuine doctor exit 1 (uncaptured drift); "
        f"got {pre.returncode}:\n{pre.stdout}\n{pre.stderr}"
    )

    # Must NOT raise — D1 treats exit 1 as "ran cleanly", so self-update
    # completes normally instead of rolling back.
    project.mod.cmd_self_update(ns(ref="v2.0.1", to=None, trust_on_first_use=False), project.root)

    assert marker in engine_path.read_bytes(), "new engine must be KEPT, not rolled back, on doctor exit 1"
    backup_path = engine_path.with_suffix(".bak")
    assert backup_path.exists()
    assert backup_path.read_bytes() == ORIGINAL


# ---------------------------------------------------------------------------
# .bak retention — overwritten on every self-update, not left stale
# ---------------------------------------------------------------------------


def test_self_update_backup_is_overwritten_on_second_hop(project, gpg_key, tmp_path):
    project.add("conductor/a.md", "alpha\n")
    marker1 = b"\n# SU-HOP1-MARKER\n"
    marker2 = b"\n# SU-HOP2-MARKER\n"

    up1 = make_upstream(
        tmp_path / "up_hop1", gpg_key, "v2.0.1", sign="signed",
        core_files={".tess/core/conductor/guardrails.md": "g\n"},
        engine_bytes=ORIGINAL + marker1,
    )
    _lock_upstream(project, up1, fingerprint=gpg_key.fpr)
    project.write()

    engine_path = project.root / ".tess" / "bin" / "tessctl"
    backup_path = engine_path.with_suffix(".bak")

    project.mod.cmd_self_update(ns(ref="v2.0.1", to=None, trust_on_first_use=False), project.root)
    assert marker1 in engine_path.read_bytes()
    assert backup_path.read_bytes() == ORIGINAL
    engine_after_hop1 = engine_path.read_bytes()

    up2 = make_upstream(
        tmp_path / "up_hop2", gpg_key, "v2.0.2", sign="signed",
        core_files={".tess/core/conductor/guardrails.md": "g\n"},
        engine_bytes=ORIGINAL + marker2,
    )
    project.framework["upstream"] = str(up2)
    project.write()

    project.mod.cmd_self_update(ns(ref="v2.0.2", to=None, trust_on_first_use=False), project.root)
    assert marker2 in engine_path.read_bytes()
    # The backup now holds hop 1's engine (the engine that was LIVE right
    # before this second hop), not the very first original — proving the
    # docstring's "overwritten on every self-update" contract, not a stale
    # one-time snapshot.
    assert backup_path.read_bytes() == engine_after_hop1
    assert backup_path.read_bytes() != ORIGINAL


# ---------------------------------------------------------------------------
# fresh install — no prior engine on disk → no backup, still installs + execs
# ---------------------------------------------------------------------------


def test_self_update_with_no_existing_engine_installs_without_backup(project, gpg_key, tmp_path):
    project.add("conductor/a.md", "alpha\n")
    engine_path = project.root / ".tess" / "bin" / "tessctl"
    engine_path.unlink()
    assert not engine_path.exists()

    marker = b"\n# SU-FRESH-INSTALL-MARKER\n"
    up = make_upstream(
        tmp_path / "up_fresh", gpg_key, "v2.0.1", sign="signed",
        core_files={".tess/core/conductor/guardrails.md": "g\n"},
        engine_bytes=ORIGINAL + marker,
    )
    _lock_upstream(project, up, fingerprint=gpg_key.fpr)
    project.write()

    project.mod.cmd_self_update(ns(ref="v2.0.1", to=None, trust_on_first_use=False), project.root)

    assert marker in engine_path.read_bytes()
    backup_path = engine_path.with_suffix(".bak")
    assert not backup_path.exists(), "nothing existed to back up — no .bak should be created"

    mode = stat.S_IMODE(engine_path.stat().st_mode)
    assert mode & 0o111, "installed engine must be executable even with no prior mode to preserve"


# ---------------------------------------------------------------------------
# atomic install failure → rollback, no orphan temp file, clear exit message
# ---------------------------------------------------------------------------


def test_self_update_rolls_back_and_cleans_up_on_atomic_install_failure(
    project, gpg_key, tmp_path, monkeypatch, capsys,
):
    project.add("conductor/a.md", "alpha\n")
    up = make_upstream(
        tmp_path / "up_failinstall", gpg_key, "v2.0.1", sign="signed",
        core_files={".tess/core/conductor/guardrails.md": "g\n"},
        engine_bytes=ORIGINAL + b"\n# SHOULD-NEVER-INSTALL-ATOMIC-FAIL\n",
    )
    _lock_upstream(project, up, fingerprint=gpg_key.fpr)
    project.write()

    engine_path = project.root / ".tess" / "bin" / "tessctl"
    before = engine_path.read_bytes()
    before_dir_listing = set(p.name for p in engine_path.parent.iterdir())

    real_replace = project.mod.os.replace
    calls = {"n": 0}

    def _boom(src, dst, *a, **kw):
        # Only intercept the ENGINE swap itself — any other os.replace call
        # elsewhere in the same process (e.g. tempfile/save_lock internals)
        # must behave exactly as before.
        if str(dst) == str(engine_path):
            calls["n"] += 1
            raise OSError("simulated disk failure during atomic engine replace")
        return real_replace(src, dst, *a, **kw)

    monkeypatch.setattr(project.mod.os, "replace", _boom)

    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_self_update(ns(ref="v2.0.1", to=None, trust_on_first_use=False), project.root)

    assert calls["n"] == 1, "the mocked failure must actually be hit exactly once"
    assert "installation failed" in str(ei.value).lower()

    captured = capsys.readouterr()
    assert "rolled back to backup after install failure" in captured.out

    assert engine_path.read_bytes() == before, "pre-upgrade engine must survive a failed install"
    backup_path = engine_path.with_suffix(".bak")
    assert backup_path.exists()

    # The retained/refreshed `.bak` is an EXPECTED artifact of Step 3 (backup)
    # regardless of the Step 4 install outcome — only flag genuine orphans:
    # the mkstemp scratch file Step 4 creates and must clean up on failure.
    after_dir_listing = set(p.name for p in engine_path.parent.iterdir())
    new_entries = after_dir_listing - before_dir_listing
    orphans = {n for n in new_entries if n.startswith(".tessctl_selfupdate_")}
    assert orphans == set(), f"orphan temp file(s) left behind after failed install: {orphans}"
