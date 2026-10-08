"""Brain key directory comes from the OS user record, not $HOME / $XDG_CONFIG_HOME.

v1.0.0 security review round 3, N-2 (integrator follow-up to #222): tessctl
already finds the operator key under pwd.getpwuid(os.getuid()).pw_dir. The
brain provenance key and the per-project external ledger (extstate.py, which
also holds claims and the outbox) now do the same, so a command run with
HOME=/tmp/x or XDG_CONFIG_HOME=/tmp/x cannot make the brain mint or verify
attestations with a key an agent controls.

TESS_BRAIN_PROVENANCE_DIR stays as the test suite's override: the
tests/fixtures/fake_os_home sitecustomize cannot reach brain subprocesses,
which relaunch with `python3 -I` (PYTHONPATH ignored), so without it those
tests would write into the operator's real ~/.config. The gate denies every
shell command that names it (tests/test_v1_r2_security.py).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "brain"))
from brainlib import config, extstate, provenance  # noqa: E402

pwd = pytest.importorskip("pwd")
FAKE_OS_HOME_SITE = ROOT / "tests" / "fixtures" / "fake_os_home"


@pytest.fixture
def hostile_env(tmp_path, monkeypatch):
    """No test override; HOME and XDG_CONFIG_HOME point at attacker folders."""
    monkeypatch.delenv(provenance.KEY_ENV, raising=False)
    evil_home, evil_xdg = tmp_path / "evil-home", tmp_path / "evil-xdg"
    evil_home.mkdir()
    evil_xdg.mkdir()
    monkeypatch.setenv("HOME", str(evil_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(evil_xdg))
    return evil_home, evil_xdg


@pytest.fixture
def os_home(tmp_path, monkeypatch):
    """Fake the OS user record's home for this process only."""
    home = tmp_path / "os-home"
    home.mkdir()
    real = pwd.getpwuid

    def fake(uid):
        rec = real(uid)
        return pwd.struct_passwd((rec.pw_name, rec.pw_passwd, rec.pw_uid, rec.pw_gid,
                                  rec.pw_gecos, str(home), rec.pw_shell))
    monkeypatch.setattr(pwd, "getpwuid", fake)
    return home


def test_key_dir_is_under_the_real_os_record_home(hostile_env):
    real_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    assert provenance.key_dir() == real_home / ".config" / "tess" / "brain"


def test_key_dir_ignores_home_and_xdg_config_home(hostile_env, os_home):
    evil_home, evil_xdg = hostile_env
    d = provenance.key_dir()
    assert d == os_home / ".config" / "tess" / "brain"
    for evil in (evil_home, evil_xdg):
        assert not str(d).startswith(str(evil))


def test_external_ledger_follows_the_os_record_home(hostile_env, os_home, tmp_path):
    evil_home, evil_xdg = hostile_env
    inst = tmp_path / "instance"
    inst.mkdir()
    (os_home / ".config" / "tess" / "brain").mkdir(parents=True, mode=0o700)  # as key() makes it
    d = extstate.project_dir(SimpleNamespace(root=inst))
    assert d is not None and d.is_dir()
    assert d.parent == os_home / ".config" / "tess" / "brain" / "projects"
    assert not any(evil_home.iterdir()) and not any(evil_xdg.iterdir())


def test_brain_subprocess_ignores_home_and_xdg(tmp_path):
    """A separate interpreter sees the same answer: env overrides do not move the key."""
    fake_home = tmp_path / "os-home"
    fake_home.mkdir()
    env = {k: v for k, v in os.environ.items() if k != provenance.KEY_ENV}
    env.update(HOME=str(tmp_path / "evil-home"), XDG_CONFIG_HOME=str(tmp_path / "evil-xdg"),
               TESS_TEST_OS_HOME=str(fake_home),
               PYTHONPATH=os.pathsep.join([str(FAKE_OS_HOME_SITE), str(ROOT / "scripts" / "brain")]))
    out = subprocess.run([sys.executable, "-B", "-c",
                          "from brainlib import provenance; print(provenance.key_dir())"],
                         env=env, capture_output=True, text=True, timeout=60, check=True)
    assert Path(out.stdout.strip()) == fake_home / ".config" / "tess" / "brain"


def test_no_user_database_falls_back_to_path_home(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "pwd", None)  # `import pwd` raises ImportError
    monkeypatch.setenv("HOME", str(tmp_path))
    assert config.os_user_home() == Path.home() == tmp_path


def test_test_override_still_wins_and_is_named_in_the_gate_deny_list(monkeypatch, tmp_path):
    monkeypatch.setenv(provenance.KEY_ENV, str(tmp_path / "k"))
    assert provenance.key_dir() == tmp_path / "k"
    gate = (ROOT / ".claude" / "hooks" / "tess-gate.py").read_text(encoding="utf-8")
    assert "TESS_BRAIN_PROVENANCE_DIR" in gate.split("_KEY_TEXT = re.compile(", 1)[1].split(")\n", 1)[0]
