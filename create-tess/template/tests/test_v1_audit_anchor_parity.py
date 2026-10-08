"""v1.0 security audit, integration: `tessctl doctor`, `verify` and `anchor
status` agree with run-pinned.py about a hidden anchor store.

Writer D made run-pinned.py list an anchored checkout in
<common git dir>/info/tess-anchored the first time a hook finds its anchor, and
stop (with a "put it back / anchor accept" message) when that checkout's anchor
store later cannot be found (`mv ~/.config ~/.config.off`, `chmod 000
~/.config`). tessctl still read that case as "anchor: none" and doctor passed.
These tests fail on the merged tree before the parity fix and pass after it.

The OS home is a temp folder (tests/fixtures/os_home.py); the real
~/.config/tess is never touched.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fixtures.anchor import real_anchor  # noqa: F401  (fixture)
from fixtures.os_home import use_os_home
from test_codex_gate import HAS_GIT, proj  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not HAS_GIT, reason="needs git")

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / ".claude" / "hooks" / "run-pinned.py"
HIDDEN = "put it back"


def _launcher():
    spec = importlib.util.spec_from_file_location("run_pinned_anchor_parity", str(LAUNCHER))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tessctl(root, *args):
    return subprocess.run([sys.executable, "-I", "-B", str(root / ".tess/bin/tessctl"), *args],
                          cwd=str(root), capture_output=True, text=True,
                          env={**os.environ, "TESS_ROOT": str(root)}, timeout=300)


@pytest.fixture
def anchored(proj, tmp_path, monkeypatch, real_anchor):  # noqa: F811
    home = tmp_path / "os-home"
    home.mkdir()
    use_os_home(monkeypatch, home)
    real_anchor(proj)
    rp = _launcher()
    assert rp.anchor_check(proj) is not None  # a hook ran: the checkout is listed
    assert rp.anchor_seen(proj)
    return proj, home, rp


def test_status_and_doctor_fail_when_the_anchor_store_is_hidden(anchored):
    root, home, rp = anchored
    (home / ".config").rename(home / ".config.off")  # `mv ~/.config ~/.config.off`
    with pytest.raises(rp.AnchorError) as exc:
        rp.anchor_check(root)
    launcher_says = str(exc.value)

    st = _tessctl(root, "anchor", "status")
    assert st.returncode == 1, st.stdout + st.stderr
    assert "anchor: none" not in st.stdout
    assert "anchor: FAIL" in st.stdout and launcher_says in st.stdout, st.stdout
    assert HIDDEN in st.stdout and "tessctl anchor accept" in st.stdout

    doc = _tessctl(root, "doctor")
    assert doc.returncode == 1, (doc.stdout[-2000:], doc.stderr[-2000:])
    assert "doctor: FAIL" in doc.stdout and launcher_says in doc.stdout

    ver = _tessctl(root, "verify")
    assert ver.returncode == 1 and "ANCHOR" in ver.stdout and HIDDEN in ver.stdout


def test_an_unreachable_anchor_store_is_a_failure_not_none(anchored):
    root, home, rp = anchored
    os.chmod(str(home / ".config"), 0)  # `chmod 000 ~/.config`
    try:
        st = _tessctl(root, "anchor", "status")
        doc = _tessctl(root, "doctor")
    finally:
        os.chmod(str(home / ".config"), 0o700)
    assert st.returncode == 1 and "anchor: FAIL" in st.stdout, st.stdout + st.stderr
    assert "anchor accept" in st.stdout
    assert doc.returncode == 1 and "doctor: FAIL" in doc.stdout


def test_anchor_init_does_not_start_over_when_the_store_is_hidden(anchored):
    root, home, _rp = anchored
    (home / ".config").rename(home / ".config.off")
    r = _tessctl(root, "anchor", "init")
    assert r.returncode != 0 and "refused" in r.stderr and HIDDEN in r.stderr, r.stdout + r.stderr
    assert not (home / ".config" / "tess" / "projects").exists(), "nothing was recorded"


def test_a_checkout_that_was_never_anchored_still_reads_as_none(proj, tmp_path, monkeypatch):  # noqa: F811
    use_os_home(monkeypatch, tmp_path / "os-home")
    assert not (proj / ".git/info/tess-anchored").exists()
    st = _tessctl(proj, "anchor", "status")
    assert st.returncode == 0 and "anchor: none" in st.stdout, st.stdout + st.stderr


def test_the_marker_of_another_checkout_does_not_count(anchored):
    """The marker lists checkouts by path key: a worktree-shared marker that
    names another path leaves this one reading as never anchored."""
    root, home, rp = anchored
    marker = root / ".git/info/tess-anchored"
    marker.write_text("0" * 64 + "\n")
    (home / ".config").rename(home / ".config.off")
    st = _tessctl(root, "anchor", "status")
    assert st.returncode == 0 and "anchor: none" in st.stdout, st.stdout + st.stderr
