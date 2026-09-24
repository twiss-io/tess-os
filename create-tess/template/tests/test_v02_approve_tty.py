"""
v0.2: `tessctl approve` of a quarantined or security-tier file needs a human
at an interactive terminal, and acts on EVERY lock entry that shares the
live path.

On 5c2d698 approve ran headless (an agent could approve its own quarantined
guardrails edit through a pipe) and flipped only the first matching lock
entry, leaving the others quarantined.
"""

from __future__ import annotations

import io
import sys

import pytest

from conftest import ns

LR = "conductor/guardrails.md"          # security tier
AUTHORITATIVE = "GUARDRAILS\n"
WEAKENED = "GUARDRAILS weakened by an agent\n"
RATIONALE = "operator reviewed and accepted this edit"


class _Stream(io.StringIO):
    """A text stream whose isatty() answer the test controls."""

    def __init__(self, text: str = "", tty: bool = True):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


def _set_stdio(monkeypatch, *, stdin_tty: bool, stdout_tty: bool, typed: str = ""):
    monkeypatch.setattr(sys, "stdin", _Stream(typed, tty=stdin_tty))
    out = _Stream("", tty=stdout_tty)
    monkeypatch.setattr(sys, "stdout", out)
    return out


def _quarantined(project, n_entries: int = 1):
    """A live path backed by n_entries lock entries, all quarantined, with the
    attempted edit parked in .tess/quarantine/ and the authoritative bytes live."""
    keys = []
    for i in range(n_entries):
        core_key = ".tess/core/" + LR if i == 0 else f".tess/core/templates/guardrails-part-{i}.md"
        keys.append(project.add(
            LR, AUTHORITATIVE, tier="security", status="quarantined",
            core_key=core_key,
            quarantined_at="2026-09-24T00:00:00.000000Z",
            quarantined_by="agent",
        ))
    project.write()
    q = project.root / ".tess" / "quarantine" / LR
    q.parent.mkdir(parents=True, exist_ok=True)
    q.write_text(WEAKENED)
    return keys


def _statuses(project, keys):
    files = project.mod.load_lock(project.root)["files"]
    return [files[k]["status"] for k in keys]


def test_approve_without_tty_refuses_and_stays_quarantined(project, monkeypatch):
    keys = _quarantined(project)
    _set_stdio(monkeypatch, stdin_tty=False, stdout_tty=False, typed=LR + "\n")
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_approve(ns(path=LR, rationale=RATIONALE), project.root)
    assert ei.value.code not in (0, None)
    assert "TTY" in str(ei.value.code)
    assert _statuses(project, keys) == ["quarantined"]
    assert project.read_live(LR) == AUTHORITATIVE


@pytest.mark.parametrize("stdin_tty,stdout_tty", [(True, False), (False, True)])
def test_approve_needs_both_streams_to_be_ttys(project, monkeypatch, stdin_tty, stdout_tty):
    keys = _quarantined(project)
    _set_stdio(monkeypatch, stdin_tty=stdin_tty, stdout_tty=stdout_tty, typed=LR + "\n")
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_approve(ns(path=LR, rationale=RATIONALE), project.root)
    assert ei.value.code not in (0, None)
    assert _statuses(project, keys) == ["quarantined"]
    assert project.read_live(LR) == AUTHORITATIVE


@pytest.mark.parametrize("typed", ["", "conductor/other.md\n", "yes\n"])
def test_approve_with_tty_but_wrong_path_typed_refuses(project, monkeypatch, typed):
    keys = _quarantined(project)
    _set_stdio(monkeypatch, stdin_tty=True, stdout_tty=True, typed=typed)
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_approve(ns(path=LR, rationale=RATIONALE), project.root)
    assert ei.value.code not in (0, None)
    assert _statuses(project, keys) == ["quarantined"]
    assert project.read_live(LR) == AUTHORITATIVE


def test_approve_with_tty_and_path_typed_back_succeeds(project, monkeypatch):
    keys = _quarantined(project)
    out = _set_stdio(monkeypatch, stdin_tty=True, stdout_tty=True, typed=LR + "\n")
    project.mod.cmd_approve(ns(path=LR, rationale=RATIONALE), project.root)
    assert _statuses(project, keys) == ["locally-modified"]
    assert project.read_live(LR) == WEAKENED
    assert "Type the path" in out.getvalue()


def test_approve_flips_every_entry_for_the_live_path(project, monkeypatch):
    """Three lock entries share conductor/guardrails.md; approve flips all
    three. On 5c2d698 only the first flipped and two stayed quarantined."""
    keys = _quarantined(project, n_entries=3)
    _set_stdio(monkeypatch, stdin_tty=True, stdout_tty=True, typed=LR + "\n")
    project.mod.cmd_approve(ns(path=LR, rationale=RATIONALE), project.root)
    files = project.mod.load_lock(project.root)["files"]
    assert [files[k]["status"] for k in keys] == ["locally-modified"] * 3
    for k in keys:
        assert files[k]["approved_rationale"] == RATIONALE
        assert "quarantined_at" not in files[k]
        assert "quarantined_by" not in files[k]
    assert project.read_live(LR) == WEAKENED


def test_cli_approve_through_a_pipe_is_refused(project, run_cli):
    """End to end: an agent running `tessctl approve` with piped stdio (the
    shape of every tool call) exits non-zero and nothing changes. On 5c2d698
    this exited 0 and the weakened guardrails went live."""
    keys = _quarantined(project)
    res = run_cli(project.root, "approve", LR, "--rationale", RATIONALE, input_text=LR + "\n")
    assert res.returncode != 0, res.stdout + res.stderr
    assert "TTY" in (res.stdout + res.stderr)
    assert _statuses(project, keys) == ["quarantined"]
    assert project.read_live(LR) == AUTHORITATIVE


def test_approve_has_no_bypass_flag(engine):
    """The approve subcommand takes a path and --rationale, nothing else: no
    --yes / --non-interactive style flag can skip the human-presence check."""
    parser = engine.build_parser()
    sub = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
    p_approve = sub.choices["approve"]
    opts = {s for a in p_approve._actions for s in a.option_strings}
    assert opts <= {"-h", "--help", "--rationale"}, opts
