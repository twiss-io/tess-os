"""1.0.0: Cyra's security review of f8fb9c6, item b: `tessctl harden` locked
the files but not their folders.

With only the files locked, a process of the operator's user could rename the
folder that holds them (`.claude/hooks/`, say) and put new files in its place.
`harden on` now also locks every folder of the Tess-only trees
(`.claude/hooks/`, `.tess/core/`, `.tess/bin/` and the folders below them),
never `.claude/` itself (Claude Code writes settings.local.json there), the
project folder or `.tess/`, and `harden off` unlocks all of it.

As in tests/test_v1_0_0_harden.py, sudo is never run: a recorder replaces it
and flips fake flags, and a guard fails the test if subprocess.run ever gets
sudo. The OS behaviour the fix relies on (an immutable folder cannot be
renamed and gets no new entries) is checked with the user-settable macOS
flag `uchg`, where the system allows it.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_v1_0_0_harden import _Sudo, _args, no_real_sudo  # noqa: F401 — fixture
from test_v1_r7_engine import HAS_GIT, anchored, proj  # noqa: F401 — fixtures

pytestmark = pytest.mark.skipif(not HAS_GIT, reason="needs git")

TREES = (".claude/hooks", ".tess/core", ".tess/bin")


def _dirs_below(root: Path, tree: str) -> list:
    out = []
    for dp, dn, _fn in os.walk(root / tree):
        dn[:] = [d for d in dn if d != "__pycache__" and not (Path(dp) / d).is_symlink()]
        out.append(Path(dp).relative_to(root).as_posix())
    return out


def test_folders_of_the_tess_only_trees_are_locked(anchored, engine):
    root = anchored
    (root / ".claude" / "hooks" / "__pycache__").mkdir(exist_ok=True)
    os.symlink(str(root / "conductor"), str(root / ".tess" / "core" / "zz-dirlink"))
    paths = engine._harden_paths(root)
    for tree in TREES:
        assert tree in paths, tree
        for d in _dirs_below(root, tree):
            assert d in paths, d
    # never the folders other programs write in, a symlink or a cache folder
    for never in (".claude", ".tess", ".", "", ".git", ".git/hooks", ".claude/hooks/__pycache__",
                  ".tess/core/zz-dirlink"):
        assert never not in paths, never
    # the files are still there, before the folders (locked in that order)
    assert ".claude/hooks/tess-gate.py" in paths
    assert paths.index(".claude/hooks/tess-gate.py") < paths.index(".claude/hooks")


def test_on_locks_the_folders_and_off_unlocks_everything(anchored, engine, monkeypatch, capsys,
                                                         no_real_sudo):  # noqa: F811
    root = anchored
    rec = _Sudo(engine, monkeypatch, root)
    monkeypatch.setattr(engine, "_require_human_presence", lambda *a, **k: None)
    monkeypatch.setattr(engine, "_require_terminal_for_questions", lambda *a, **k: None)
    monkeypatch.setattr(engine.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))
    engine.cmd_harden(_args("on"), root)
    locked = set(rec.calls[-1][1])
    assert set(TREES) <= locked and ".claude" not in locked
    assert engine._harden_state(root)["open"] == []
    engine.cmd_harden(_args("status"), root)
    assert "harden: on" in capsys.readouterr().out
    # a locked folder alone is enough for the commands that rewrite Tess's files to stop
    for rel in list(rec.locked):
        rec.locked.discard(rel)
    rec.locked.add(os.path.realpath(str(root / ".claude" / "hooks")))
    with pytest.raises(SystemExit) as exc:
        engine._harden_refuse_if_locked(root, "update")
    assert "locked by `tessctl harden on`" in str(exc.value.code)
    engine.cmd_harden(_args("status"), root)
    assert "PARTIAL" in capsys.readouterr().out
    # off: every locked file AND folder is unlocked
    engine.cmd_harden(_args("on"), root)
    engine.cmd_harden(_args("off"), root)
    argv, rels = rec.calls[-1]
    assert argv == ["chflags", "noschg"] and set(TREES) <= set(rels)
    st = engine._harden_state(root)
    assert st["locked"] == [] and rec.locked == set()
    engine.cmd_harden(_args("status"), root)
    assert "harden: off" in capsys.readouterr().out


def test_docs_say_what_the_lock_covers_and_what_it_does_not():
    repo = Path(__file__).resolve().parent.parent
    sec = (repo / "SECURITY.md").read_text(encoding="utf-8")
    block = sec[sec.index("Optional OS file lock: `tessctl harden`"):]
    block = block[:block.index("\n- **")]
    flat = " ".join(block.split())
    assert "whatever the spelling" not in flat
    assert "on the folders that hold only such files" in flat
    assert "What it does not cover" in flat
    for name in ("`.claude/`", "`.tess/`", "project folder"):
        assert name in flat, name
    eng = (repo / ".tess" / "bin" / "tessctl").read_text(encoding="utf-8")
    head = eng[eng.index("# OPT-IN FILE LOCK"):eng.index("HARDEN_FILES = ")]
    assert "whatever the" not in " ".join(head.split())
    assert "What it does NOT cover" in head


@pytest.mark.skipif(sys.platform != "darwin", reason="the user-settable flag check is macOS only")
def test_an_immutable_folder_cannot_be_renamed_or_refilled(tmp_path):
    """What the fix relies on, shown with the user-settable `uchg` flag (the
    root-owned `schg` behaves the same and needs root): a locked file can be
    replaced by renaming its unlocked folder; a locked folder stops that."""
    d = tmp_path / "hooks"
    d.mkdir()
    (d / "gate.py").write_text("ok\n")
    if subprocess.run(["chflags", "uchg", str(d / "gate.py")]).returncode != 0:
        pytest.skip("this file system has no user immutable flag")
    try:
        os.rename(str(d), str(tmp_path / "away"))       # file locked, folder not: rename works
        assert (tmp_path / "away" / "gate.py").exists()
        os.rename(str(tmp_path / "away"), str(d))
        subprocess.run(["chflags", "uchg", str(d)], check=True)
        with pytest.raises(PermissionError):
            os.rename(str(d), str(tmp_path / "away"))
        with pytest.raises(PermissionError):
            (d / "new.py").write_text("x\n")
        with pytest.raises(PermissionError):
            os.rename(str(d / "gate.py"), str(d / "old.py"))
    finally:
        subprocess.run(["chflags", "nouchg", str(d), str(d / "gate.py")])
