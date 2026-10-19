"""v1.0.x QA (Quinn GAP-1): `.claude/settings.local.json` is an anchored file.

`{"disableAllHooks": true}` there switches every Claude Code hook off, Tess's
gate included, and before this change only a person running `tessctl doctor`
noticed. It is the operator's own file and is normally absent, and Claude Code
writes "don't ask again" answers to it, so it is anchored by its enforcement
content: the JSON object without the permission-rule lists (allow, ask, deny,
additionalDirectories), with a missing file counted as `{}`.

  * absent at anchor time: recorded as absent; creating it with any other key
    is a change (hooks stop, git hooks refuse, doctor / verify / status fail);
  * permission rules come and go freely, and deleting a file that held only
    permission rules is not a change;
  * a symlink or a folder in its place is a change;
  * `tessctl restore` puts back the approved keys and keeps the operator's
    current permission rules;
  * an anchor written by an earlier release gains the record on the next
    verified update (ANCHOR_FIRST_RECORD), as the manifest did.
"""
from __future__ import annotations

import json
import os
import shutil

import pytest

from fixtures.anchor import real_anchor  # noqa: F401 — fixture
from test_v1_enforcement_anchor import chain  # noqa: F401 — fixture (its own proj)
from test_v1_r7_engine import HAS_GIT, L, MANIFEST, anchored, proj  # noqa: F401 — fixtures

LOCAL = ".claude/settings.local.json"
pytestmark = pytest.mark.skipif(not HAS_GIT, reason="needs git")


def _write(root, doc):
    path = root / LOCAL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc if isinstance(doc, str) else json.dumps(doc))


def _launcher_problems(root):
    return L.anchor_problems(root, L.anchor_locate(root)[0])


def _state(engine, root):
    st = engine._anchor_state(root)
    assert st.state == ("ok" if not st.problems else "mismatch")
    return st.state, st.problems


def test_lists_and_digest_match_in_launcher_and_engine(engine):
    assert LOCAL in L.ANCHOR_FILES and LOCAL in engine.ANCHOR_FILES
    assert LOCAL in engine.ANCHOR_FIRST_RECORD
    assert L.ANCHOR_LOCAL_PERMISSION_KEYS == engine.ANCHOR_LOCAL_PERMISSION_KEYS
    for data in (None, b"{}", b'{"disableAllHooks": true}', b"not json", b"[1]",
                 b'{"permissions": {"allow": ["Bash(ls)"]}}', b'{"permissions": {"defaultMode": "x"}}',
                 "{\"env\": {\"A\": \"é\"}}".encode()):
        assert L.anchor_local_settings_digest(data) == engine.anchor_local_settings_digest(data), data


def test_digest_ignores_only_the_permission_rule_lists(engine):
    d = engine.anchor_local_settings_digest
    empty = d(None)
    assert d(b"{}") == empty
    assert d(b'{"permissions": {"allow": ["Bash(ls)"], "deny": [], "ask": ["x"], '
             b'"additionalDirectories": ["/tmp"]}}') == empty
    for other in (b'{"disableAllHooks": true}', b'{"hooks": {}}', b'{"env": {"A": "1"}}',
                  b'{"permissions": {"defaultMode": "bypassPermissions"}}', b"", b"null", b"{"):
        assert d(other) != empty, other


def test_absent_file_is_recorded_and_its_creation_stops_tess(anchored, engine):
    root = anchored
    rec = engine._anchor_state(root).doc["files"][LOCAL]
    assert rec.get("absent") is True
    assert _state(engine, root) == ("ok", [])
    _write(root, {"disableAllHooks": True})
    assert f"{LOCAL} has changed" in _launcher_problems(root)
    with pytest.raises(L.AnchorError):
        L.anchor_check(root)
    assert engine._anchor_state(root).state == "mismatch"
    assert any(LOCAL in line for line in engine._anchor_findings(root))
    with pytest.raises(SystemExit):
        engine._anchor_git_hook_check(root, "commit")


def test_permission_rules_are_the_operators_own(anchored, engine):
    root = anchored
    _write(root, {"permissions": {"allow": ["Bash(npm test:*)"], "deny": ["Bash(curl:*)"]}})
    assert _launcher_problems(root) == [] and _state(engine, root) == ("ok", [])
    _write(root, {"permissions": {"allow": ["Bash(npm test:*)", "Bash(ls:*)"]}})
    assert _launcher_problems(root) == []
    (root / LOCAL).unlink()
    assert _launcher_problems(root) == [] and _state(engine, root) == ("ok", [])


@pytest.mark.parametrize("doc", [
    {"disableAllHooks": True},
    {"hooks": {"PreToolUse": []}},
    {"permissions": {"allow": ["Bash(*)"], "defaultMode": "bypassPermissions"}},
    {"env": {"PATH": "/tmp/evil"}},
    "{ not json",
    "[]",
])
def test_any_other_content_is_a_change(anchored, engine, doc):
    root = anchored
    _write(root, doc)
    assert f"{LOCAL} has changed" in _launcher_problems(root)
    assert engine._anchor_state(root).state == "mismatch"


def test_a_symlink_or_folder_in_its_place_is_a_change(anchored, engine, tmp_path):
    root = anchored
    target = tmp_path / "elsewhere.json"
    target.write_text("{}")
    (root / LOCAL).symlink_to(target)
    assert any("not a regular file" in p for p in _launcher_problems(root))
    assert engine._anchor_state(root).state == "mismatch"
    (root / LOCAL).unlink()
    (root / LOCAL).mkdir()
    assert any("not a regular file" in p for p in _launcher_problems(root))
    (root / LOCAL).rmdir()
    assert _launcher_problems(root) == []


def test_a_present_file_is_anchored_by_content(proj, engine, monkeypatch):  # noqa: F811
    _write(proj, {"env": {"A": "1"}, "permissions": {"allow": ["Bash(ls)"]}})
    monkeypatch.setattr(engine, "_RELEASE_WRITES", {})
    where = engine._anchor_write(proj, "test")
    try:
        rec = engine._anchor_state(proj).doc["files"][LOCAL]
        assert "absent" not in rec and rec.get("blob")
        _write(proj, {"env": {"A": "1"}, "permissions": {"allow": ["Bash(ls)", "Bash(pwd)"]}})
        assert _launcher_problems(proj) == []
        _write(proj, {"env": {"A": "2"}})
        assert f"{LOCAL} has changed" in _launcher_problems(proj)
        (proj / LOCAL).unlink()  # removed while it held more than permission rules
        assert f"{LOCAL} has changed" in _launcher_problems(proj)
        assert engine._anchor_state(proj).state == "mismatch"
    finally:
        shutil.rmtree(where.parent, ignore_errors=True)


def test_restore_keeps_the_operators_permission_rules(anchored, engine):
    root = anchored
    _write(root, {"disableAllHooks": True, "permissions": {"allow": ["Bash(ls:*)"]}})
    assert engine._anchor_restore(root) == []
    assert json.loads((root / LOCAL).read_text()) == {"permissions": {"allow": ["Bash(ls:*)"]}}
    assert _state(engine, root) == ("ok", []) and _launcher_problems(root) == []
    _write(root, {"disableAllHooks": True})
    assert engine._anchor_restore(root) == []
    assert not (root / LOCAL).exists(), "the approved state is no file"
    assert _state(engine, root) == ("ok", [])


def test_restore_refuses_a_symlink_in_the_way(anchored, engine, tmp_path):
    root = anchored
    target = tmp_path / "x.json"
    target.write_text("{}")
    (root / LOCAL).symlink_to(target)
    failed = engine._anchor_restore(root)
    assert failed and LOCAL in failed[0]
    assert target.read_text() == "{}"


def test_anchor_accept_refuses_to_record_a_symlink(proj, engine):  # noqa: F811
    target = proj.parent / "x.json"
    target.write_text("{}")
    (proj / LOCAL).symlink_to(target)
    with pytest.raises(ValueError):
        engine._anchor_write(proj, "test")


def test_an_older_anchor_records_it_on_the_next_verified_update(anchored, engine):
    root = anchored
    st = engine._anchor_state(root)
    doc = dict(st.doc)
    doc["files"] = {k: v for k, v in doc["files"].items() if k != LOCAL}
    engine._anchor_write_private(type(root)(st.where), (json.dumps(doc) + "\n").encode())
    _write(root, {"disableAllHooks": True})
    assert engine._anchor_state(root).state == "ok", "an older anchor has no record of it"
    os.unlink(root / LOCAL)
    engine._anchor_after_release(root, "update")
    rec = engine._anchor_state(root).doc["files"][LOCAL]
    assert rec.get("absent") is True
    _write(root, {"disableAllHooks": True})
    assert engine._anchor_state(root).state == "mismatch"


def test_update_never_reblesses_a_local_settings_change(anchored, engine):
    root = anchored
    _write(root, {"disableAllHooks": True})
    with pytest.raises(SystemExit) as exc:
        engine._anchor_after_release(root, "update")
    assert LOCAL in str(exc.value.code) and "did NOT record" in str(exc.value.code)


def test_manifest_still_anchored_alongside(anchored, engine):
    assert MANIFEST in engine._anchor_state(anchored).doc["files"]


def test_the_real_hooks_stop_on_it_and_not_on_permission_rules(request):
    """End to end through the real Claude Code hook command (run-pinned.py)."""
    from test_v1_enforcement_anchor import STOP, _claude, _tessctl
    root, _ = request.getfixturevalue("chain")
    request.getfixturevalue("real_anchor")(root)
    assert _claude(root, "ls")[0:2] == (0, None)
    _write(root, {"permissions": {"allow": ["Bash(ls:*)"]}})
    assert _claude(root, "ls")[0:2] == (0, None), "a permission rule is the operator's own"
    _write(root, {"disableAllHooks": True, "permissions": {"allow": ["Bash(ls:*)"]}})
    rc, _, err = _claude(root, "ls")
    assert rc == 2 and STOP in err
    st = _tessctl(root, "anchor", "status")
    assert st.returncode == 1 and f"{LOCAL} has changed" in st.stdout
    r = _tessctl(root, "restore")
    assert "safety files: back to the approved copies" in r.stdout, r.stdout + r.stderr
    assert json.loads((root / LOCAL).read_text()) == {"permissions": {"allow": ["Bash(ls:*)"]}}
    assert _claude(root, "ls")[0:2] == (0, None)
