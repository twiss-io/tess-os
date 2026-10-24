"""1.0.0 (section 2, operator decision 22 Oct): `.mcp.json` is anchored.

`.mcp.json` says what each project MCP server runs (command, arguments, URL,
environment). Claude Code records an approval by server NAME in
settings.local.json, so before this a changed definition behind an approved
name was never seen. Now:

  * it is in ANCHOR_FILES (launcher and engine, same list) and
    ANCHOR_FIRST_RECORD; its absence is a recorded state;
  * creating, changing or removing it, or a symlink or folder in its place,
    stops Tess (launcher, engine, git hooks) until `tessctl anchor accept`;
  * Tess keeps NO copy of it outside the project (it can hold API keys):
    no blob is written, `anchor accept` shows server names, transports and
    programs and never a value, and `restore` says it cannot put it back;
  * the gate refuses an agent's write to it.

Every stop case below passes c80f6a3's anchor (the file was not checked).
"""
from __future__ import annotations

import json
import os

import pytest

from test_v1_r7_engine import HAS_GIT, L, _level, anchored, proj  # noqa: F401 — fixtures

MCP = ".mcp.json"
# A marker standing in for a credential: it must never leave the project file.
HIDDEN = "MARKER" + "-unseen-" + "value-" + "7f3a9c"
SERVER = {"mcpServers": {"docs": {"command": "/usr/local/bin/docs-mcp", "args": ["--opt", HIDDEN],
                                  "env": {"DOCS_OPT": HIDDEN}},
                         "web": {"type": "http", "url": "https://mcp.example.com/x?q=" + HIDDEN,
                                 "headers": {"X-Note": HIDDEN}}}}
pytestmark = pytest.mark.skipif(not HAS_GIT, reason="needs git")


def _write(root, doc):
    (root / MCP).write_text(doc if isinstance(doc, str) else json.dumps(doc))


def _launcher(root):
    return L.anchor_problems(root, L.anchor_locate(root)[0])


def test_lists_match_in_launcher_and_engine(engine):
    assert MCP in L.ANCHOR_FILES and MCP in engine.ANCHOR_FILES
    assert MCP in engine.ANCHOR_FIRST_RECORD
    assert L.ANCHOR_MCP_ABSENT == engine.ANCHOR_MCP_ABSENT
    assert tuple(L.ANCHOR_MAY_BE_ABSENT) == tuple(engine.ANCHOR_MAY_BE_ABSENT)


def test_absent_is_recorded_and_creation_stops_tess(anchored, engine):
    root = anchored
    rec = engine._anchor_state(root).doc["files"][MCP]
    assert rec == {"sha256": engine.ANCHOR_MCP_ABSENT, "absent": True}
    assert _launcher(root) == []
    _write(root, SERVER)
    assert f"{MCP} has changed" in _launcher(root)
    with pytest.raises(L.AnchorError):
        L.anchor_check(root)
    assert engine._anchor_state(root).state == "mismatch"
    with pytest.raises(SystemExit):
        engine._anchor_git_hook_check(root, "commit")


def test_present_file_is_anchored_without_a_copy(proj, engine, monkeypatch):  # noqa: F811
    _write(proj, SERVER)
    monkeypatch.setattr(engine, "_RELEASE_WRITES", {})
    where = engine._anchor_write(proj, "test")
    try:
        rec = engine._anchor_state(proj).doc["files"][MCP]
        assert rec.get("no_copy") is True and "blob" not in rec
        blobs = engine._anchor_tess_dir() / "anchor-blobs"
        for b in blobs.iterdir():
            assert HIDDEN.encode() not in b.read_bytes(), "a copy of .mcp.json was kept"
        assert HIDDEN not in where.read_text()
        assert _launcher(proj) == [] and engine._anchor_state(proj).state == "ok"
        doc = json.loads(json.dumps(SERVER))
        doc["mcpServers"]["docs"]["command"] = "/tmp/evil"
        _write(proj, doc)  # same server name, different program
        assert f"{MCP} has changed" in _launcher(proj)
        (proj / MCP).unlink()
        assert f"{MCP} has changed" in _launcher(proj)
        assert engine._anchor_state(proj).state == "mismatch"
    finally:
        os.unlink(where)


def test_a_symlink_or_folder_in_its_place_is_a_change(anchored, engine, tmp_path):
    root = anchored
    target = tmp_path / "m.json"
    target.write_text("{}")
    (root / MCP).symlink_to(target)
    assert any("not a regular file" in p for p in _launcher(root))
    assert engine._anchor_state(root).state == "mismatch"
    with pytest.raises(ValueError):
        engine._anchor_write(root, "test")
    (root / MCP).unlink()
    (root / MCP).mkdir()
    assert any("not a regular file" in p for p in _launcher(root))
    (root / MCP).rmdir()
    assert _launcher(root) == []


def test_restore_does_not_rewrite_or_delete_it(anchored, engine):
    root = anchored
    _write(root, SERVER)
    failed = engine._anchor_restore(root)
    assert failed and MCP in failed[0] and "no copy" in failed[0]
    assert json.loads((root / MCP).read_text()) == SERVER


def test_accept_shows_servers_but_never_values(anchored, engine, capsys):
    root = anchored
    _write(root, SERVER)
    engine._anchor_show_changes(root, engine._anchor_state(root))
    out = capsys.readouterr().out
    assert MCP in out and '"docs"' in out and '"web"' in out
    assert "docs-mcp" in out and "mcp.example.com" in out and "(not shown)" in out
    assert HIDDEN not in out and "MARKER" not in out, out


def test_server_summary_handles_bad_text(engine):
    assert engine.anchor_mcp_servers(None) == []
    assert engine.anchor_mcp_servers(b"not json") is None
    assert engine.anchor_mcp_servers(b"[]") is None
    assert engine.anchor_mcp_servers(b'{"mcpServers": 3}') == []
    assert engine.anchor_mcp_servers(b'{"mcpServers": {"a": {"url": "http://[bad"}}}')[0][0] == "a"


def test_an_older_anchor_records_it_on_the_next_verified_update(anchored, engine, capsys):
    root = anchored
    st = engine._anchor_state(root)
    doc = dict(st.doc)
    doc["files"] = {k: v for k, v in doc["files"].items() if k != MCP}
    engine._anchor_write_private(type(root)(st.where), engine._anchor_record_bytes(root, doc))
    _write(root, SERVER)
    assert engine._anchor_state(root).state == "ok", "an older anchor has no record of it"
    engine._anchor_after_release(root, "update")
    out = capsys.readouterr().out
    assert "WARNING" in out and '"docs"' in out and HIDDEN not in out, out
    assert engine._anchor_state(root).doc["files"][MCP].get("no_copy") is True
    _write(root, {"mcpServers": {}})
    assert engine._anchor_state(root).state == "mismatch"


def test_update_never_reblesses_a_change(anchored, engine):
    root = anchored
    _write(root, SERVER)
    with pytest.raises(SystemExit) as exc:
        engine._anchor_after_release(root, "update")
    assert MCP in str(exc.value.code) and "did NOT record" in str(exc.value.code)


@pytest.mark.parametrize("tool,tin", [
    ("Write", {"file_path": MCP, "content": "{}"}),
    ("Edit", {"file_path": MCP, "old_string": "a", "new_string": "b"}),
    ("Bash", {"command": "echo '{}' > .mcp.json"}),
    ("Bash", {"command": "cp /tmp/x.json .mcp.json"}),
    ("Bash", {"command": "rm -f .mcp.json"}),
])
def test_the_gate_refuses_agent_writes(proj, tool, tin):  # noqa: F811
    if "file_path" in tin:
        tin = dict(tin, file_path=str(proj / MCP))
    assert _level(proj, tool, tin) == "deny"
    assert _level(proj, tool, tin, codex=True) == "deny"


def test_reading_it_stays_allowed(proj):  # noqa: F811
    _write(proj, SERVER)
    assert _level(proj, "Read", {"file_path": str(proj / MCP)}) == "allow"


# ---------------------------------------------------------------- review fix (phase 2)
# Claude Code picks the transport from `type` only: no type is stdio (it runs
# `command`), a url with no type is skipped (code.claude.com/docs/en/mcp,
# checked 24 Oct 2026). The summary showed a url host whenever `url` was set.
def _one(engine, spec):
    got = engine.anchor_mcp_servers(json.dumps({"mcpServers": {"s": spec}}).encode())
    assert len(got) == 1
    return got[0]


def test_review_url_and_command_without_type_shows_the_command_it_runs(engine):
    """Failed on 451a5e6: shown as http with only the url host."""
    _n, kind, what, warns = _one(engine, {"url": "https://ok.example/mcp", "command": "/tmp/evil.sh"})
    assert kind == "stdio" and "/tmp/evil.sh" in what
    assert any("both a command and a url" in w and "RUNS the command" in w for w in warns)


def test_review_url_without_type_is_flagged_as_skipped(engine):
    _n, kind, _what, warns = _one(engine, {"url": "https://x.example"})
    assert kind == "stdio" and any("skips it" in w for w in warns)


def test_review_type_that_contradicts_the_fields_warns(engine):
    assert any("names no url" in w for w in _one(engine, {"type": "http", "command": "/bin/x"})[3])
    assert any("names no command" in w for w in _one(engine, {"type": "stdio", "url": "https://x.example"})[3])
    assert any("not one Claude Code knows" in w for w in _one(engine, {"type": "zz", "command": "x"})[3])
    assert _one(engine, {"type": "streamable-http", "url": "https://x.example"})[1] == "http"


@pytest.mark.parametrize("prog", ["bash", "/bin/sh", "node", "/usr/bin/python3", "npx", "uvx",
                                  "python3.12"])
def test_review_interpreters_are_flagged_with_the_full_path(engine, prog):
    _n, kind, what, warns = _one(engine, {"command": prog, "args": ["-c", "x"]})
    assert kind == "stdio" and f"runs {prog} " in what
    assert any("interpreter or package runner" in w for w in warns)


def test_review_first_argument_shown_only_when_not_a_secret(engine):
    assert 'first "@scope/server"' in _one(engine, {"command": "npx", "args": ["@scope/server", HIDDEN]})[2]
    for secretish in ("--token=abc", "--api-key", "a1b2c3d4e5f6g7h8i9j0k1", HIDDEN + " x"):
        what = _one(engine, {"command": "srv", "args": [secretish]})[2]
        assert "first not shown" in what and secretish not in what


def test_review_accept_prints_the_warnings(anchored, engine, capsys):
    root = anchored
    _write(root, {"mcpServers": {"x": {"url": "https://ok.example", "command": "/tmp/evil.sh"}}})
    engine._anchor_show_changes(root, engine._anchor_state(root))
    out = capsys.readouterr().out
    assert "/tmp/evil.sh" in out and "WARNING: it has both a command and a url" in out
