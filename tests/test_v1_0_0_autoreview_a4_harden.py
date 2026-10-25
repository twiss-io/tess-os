"""1.0.0: the automated security review of a4113f7, item c: `tessctl harden`
listed the paths, then ran a root-level `chflags`/`chattr` on them. A path
swapped for a symlink between the listing and the call would be followed by
the root call.

The fix: macOS passes `chflags -h` (acts on a link itself); every path is
re-checked with `lstat` right before each sudo batch and a path that is now a
link, gone, or no longer the listed file/folder stops the run before sudo; and
after the call the locked (or unlocked) set's device/inode identities must
equal the listed set, or the command fails loudly. `harden off` gets the same.

As in the other harden tests, sudo is never run: a stub records the argv, and
`no_real_sudo` fails the test if subprocess.run is ever handed sudo.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_v1_0_0_harden import _Sudo, _args, no_real_sudo  # noqa: F401 — fixtures
from test_v1_r7_engine import HAS_GIT, anchored, proj  # noqa: F401 — fixtures

pytestmark = pytest.mark.skipif(not HAS_GIT, reason="needs git")


def test_nofollow_argv_keeps_the_call_off_links(engine):
    # macOS: -h acts on the link itself; options end before the flag operand
    assert engine._harden_argv(["chflags", "schg"], ["/a", "/b"]) == \
        ["chflags", "-h", "--", "schg", "/a", "/b"]
    assert engine._harden_argv(["chflags", "noschg"], ["/a"]) == \
        ["chflags", "-h", "--", "noschg", "/a"]
    # Linux chattr has no link switch; the re-check is what keeps it off links
    assert engine._harden_argv(["chattr", "+i"], ["/a", "/b"]) == \
        ["chattr", "+i", "--", "/a", "/b"]


def test_recheck_flags_a_path_swapped_for_a_link_or_moved(anchored, engine):
    root = anchored
    rels = engine._harden_paths(root)
    ids = {r: engine._harden_ident(root / r) for r in rels}
    assert engine._harden_recheck(root, rels, ids) == []        # unchanged: nothing flagged
    # a file swapped for a symlink
    victim = ".claude/hooks/tess-gate.py"
    p = root / victim
    data = p.read_bytes()
    p.unlink()
    os.symlink("/etc/hosts", str(p))
    try:
        assert victim in engine._harden_recheck(root, rels, ids)
        # a parent folder step swapped for a symlink flags the paths below it
        folder = ".tess/bin"
        fp = root / folder
        moved = root / ".tess" / "bin.real"
        os.rename(str(fp), str(moved))
        os.symlink(str(moved), str(fp))
        try:
            below = [r for r in rels if r.startswith(folder + "/")]
            assert below and set(below) <= set(engine._harden_recheck(root, rels, ids))
        finally:
            os.unlink(str(fp))
            os.rename(str(moved), str(fp))
    finally:
        if p.is_symlink():
            p.unlink()
        p.write_bytes(data)


def test_run_sudo_stops_before_sudo_when_a_path_became_a_link(anchored, engine, monkeypatch):
    root = anchored
    rels = engine._harden_paths(root)
    ids = {r: engine._harden_ident(root / r) for r in rels}
    calls = []
    monkeypatch.setattr(engine.subprocess, "run",
                        lambda argv, **k: calls.append(argv) or subprocess.CompletedProcess(argv, 0))
    # clean tree: sudo is invoked, with -h/-- for chflags, and recheck passes
    rc = engine._harden_run_sudo(root, ["chflags", "schg"], rels, ids)
    assert rc == 0 and calls and calls[0] == ["sudo", "-v"]
    assert calls[1][:6] == ["sudo", "-n", "--", "chflags", "-h", "--"]
    # now swap a path for a link and expect a hard stop, with no sudo run
    calls.clear()
    victim = ".claude/hooks/tess-gate.py"
    p = root / victim
    data = p.read_bytes()
    p.unlink()
    os.symlink("/etc/hosts", str(p))
    try:
        with pytest.raises(SystemExit) as exc:
            engine._harden_run_sudo(root, ["chflags", "schg"], rels, ids)
        assert "changed after they were listed" in str(exc.value.code)
        assert victim in str(exc.value.code)
        assert calls == [["sudo", "-v"]]  # authenticated only; no flag call
    finally:
        if p.is_symlink():
            p.unlink()
        p.write_bytes(data)


def test_on_fails_loudly_when_a_locked_path_is_not_the_one_listed(anchored, engine, monkeypatch,
                                                                  no_real_sudo):  # noqa: F811
    """After the call, cmd_harden checks that the set it acted on is the set it
    listed (device/inode). If a path was replaced mid-flight, it fails loudly."""
    root = anchored
    rec = _Sudo(engine, monkeypatch, root)
    monkeypatch.setattr(engine, "_require_human_presence", lambda *a, **k: None)
    monkeypatch.setattr(engine, "_require_terminal_for_questions", lambda *a, **k: None)
    monkeypatch.setattr(engine.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))
    victim = ".claude/hooks/tess-gate.py"

    def swap_then_lock(r, argv, rels, ids=None):
        # the real sudo would lock them; here we also simulate another process
        # replacing one path with a different file during the call. The
        # original is renamed away, not deleted, so it keeps its inode and the
        # new file cannot reuse it (Linux reuses a freed inode at once).
        p = root / victim
        if p.exists() and not p.is_symlink():
            os.rename(str(p), str(p) + ".orig")
            p.write_bytes(b"different\n")   # a new inode: identity no longer matches
        for rel in rels:
            rec.locked.add(os.path.realpath(str(r / rel)))
        return 0
    monkeypatch.setattr(engine, "_harden_run_sudo", swap_then_lock)
    with pytest.raises(SystemExit) as exc:
        engine.cmd_harden(_args("on"), root)
    assert "not the files or folders that were listed" in str(exc.value.code)
    assert victim in str(exc.value.code)


def test_off_also_rechecks_and_passes_the_link_switch(anchored, engine, monkeypatch, no_real_sudo):  # noqa: F811
    root = anchored
    rels = engine._harden_paths(root)
    ids = {r: engine._harden_ident(root / r) for r in rels}
    calls = []
    monkeypatch.setattr(engine.subprocess, "run",
                        lambda argv, **k: calls.append(argv) or subprocess.CompletedProcess(argv, 0))
    rc = engine._harden_run_sudo(root, ["chflags", "noschg"], rels, ids)
    assert rc == 0 and calls[0] == ["sudo", "-v"]
    assert calls[1][:6] == ["sudo", "-n", "--", "chflags", "-h", "--"]


# ---------------------------------------------------------------------------
# RC hardening (automated push review): sudo may ask for a password, and a
# path step can change while it waits. Each batch now authenticates first
# (`sudo -v`, no privileged action), THEN re-checks every step with lstat,
# THEN applies the flag with `sudo -n` (which never prompts, so no new wait
# opens between the re-check and the call). The identity check afterwards is
# unchanged. A fake `sudo` shim on PATH stands in; the real sudo never runs.
# ---------------------------------------------------------------------------

_SUDO_SHIM = r'''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_SUDO_LOG"], "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\n")
swap = os.environ.get("FAKE_SUDO_SWAP_ON_AUTH")
if sys.argv[1:] == ["-v"] and swap:
    # what another process could do while sudo waits for the password:
    # replace a parent folder step with a symlink to a copy of it
    real = swap + ".during-prompt"
    os.rename(swap, real)
    os.symlink(real, swap)
sys.exit(0)
'''


@pytest.fixture
def sudo_shim(tmp_path, monkeypatch):
    import json as _json
    import shutil as _shutil
    bindir = tmp_path / "shim-bin"
    bindir.mkdir()
    shim = bindir / "sudo"
    shim.write_text(_SUDO_SHIM)
    shim.chmod(0o755)
    log = tmp_path / "sudo.log"
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_SUDO_LOG", str(log))
    monkeypatch.delenv("FAKE_SUDO_SWAP_ON_AUTH", raising=False)
    # never the real sudo
    assert _shutil.which("sudo") == str(shim)

    def calls():
        return [_json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
    return calls


def test_run_sudo_authenticates_before_the_recheck_and_never_prompts_after_it(anchored, engine, sudo_shim):
    root = anchored
    rels = engine._harden_paths(root)
    ids = {r: engine._harden_ident(root / r) for r in rels}
    rc = engine._harden_run_sudo(root, ["chflags", "schg"], rels, ids)
    calls = sudo_shim()
    assert rc == 0
    assert calls[0] == ["-v"], calls
    assert calls[1][:5] == ["-n", "--", "chflags", "-h", "--"], calls
    assert all(c == ["-v"] or c[:2] == ["-n", "--"] for c in calls)


def test_a_parent_step_swapped_for_a_link_during_the_password_prompt_is_refused(anchored, engine, sudo_shim,
                                                                                monkeypatch):
    root = anchored
    rels = engine._harden_paths(root)
    ids = {r: engine._harden_ident(root / r) for r in rels}
    folder = root / ".tess" / "bin"
    below = [r for r in rels if r.startswith(".tess/bin/")]
    assert below
    monkeypatch.setenv("FAKE_SUDO_SWAP_ON_AUTH", str(folder))
    try:
        with pytest.raises(SystemExit) as exc:
            engine._harden_run_sudo(root, ["chflags", "schg"], rels, ids)
        assert "changed after they were listed" in str(exc.value.code)
        # authenticated, then the re-check caught the swapped parent step:
        # no flag call was ever made
        assert sudo_shim() == [["-v"]]
    finally:
        if folder.is_symlink():
            real = Path(os.readlink(str(folder)))
            folder.unlink()
            os.rename(str(real), str(folder))


def test_recheck_refuses_a_symlinked_parent_step_even_when_the_leaf_is_unchanged(anchored, engine):
    root = anchored
    rels = engine._harden_paths(root)
    ids = {r: engine._harden_ident(root / r) for r in rels}
    folder = root / ".tess" / "bin"
    moved = root / ".tess" / "bin.moved"
    os.rename(str(folder), str(moved))
    os.symlink(str(moved), str(folder))
    try:
        below = [r for r in rels if r.startswith(".tess/bin/") and "/" not in r[len(".tess/bin/"):]]
        assert below
        # the leaf files keep their inodes through the link; only the parent step changed
        assert all(engine._harden_ident(moved / Path(r).name) == ids[r] for r in below)
        bad = engine._harden_recheck(root, rels, ids)
        assert set(below) <= set(bad)
        assert ".tess/bin" in bad
    finally:
        folder.unlink()
        os.rename(str(moved), str(folder))
