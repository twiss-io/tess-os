"""
self-update: backup / atomic replace / rollback.

  * a valid signed upstream engine replaces .tess/bin/tessctl, keeping a .bak
  * a syntactically broken upstream engine is rejected at AST parse — BEFORE the
    live engine is touched (no replace, no backup)
  * an engine that parses but crashes when run (`doctor`) is rolled back to .bak
"""

from __future__ import annotations

import pytest

from conftest import ENGINE_SRC, make_upstream, ns

ORIGINAL = ENGINE_SRC.read_bytes()
MARKER = b"\n# SELFUPDATE-MARKER v2.0.1\n"

CRASH_ENGINE = (
    b"import sys\n"
    b"sys.stderr.write('Traceback (most recent call last):\\n  boom\\n')\n"
    b"sys.exit(2)\n"
)
BROKEN_ENGINE = b"def broken(:\n    pass\n"


def _prep(project, up):
    project.add("conductor/a.md", "alpha\n")
    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.write()


def test_self_update_replaces_engine_and_keeps_backup(project, gpg_key, tmp_path):
    up = make_upstream(
        tmp_path / "up_ok", gpg_key, "v2.0.1", sign="signed",
        core_files={".tess/core/conductor/guardrails.md": "g\n"},
        engine_bytes=ORIGINAL + MARKER,
    )
    _prep(project, up)

    # No pin in lock → fail-closed; opt into TOFU for this first-use self-update.
    project.mod.cmd_self_update(ns(ref="v2.0.1", to=None, trust_on_first_use=True), project.root)

    engine_path = project.root / ".tess" / "bin" / "tessctl"
    backup_path = project.root / ".tess" / "bin" / "tessctl.bak"
    assert MARKER in engine_path.read_bytes()          # new engine installed
    assert backup_path.exists()
    assert backup_path.read_bytes() == ORIGINAL        # previous engine retained
    # ref change recorded in lock
    lock = project.mod.load_lock(project.root)
    assert lock["framework"]["upstream_ref"] == "v2.0.1"


def test_self_update_aborts_on_unparseable_engine(project, gpg_key, tmp_path):
    up = make_upstream(
        tmp_path / "up_broken", gpg_key, "v2.0.1", sign="signed",
        engine_bytes=BROKEN_ENGINE,
    )
    _prep(project, up)

    # allow_tofu so we get past signature verification to the AST parse-check.
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_self_update(ns(ref="v2.0.1", to=None, trust_on_first_use=True), project.root)
    assert "parse" in str(ei.value).lower()

    engine_path = project.root / ".tess" / "bin" / "tessctl"
    backup_path = project.root / ".tess" / "bin" / "tessctl.bak"
    # Live engine untouched; no backup made (abort happens before replace).
    assert engine_path.read_bytes() == ORIGINAL
    assert not backup_path.exists()


def test_self_update_rolls_back_when_new_engine_crashes(project, gpg_key, tmp_path):
    up = make_upstream(
        tmp_path / "up_crash", gpg_key, "v2.0.1", sign="signed",
        engine_bytes=CRASH_ENGINE,
    )
    _prep(project, up)

    # allow_tofu so we get past signature verification to the engine swap + rollback.
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_self_update(ns(ref="v2.0.1", to=None, trust_on_first_use=True), project.root)
    assert "rolled back" in str(ei.value).lower()

    engine_path = project.root / ".tess" / "bin" / "tessctl"
    backup_path = project.root / ".tess" / "bin" / "tessctl.bak"
    # Rolled back to the working engine.
    assert engine_path.read_bytes() == ORIGINAL
    assert backup_path.exists()


def test_self_update_rejects_unsigned_upstream(project, gpg_key, tmp_path):
    up = make_upstream(
        tmp_path / "up_unsigned", gpg_key, "v2.0.1", sign="lightweight",
        engine_bytes=ORIGINAL + MARKER,
    )
    _prep(project, up)

    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_self_update(ns(ref="v2.0.1", to=None), project.root)
    assert "SECURITY REJECT" in str(ei.value)
    engine_path = project.root / ".tess" / "bin" / "tessctl"
    assert engine_path.read_bytes() == ORIGINAL  # unchanged
