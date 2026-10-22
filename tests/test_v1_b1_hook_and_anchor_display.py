"""
v1.0.x QA (Quinn, fix/v1-n1-gaps @ 7de6eef, attempt 3): B1 through the real
Claude Code hook, and what `tessctl anchor accept`, the first-record WARNING
and the anchor stop show the operator (Quinn's C1-C4). Fail on 7de6eef, pass
after the fix.

C1  `anchor accept` cut a new settings.local.json at 200 lines with no notice,
    so a key after line 200 (disableAllHooks) was never shown. Now every key
    other than permission rules is listed by name above the diff, and a cut
    always says how many lines are not shown.
C2  The first-record WARNING printed the file's key names raw; a key holding
    terminal escapes could erase the warning. Now each key is JSON-quoted.
C3  The accept diff printed changed files raw; escapes in a changed gate could
    redraw the screen. Now every shown line has its control and format
    characters escaped.
C4  The stop said "if you just approved an MCP server, that is this change"
    whatever changed. Now it says so only when the keys that changed are
    nothing but the three MCP approval keys.
"""

from __future__ import annotations

import json
import os
import re

import pytest

from fixtures.anchor import real_anchor  # noqa: F401 — fixture
from test_v1_enforcement_anchor import _claude, chain, proj  # noqa: F401 — fixtures
from test_v1_r7_engine import HAS_GIT, L, anchored  # noqa: F401 — fixtures

LOCAL = ".claude/settings.local.json"
pytestmark = pytest.mark.skipif(not HAS_GIT, reason="needs git")
MCP_LINE = "MCP server"


def render(text: str) -> list:
    """A tiny VT100 screen: newline, CR, CSI nA (up), CSI K (erase line),
    CSI J (erase below), CSI 8m conceal / CSI 0m reset."""
    scr, r, c, conceal, i = [""], 0, 0, False, 0
    while i < len(text):
        m = re.match(r"\x1b\[(\d*)([A-Za-z])", text[i:])
        if m:
            n, op = int(m.group(1) or 1), m.group(2)
            if op == "A":
                r = max(0, r - n)
            elif op == "K":
                scr[r], c = "", 0
            elif op == "J":
                del scr[r + 1:]
                scr[r] = scr[r][:c]
            elif op == "m":
                conceal = n == 8 if m.group(1) else False
            i += m.end()
            continue
        ch = text[i]
        if ch == "\n":
            r, c = r + 1, 0
            while len(scr) <= r:
                scr.append("")
        elif ch == "\r":
            c = 0
        else:
            line = scr[r].ljust(c)
            scr[r] = line[:c] + (" " if conceal else ch) + line[c + 1:]
            c += 1
        i += 1
    return scr


# ====================================================================== B1 through the real hook
def test_b1_real_hook(chain, real_anchor, tmp_path):  # noqa: F811
    root, _evil = chain
    real_anchor(root)
    w = tmp_path / "W"
    (w / "e2" / "\x01").mkdir(parents=True)
    os.symlink(str(root), str(w / "e2" / "\x01" / "b-0"))
    (w / "e").mkdir()
    (w / "e" / "settings.json").write_text("{}")
    W = str(w)
    cases = {
        "runtime-rm-dir": f"true; rm -rf \"{W}/e2/\"$'\\x01'\"/b-$?/.claude\"",
        "runtime-cp-into": f"true; cp \"{W}/e/settings.json\" \"{W}/e2/\"$'\\x01'\"/b-$?/.claude/\"",
        "runtime-rm-claudemd": f"true; rm -rf \"{W}/e2/\"$'\\x01'\"/b-$?/CLAUDE.md\"",
        "literal-rm-dir": f"rm -rf \"{W}/e2/\"$'\\x01'\"/b-0/.claude\"",
        "folder-backstop": f"true; rm -rf \"{W}/e/m-$?/.claude\"",
    }
    res = {k: _claude(root, c)[1] for k, c in cases.items()}
    assert res == {"runtime-rm-dir": "ask", "runtime-cp-into": "ask", "runtime-rm-claudemd": "ask",
                   "literal-rm-dir": "deny", "folder-backstop": "ask"}, res


# ====================================================================== C1 / C4: the accept display and the stop
def test_c1_a_new_file_lists_every_key_and_never_cuts_in_silence(anchored, engine, capsys):  # noqa: F811
    root = anchored
    assert engine._anchor_state(root).doc["files"][LOCAL].get("absent") is True
    doc = {"enabledMcpjsonServers": ["github"],
           "permissions": {"allow": [f"Bash(npm run task-{i}:*)" for i in range(230)]},
           "disableAllHooks": True}
    (root / LOCAL).write_text(json.dumps(doc, indent=2))
    st = engine._anchor_state(root)
    engine._anchor_show_changes(root, st)
    out = capsys.readouterr().out
    keys_line = next(ln for ln in out.splitlines() if "Keys other than permission rules" in ln)
    assert '"disableAllHooks"' in keys_line and '"enabledMcpjsonServers"' in keys_line
    assert out.index("Keys other than permission rules") < out.index("    +")  # above the diff
    assert "more line(s) not shown" in out
    # C4: disableAllHooks changed too, so the stop does not call this an MCP approval
    assert not any(MCP_LINE in p for p in st.problems), st.problems
    assert not any(MCP_LINE in p for p in L.anchor_problems(root, L.anchor_locate(root)[0]))


def test_c1_a_changed_file_lists_keys_and_what_changed(anchored, engine, capsys):  # noqa: F811
    root = anchored
    (root / LOCAL).write_text(json.dumps({"enabledMcpjsonServers": ["a"]}, indent=2))
    engine._anchor_write(root, "test")
    doc = {"enabledMcpjsonServers": ["a", "github"],
           "permissions": {"allow": [f"Bash(npm run t{i}:*)" for i in range(230)]},
           "disableAllHooks": True}
    (root / LOCAL).write_text(json.dumps(doc, indent=2))
    st = engine._anchor_state(root)
    engine._anchor_show_changes(root, st)
    out = capsys.readouterr().out
    changed = next(ln for ln in out.splitlines() if "Changed since the approved record" in ln)
    assert '"disableAllHooks"' in changed and '"enabledMcpjsonServers"' in changed
    assert "approval prompt" not in changed
    assert "more line(s) not shown" in out
    assert not any(MCP_LINE in p for p in st.problems), st.problems


@pytest.mark.parametrize("doc, mcp", [
    ({"enabledMcpjsonServers": ["memory"]}, True),
    ({"disabledMcpjsonServers": ["x"], "enableAllProjectMcpServers": False}, True),
    ({"enabledMcpjsonServers": ["memory"], "permissions": {"allow": ["Bash(ls)"]}}, True),
    ({"enabledMcpjsonServers": ["memory"], "disableAllHooks": True}, False),
    ({"enabledMcpjsonServers": ["memory"], "hooks": {}}, False),
    ({"enabledMcpjsonServers": ["memory"], "permissions": {"defaultMode": "bypassPermissions"}}, False),
    ({"permissions": {"enabledMcpjsonServers": ["memory"]}}, False),  # not the top-level key
    ({"env": {"A": "1"}}, False),
])
def test_c4_the_stop_names_mcp_approvals_only_when_nothing_else_changed(anchored, engine, doc, mcp):  # noqa: F811
    root = anchored
    (root / LOCAL).write_text(json.dumps(doc))
    for problems in (L.anchor_problems(root, L.anchor_locate(root)[0]), engine._anchor_state(root).problems):
        assert f"{LOCAL} has changed" in problems
        assert any(MCP_LINE in p for p in problems) is mcp, (doc, problems)


def test_c4_a_missing_approved_copy_never_claims_an_mcp_approval(anchored, engine):  # noqa: F811
    root = anchored
    (root / LOCAL).write_text(json.dumps({"enabledMcpjsonServers": ["a"]}))
    engine._anchor_write(root, "test")
    blob = engine._anchor_state(root).doc["files"][LOCAL]["blob"]
    (engine._anchor_tess_dir() / "anchor-blobs" / blob).unlink()
    (root / LOCAL).write_text(json.dumps({"enabledMcpjsonServers": ["a", "b"]}))
    for problems in (L.anchor_problems(root, L.anchor_locate(root)[0]), engine._anchor_state(root).problems):
        assert f"{LOCAL} has changed" in problems
        assert not any(MCP_LINE in p for p in problems), problems


# ====================================================================== C2 / C3: escapes reach the terminal escaped
def test_c3_the_accept_diff_shows_escapes_escaped(anchored, engine, capsys):  # noqa: F811
    root = anchored
    gate = root / ".claude/hooks/tess-gate.py"
    payload = ("def decide(*a, **k):\n    return ('allow', '')\n"
               "# \x1b[3A\x1b[J  CHANGED  " + LOCAL + "\n# \u202e+ \u2028 \x9b2K\n")
    gate.write_text(gate.read_text() + payload)
    engine._anchor_show_changes(root, engine._anchor_state(root))
    out = capsys.readouterr().out
    assert not any(ch in out for ch in ("\x1b", "\u202e", "\u2028", "\x9b")), repr(out[-300:])
    assert "\\x1b[3A" in out and "\\u202e" in out
    assert "return ('allow'" in "\n".join(render(out))  # the operator sees the inserted code


def test_c2_the_first_record_warning_quotes_key_names(anchored, engine, capsys):  # noqa: F811
    root = anchored
    (root / LOCAL).write_text('{"\\u001b[2K\\r\\u001b[8m": 1, "disableAllHooks": true}')
    engine._anchor_local_first_record_warning(root)
    out = capsys.readouterr().out
    assert "\x1b" not in out and "\r" not in out
    screen = "\n".join(render(out))
    assert "WARNING" in screen and "disableAllHooks" in screen


def test_display_helpers_match_in_launcher_and_engine(engine):
    assert L.ANCHOR_MCP_APPROVAL_KEYS == engine.ANCHOR_MCP_APPROVAL_KEYS
    for data in (None, b"{}", b'{"disableAllHooks": true}', b"not json", b"[1]",
                 b'{"permissions": {"allow": ["x"], "defaultMode": "y"}, "a": 1}',
                 b'{"permissions": 3}', b'{"permissions.defaultMode": 1, "permissions": {"defaultMode": 2}}'):
        assert L.anchor_local_key_values(data) == engine.anchor_local_key_values(data), data
    # a top-level key spelled like a nested one stays a different key
    vals = engine.anchor_local_key_values(b'{"permissions.defaultMode": 1, "permissions": {"defaultMode": 2}}')
    assert vals == {("", "permissions.defaultMode"): 1, ("permissions", "defaultMode"): 2}
