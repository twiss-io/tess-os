"""Shared test helper: a fake home in the OS user record (v1.0.0 round 3, N-2).

tessctl and the brain find their keys under pwd.getpwuid(os.getuid()).pw_dir
and ignore $HOME / $XDG_CONFIG_HOME, so tests move the home by faking the user
record: in-process by patching pwd.getpwuid, and in plain (non -I) python
subprocesses through tests/fixtures/fake_os_home/sitecustomize.py.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

FAKE_OS_HOME_SITE = Path(__file__).resolve().parent / "fake_os_home"


def use_os_home(monkeypatch, home: Path) -> None:
    """Point the OS user record's home at `home` for this process and for every
    tessctl subprocess (tests/fixtures/fake_os_home/sitecustomize.py). Round 3
    (N-2): tessctl ignores $HOME / $XDG_CONFIG_HOME for the operator key, so an
    environment variable no longer moves it."""
    import pwd
    monkeypatch.setenv("TESS_TEST_OS_HOME", str(home))
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(
        [str(FAKE_OS_HOME_SITE)] + [p for p in [os.environ.get("PYTHONPATH")] if p]))
    real = pwd.getpwuid

    def fake(uid):
        rec = real(uid)
        return pwd.struct_passwd((rec.pw_name, rec.pw_passwd, rec.pw_uid, rec.pw_gid,
                                  rec.pw_gecos, os.environ["TESS_TEST_OS_HOME"], rec.pw_shell))
    monkeypatch.setattr(pwd, "getpwuid", fake)


@pytest.fixture(autouse=True)
def operator_home(tmp_path_factory, monkeypatch):
    """Every test gets its own operator key location, never the real ~/.config."""
    home = tmp_path_factory.mktemp("os-home")  # outside every test project
    use_os_home(monkeypatch, home)
    return home / ".config"
