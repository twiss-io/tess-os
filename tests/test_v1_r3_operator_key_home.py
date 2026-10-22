"""v1.0.0 security review round 3, N-2: tessctl's operator key directory comes
from the OS user record, not $HOME / $XDG_CONFIG_HOME (split out of
tests/test_v1_policy_update_approval.py to keep that file under the size cap).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fixtures.os_home import operator_home  # noqa: F401 — autouse: fake OS-record home


def test_operator_key_ignores_home_and_xdg_config_home(engine, tmp_path, monkeypatch):
    """Round 3, N-2: `XDG_CONFIG_HOME=/tmp/x tessctl ...` (or a moved HOME) must
    not make tessctl read a key the agent planted. The key directory comes from
    the OS user record; the planted key is never read and nothing is created there."""
    proj, planted = tmp_path / "proj", tmp_path / "agent-cfg"
    proj.mkdir()
    (planted / "tess" / "operator").mkdir(parents=True, mode=0o700)
    (planted / "tess" / "operator" / "key").write_bytes(b"p" * 32)
    (planted / "tess" / "operator" / "key").chmod(0o600)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(planted))
    monkeypatch.setenv("HOME", str(planted))
    real_home = Path(os.environ["TESS_TEST_OS_HOME"])
    assert engine._operator_key_dir() == real_home / ".config" / "tess" / "operator"
    assert engine._operator_key(proj, create=False) == (None, "there is no operator key on this machine")
    key, why = engine._operator_key(proj, create=True)
    assert key is not None and key != b"p" * 32 and why == ""
    assert (real_home / ".config" / "tess" / "operator" / "key").read_bytes() == key
    assert (planted / "tess" / "operator" / "key").read_bytes() == b"p" * 32


def test_tessctl_subprocess_ignores_xdg_config_home(engine, tmp_path, monkeypatch):
    """The same through a real tessctl process (the pre-push gate path)."""
    planted = tmp_path / "agent-cfg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(planted))
    code = ("import importlib.machinery, importlib.util, sys; "
            "l = importlib.machinery.SourceFileLoader('t', sys.argv[1]); "
            "s = importlib.util.spec_from_loader('t', l); m = importlib.util.module_from_spec(s); "
            "l.exec_module(m); print(m._operator_key_dir())")
    from conftest import REPO_ROOT
    r = subprocess.run([sys.executable, "-c", code, str(REPO_ROOT / ".tess" / "bin" / "tessctl")],
                       capture_output=True, text=True, env=dict(os.environ))
    assert r.returncode == 0, r.stderr
    out = Path(r.stdout.strip())
    assert out == Path(os.environ["TESS_TEST_OS_HOME"]) / ".config" / "tess" / "operator"
    assert str(planted) not in r.stdout
