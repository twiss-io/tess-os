"""1.0.0 (section 2, operator decision 22 Oct): opt-in `tessctl harden`.

`tessctl harden on` sets the operating system's root-owned immutable flag
(`schg` on macOS, `chattr +i` on Linux) on the files only Tess writes, so no
process of the operator's user can change them whatever the spelling. The
contract tested here:

  * off by default: nothing is locked until the operator runs `harden on`;
  * only `harden on` / `harden off` ever run sudo, and only after the
    presence check (a real terminal, outside Claude Code and Codex); the gate
    refuses both to agents in every spelling; `harden status` is read-only;
  * `harden on` refuses while the anchor reports changed safety files, or
    while `tessctl verify` fails, so a changed gate is never locked in;
  * never locked: .claude/settings.local.json, the git config, .mcp.json,
    and no symlink;
  * while any file is locked, commands that rewrite Tess's files stop
    before changing anything and say to run `harden off` first (none of them
    runs sudo); dry runs and checks go ahead;
  * the undo path is `harden off` (documented, with the manual commands).

Real root-owned flags need root, so the sudo call is replaced by a recorder
and the flag read by a fake; the flag reader itself is checked with the
user-settable macOS flag (`uchg`), where the system allows it.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_v1_n1_n3 import _all as _gate_all, proj as gate_proj  # noqa: F401
from test_v1_r7_engine import HAS_GIT, anchored, proj  # noqa: F401 — fixtures

pytestmark = pytest.mark.skipif(not HAS_GIT, reason="needs git")


class _Sudo:
    """Records sudo calls and flips the fake flags as the real command would."""

    def __init__(self, engine, monkeypatch, root):
        self.calls, self.locked, self.ids = [], set(), []
        monkeypatch.setattr(engine, "_harden_flag",
                            lambda p: os.path.realpath(str(p)) in self.locked)
        monkeypatch.setattr(engine, "_harden_tool",
                            lambda: (["chflags", "schg"], ["chflags", "noschg"]))

        def run(r, argv, rels, ids=None):
            self.calls.append((list(argv), list(rels)))
            self.ids.append(ids)
            for rel in rels:
                (self.locked.add if argv[1] == "schg" else self.locked.discard)(
                    os.path.realpath(str(r / rel)))
            return 0
        monkeypatch.setattr(engine, "_harden_run_sudo", run)


@pytest.fixture
def no_real_sudo(monkeypatch):
    """Any subprocess call to sudo in these tests is a failure."""
    real = subprocess.run

    def guard(argv, *a, **k):
        assert not (isinstance(argv, (list, tuple)) and argv and os.path.basename(str(argv[0])) == "sudo"), argv
        return real(argv, *a, **k)
    monkeypatch.setattr(subprocess, "run", guard)


def _args(sub):
    return type("A", (), {"harden_sub": sub})()


def test_off_by_default(anchored, engine, capsys, no_real_sudo):
    st = engine._harden_state(anchored)
    assert st["locked"] == [] and len(st["open"]) + len(st["unknown"]) > 0
    engine.cmd_harden(_args("status"), anchored)
    out = capsys.readouterr().out
    assert "harden: off" in out or "not available" in out


def test_locked_set_excludes_what_others_write(anchored, engine):
    root = anchored
    (root / ".claude" / "settings.local.json").write_text("{}")
    (root / ".mcp.json").write_text("{}")
    os.symlink(str(root / "README.md"), str(root / ".claude" / "hooks" / "zz-link"))
    paths = engine._harden_paths(root)
    for never in (".claude/settings.local.json", ".git/config", ".mcp.json", ".claude/hooks/zz-link"):
        assert never not in paths, never
    for must in (".claude/settings.json", ".claude/hooks/tess-gate.py", ".tess/tess.lock", "tessctl",
                 ".tess/bin/tessctl"):
        assert must in paths, must
    assert not any("__pycache__" in p for p in paths)


def test_on_needs_a_person_at_a_terminal(anchored, engine, monkeypatch, no_real_sudo):
    rec = _Sudo(engine, monkeypatch, anchored)
    monkeypatch.setenv("CLAUDECODE", "1")
    with pytest.raises(SystemExit) as exc:
        engine.cmd_harden(_args("on"), anchored)
    assert "assistant session" in str(exc.value.code) and rec.calls == []
    monkeypatch.delenv("CLAUDECODE")
    for k in ("CLAUDE_CODE_ENTRYPOINT", "CODEX_THREAD_ID", "CODEX_SANDBOX"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(sys, "stdin", open(os.devnull))
    with pytest.raises(SystemExit) as exc:
        engine.cmd_harden(_args("on"), anchored)
    assert "interactive terminal" in str(exc.value.code) and rec.calls == []


def test_on_refuses_when_safety_files_changed(anchored, engine, monkeypatch, no_real_sudo):
    rec = _Sudo(engine, monkeypatch, anchored)
    monkeypatch.setattr(engine, "_require_human_presence", lambda *a, **k: None)
    monkeypatch.setattr(engine, "_require_terminal_for_questions", lambda *a, **k: None)
    (anchored / ".claude" / "hooks" / "tess-gate.py").write_text("# stub gate\n")
    with pytest.raises(SystemExit) as exc:
        engine.cmd_harden(_args("on"), anchored)
    assert "REFUSED" in str(exc.value.code) and "lock in changed" in str(exc.value.code)
    assert rec.calls == []


def test_on_status_writers_refuse_and_off(anchored, engine, monkeypatch, capsys, no_real_sudo):
    root = anchored
    rec = _Sudo(engine, monkeypatch, root)
    seen = []
    monkeypatch.setattr(engine, "_require_human_presence", lambda cmd, *a, **k: seen.append(cmd))
    monkeypatch.setattr(engine, "_require_terminal_for_questions", lambda *a, **k: None)
    monkeypatch.setattr(engine.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))
    engine.cmd_harden(_args("on"), root)
    assert seen == ["harden on"]
    argv, rels = rec.calls[-1]
    assert argv == ["chflags", "schg"] and ".claude/hooks/tess-gate.py" in rels
    assert not set(rels) & {".claude/settings.local.json", ".git/config", ".mcp.json"}
    engine.cmd_harden(_args("status"), root)
    assert "harden: on" in capsys.readouterr().out
    # every command that rewrites Tess's files stops first, without sudo
    for verb in engine.HARDEN_WRITERS:
        with pytest.raises(SystemExit) as exc:
            engine._harden_refuse_if_locked(root, verb)
        assert "locked by `tessctl harden on`" in str(exc.value.code)
        assert "harden off" in str(exc.value.code)
    n = len(rec.calls)
    engine.cmd_harden(_args("off"), root)
    assert seen[-1] == "harden off" and rec.calls[-1][0] == ["chflags", "noschg"]
    assert len(rec.calls) == n + 1 and engine._harden_state(root)["locked"] == []
    engine._harden_refuse_if_locked(root, "update")  # unlocked: goes ahead


@pytest.mark.parametrize("argv,stops", [
    (["update"], True), (["restore"], True), (["render"], True), (["reset", "x"], True),
    (["lock", "--regen", "--yes"], True),
    (["restore", "--dry-run"], False), (["update", "--check"], False), (["lock", "--check"], False),
])
def test_main_dispatch_stops_writers_while_locked(anchored, engine, monkeypatch, argv, stops, no_real_sudo):
    root = anchored
    monkeypatch.setattr(engine, "_harden_flag", lambda p: True)
    monkeypatch.setenv("TESS_ROOT", str(root))
    monkeypatch.chdir(root)
    called = []
    for name in ("cmd_update", "cmd_restore", "cmd_render", "cmd_reset", "cmd_lock"):
        monkeypatch.setattr(engine, name, lambda *a, _n=name, **k: called.append(_n))
    monkeypatch.setattr(sys, "argv", ["tessctl"] + argv)
    if stops:
        with pytest.raises(SystemExit) as exc:
            engine.main()
        assert "locked by `tessctl harden on`" in str(exc.value.code) and called == []
    else:
        try:
            engine.main()
        except SystemExit as e:
            assert "locked by" not in str(e.code)
        assert called, "a dry run or check must reach its command"


@pytest.mark.skipif(sys.platform != "darwin", reason="reads BSD file flags")
def test_flag_reader_sees_an_immutable_flag(engine, tmp_path, monkeypatch):
    """With the user immutable bit standing in for the root-owned one (which
    needs root), the reader reports the flag and its absence."""
    import stat as _stat
    f = tmp_path / "x"
    f.write_text("x")
    monkeypatch.setattr(engine, "_SF_IMMUTABLE", _stat.UF_IMMUTABLE)
    assert engine._harden_flag(f) is False
    subprocess.run(["chflags", "uchg", str(f)], check=True)
    try:
        assert engine._harden_flag(f) is True
    finally:
        subprocess.run(["chflags", "nouchg", str(f)], check=True)
    assert engine._harden_flag(tmp_path / "missing") is None


@pytest.mark.parametrize("cmd,want", [
    ("./tessctl harden on", "deny"), ("./tessctl harden off", "deny"), ("tessctl harden ON", "deny"),
    ('bash -c "./tessctl harden off"', "deny"),
    ("python3 -c \"import subprocess; subprocess.run(['./tessctl','harden','off'])\"", "deny"),
    ("./tessctl harden", "allow"), ("./tessctl harden status", "allow"),
    ("echo run tessctl harden off later", "allow"),
    ("sudo chflags noschg .claude/settings.json", "deny"), ("sudo chattr -i tessctl", "deny"),
    ("chattr -i .tess/tess.lock", "deny"),
])
def test_the_gate_keeps_harden_for_the_operator(gate_proj, cmd, want, monkeypatch):  # noqa: F811
    monkeypatch.setenv("HOME", str(gate_proj[1]))
    monkeypatch.delenv("TESS_CONSULT_DEPTH", raising=False)
    got = _gate_all(gate_proj, cmd)
    assert got == ((want,) * 3), (cmd, got)


def test_docs_name_the_undo_path():
    sec = (Path(__file__).resolve().parent.parent / "SECURITY.md").read_text(encoding="utf-8")
    assert "tessctl harden off" in sec and "chflags -R noschg" in sec and "chattr -R -i" in sec
