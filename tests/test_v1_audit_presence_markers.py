"""v1.0 integration pass 3: Tess's "a person must type this" steps refuse
inside an AI assistant session.

Codex can run a command in a pseudo-terminal and type into it later
(write_stdin), which never reaches Tess's gate, and Claude Code's Bash runs
commands the same way, so a TTY check cannot tell the operator from an
assistant. tessctl's presence helpers now also refuse when the process was
started inside Claude Code (CLAUDECODE, CLAUDE_CODE_ENTRYPOINT) or Codex
(CODEX_THREAD_ID, CODEX_SANDBOX, CODEX_SANDBOX_NETWORK_DISABLED), and tell the
operator to run the command in their own terminal. The gate half (Codex
denies the operator-only forms outright) is in test_v1_audit_integration.py.

The suite itself runs without these markers (tests/conftest.py); each test
here sets one.
"""
from __future__ import annotations

import os

import pytest

from _presence_pty import AGENT_SESSION_MARKERS, operator_env, run_tessctl_in_pty
from test_codex_gate import HAS_GIT, proj  # noqa: F401  (fixture)

MARKER_VALUES = {"CODEX_THREAD_ID": "019a-thread", "CODEX_SANDBOX": "seatbelt",
                 "CODEX_SANDBOX_NETWORK_DISABLED": "1", "CLAUDECODE": "1",
                 "CLAUDE_CODE_ENTRYPOINT": "cli"}


def test_marker_list_matches_the_engine(engine):
    assert tuple(engine.AGENT_SESSION_MARKERS) == AGENT_SESSION_MARKERS
    assert set(MARKER_VALUES) == set(AGENT_SESSION_MARKERS)


def _refusal(exc, marker):
    msg = str(exc.value.code)
    assert "REFUSED" in msg and marker in msg and "your own terminal" in msg, msg
    return msg


@pytest.mark.parametrize("marker", AGENT_SESSION_MARKERS)
def test_shared_presence_helper_refuses_in_an_assistant_session(engine, monkeypatch, marker):
    """Covers override, reset, resolve, rollback (`roll back`), roster changes
    and the downgrade (`downgrade to <tag>`): they all use this helper."""
    monkeypatch.setenv(marker, MARKER_VALUES[marker])
    with pytest.raises(SystemExit) as exc:
        engine._require_human_presence("rollback", "rolling back Tess's safety files",
                                       "no file was restored.", "roll back")
    assert "no file was restored" in _refusal(exc, marker)


@pytest.mark.parametrize("marker", AGENT_SESSION_MARKERS)
def test_approve_refuses_in_an_assistant_session(engine, monkeypatch, marker):
    monkeypatch.setenv(marker, MARKER_VALUES[marker])
    with pytest.raises(SystemExit) as exc:
        engine._approve_require_human_presence("CLAUDE.md")
    assert "stays quarantined" in _refusal(exc, marker)


@pytest.mark.parametrize("marker", AGENT_SESSION_MARKERS)
def test_signing_refuses_in_an_assistant_session(engine, monkeypatch, marker):
    """`sign as <name>` for `verdict sign` and `gate signoff sign`."""
    monkeypatch.setenv(marker, MARKER_VALUES[marker])
    with pytest.raises(SystemExit) as exc:
        engine._signer_require_terminal("tessctl verdict sign")
    assert "nothing was signed" in _refusal(exc, marker)


def test_no_marker_falls_through_to_the_terminal_check(engine, monkeypatch):
    for m in AGENT_SESSION_MARKERS:
        monkeypatch.delenv(m, raising=False)
    assert engine._agent_session_marker() is None
    with pytest.raises(SystemExit) as exc:  # pytest's stdin is not a terminal
        engine._require_human_presence("rollback", "rolling back", "no file was restored.",
                                       "roll back")
    assert "interactive terminal" in str(exc.value.code)


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
@pytest.mark.parametrize("marker", AGENT_SESSION_MARKERS)
def test_a_real_terminal_inside_an_assistant_session_is_refused(proj, marker):  # noqa: F811
    """End to end on a pseudo-terminal, as Codex's write_stdin would drive it:
    `anchor accept` refuses before it shows a prompt."""
    env = operator_env(TESS_ROOT=str(proj), **{marker: MARKER_VALUES[marker]})
    rc, out = run_tessctl_in_pty(proj, "anchor", "accept", answer="accept safety changes",
                                 prompt=b"accept> ", env=env, timeout=60)
    assert rc != 0 and "REFUSED" in out and marker in out and "your own terminal" in out, out
    assert "accept>" not in out


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_the_operators_own_terminal_still_reaches_the_prompt(proj):  # noqa: F811
    rc, out = run_tessctl_in_pty(proj, "anchor", "accept", answer="no", prompt=b"accept> ",
                                 timeout=60)
    assert "accept>" in out and "REFUSED — this was started from inside" not in out, out
    assert rc != 0 and "nothing was recorded" in out, out
    assert all(m not in out for m in AGENT_SESSION_MARKERS)
    assert os.environ.get("CLAUDECODE") is None  # tests/conftest.py removed it for the run
