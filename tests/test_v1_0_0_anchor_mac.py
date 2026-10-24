"""1.0.0 (section 2, operator decision 22 Oct): the anchor record is MAC-signed.

anchor.json (~/.config/tess/projects/<id>/anchor.json) holds the approved
hash of every safety file. Before this, an edited record (a hash swapped to
match a changed gate) was trusted as written. Now it carries an HMAC-SHA256
over its canonical JSON under the per-machine operator key
(~/.config/tess/operator/key, created by the first anchor write), and the
launcher and tessctl stop when:

  * the record is edited, or its "mac" is removed or malformed;
  * the record names another project (copied into this project's folder);
  * it was signed with another key (copied from another computer, or the
    key was replaced), or the key cannot be read.

`tessctl anchor accept` (and every other anchor write) signs a fresh record.
Every stop below passes on c80f6a3, which has no MAC.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from fixtures.anchor import real_anchor  # noqa: F401 — fixture
from test_v1_enforcement_anchor import chain  # noqa: F401 — fixture (its own proj)
from test_v1_r7_engine import HAS_GIT, L, anchored, proj  # noqa: F401 — fixtures

pytestmark = pytest.mark.skipif(not HAS_GIT, reason="needs git")


def _where(engine, root):
    return Path(engine._anchor_state(root).where)


def _edit(path, change):
    doc = json.loads(path.read_text())
    change(doc)
    path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")


def _launcher_stops(root):
    with pytest.raises(L.AnchorError) as exc:
        L.anchor_check(root)
    return exc.value


def test_the_same_mac_in_launcher_and_engine(engine):
    key = os.urandom(32)
    doc = {"format": "tess-enforcement-anchor/1", "project_id": "a" * 40, "files": {"x": {"sha256": "1"}},
           "written_at": "2026-10-24T00:00:00Z"}
    assert L.anchor_record_mac(key, doc) == engine.anchor_record_mac(key, doc)
    assert L.ANCHOR_MAC_DOMAIN == engine.ANCHOR_MAC_DOMAIN
    assert L.ANCHOR_EDITED == engine.ANCHOR_EDITED
    assert engine.anchor_record_mac(key, dict(doc, mac="x")) == engine.anchor_record_mac(key, doc)
    assert engine.anchor_record_mac(os.urandom(32), doc) != engine.anchor_record_mac(key, doc)


def test_a_written_record_is_signed_and_the_key_is_private(anchored, engine):
    path = _where(engine, anchored)
    doc = json.loads(path.read_text())
    assert doc["mac"].startswith("hmac-sha256:")
    key = engine._operator_key_dir() / "key"
    assert stat.S_IMODE(os.lstat(key).st_mode) == 0o600
    assert stat.S_IMODE(os.lstat(key.parent).st_mode) == 0o700
    assert L.anchor_check(anchored) is not None
    assert engine._anchor_state(anchored).state == "ok"


@pytest.mark.parametrize("change", [
    pytest.param(lambda d: d["files"][".claude/hooks/tess-gate.py"].update(sha256="0" * 64), id="hash"),
    pytest.param(lambda d: d["files"].pop(".claude/hooks/tess-gate.py"), id="drop-file"),
    pytest.param(lambda d: d.update(source="install"), id="other-field"),
    pytest.param(lambda d: d.pop("mac"), id="no-mac"),
    pytest.param(lambda d: d.update(mac="hmac-sha256:" + "0" * 64), id="wrong-mac"),
    pytest.param(lambda d: d.update(mac=3), id="mac-not-text"),
])
def test_an_edited_record_stops_tess(anchored, engine, change):
    path = _where(engine, anchored)
    _edit(path, change)
    err = _launcher_stops(anchored)
    assert str(err) == L.ANCHOR_EDITED
    st = engine._anchor_state(anchored)
    assert st.state == "lost" and st.edited
    assert engine._anchor_findings(anchored)[0] == engine.ANCHOR_EDITED
    with pytest.raises(SystemExit):
        engine._anchor_refuse_unless_clean(anchored, "update")


def test_a_record_for_another_project_stops_tess(anchored, engine):
    """A genuine signed record copied over this project's record: the MAC
    verifies, but it names another project."""
    path = _where(engine, anchored)
    doc = json.loads(path.read_text())
    doc["project_id"] = "b" * 40
    doc.pop("mac")
    path.write_bytes(engine._anchor_record_bytes(anchored, doc))
    assert "different project" in _launcher_stops(anchored).problems[0]
    assert engine._anchor_state(anchored).edited


def test_another_key_or_no_key_stops_tess(anchored, engine):
    key = engine._operator_key_dir() / "key"
    original = key.read_bytes()
    try:
        key.write_bytes(os.urandom(32))
        assert "does not match" in _launcher_stops(anchored).problems[0]
        assert engine._anchor_state(anchored).edited
        key.unlink()
        assert "cannot be used" in _launcher_stops(anchored).problems[0]
        assert engine._anchor_state(anchored).edited
        key.write_bytes(original)
        os.chmod(key, 0o644)
        assert "cannot be used" in _launcher_stops(anchored).problems[0]
    finally:
        if key.exists():
            os.chmod(key, 0o600)
        key.write_bytes(original)
        os.chmod(key, 0o600)
    assert L.anchor_check(anchored) is not None


def test_accept_signs_a_fresh_record(anchored, engine):
    path = _where(engine, anchored)
    _edit(path, lambda d: d.pop("mac"))
    assert engine._anchor_state(anchored).edited
    engine._anchor_write(anchored, "accept")
    assert engine._anchor_state(anchored).state == "ok"
    assert L.anchor_check(anchored) is not None


def test_the_real_hook_stops_on_an_edited_record(request):
    """End to end through the real Claude Code hook command (run-pinned.py)."""
    from test_v1_enforcement_anchor import _claude, _tessctl
    root, _ = request.getfixturevalue("chain")
    path = request.getfixturevalue("real_anchor")(root)
    assert _claude(root, "ls")[0:2] == (0, None)
    _edit(path, lambda d: d.update(source="hand-edited"))
    rc, _, err = _claude(root, "ls")
    assert rc == 2 and "not signed by this computer's operator key" in err
    st = _tessctl(root, "anchor", "status")
    assert st.returncode == 1 and "not signed" in st.stdout
