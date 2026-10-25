"""1.0.0: the automated security review of a4113f7, the gate items (a, b).

a. The rule that refuses an agent's run of a handler only the runtime may run
   (the gate's task-start handler, and the brain's hook handler, B-2) matched
   the literal text after the script name. A word whose value is only known
   when the shell runs it (a glob, a variable, a command substitution, a
   brace, a tilde, zsh `=cmd`, a `{}` that find or xargs fill in) could stand
   for the selector (`--task-start`, `hook`) without the gate seeing it.
   Policy, after a word that names or can expand to one of these scripts:
     * a word that can expand to the selector is refused, as the literal is;
     * any other word that is not a plain literal asks (Codex: refuses), and
       so does a run of the script by xargs;
     * programs that only read or print their words keep the literal rule.
   Defence in depth: the task-start handler marks a task only when its input
   came as the runtime sends it (a pipe, a UserPromptSubmit payload).
b. Unquoted variable and substitution values are read as globs under the
   worst case (zsh GLOB_SUBST), but `(`, `|` and zsh's `<N-M>` were read as
   plain characters. A value holding them now asks, as the raw words do, and
   the field is unreadable to the path checks.

Decisions: (claude default, claude acceptEdits, codex). The attack rows are
allowed by a4113f7's gate (or, where noted, asked there and refused here);
the everyday rows are allowed by both.
"""
from __future__ import annotations

import io
import json
import os

import pytest

from test_v1_0_0_cyra_f8_gate import _all, _env, world  # noqa: F401 — fixtures
from test_v1_n1_n3 import ALLOW, ASK, DENY, G

# ============================================== a. a word that can be the selector
A_REFUSED = [
    "python3 .claude/hooks/tess-gate.py --task-st*",
    "python3 .claude/hooks/tess-gate.py --task-?tart",
    "python3 .claude/hooks/tess-gate.py --task-s[t]art",
    "python3 .claude/hooks/tess-gate.py --TASK-START*",          # case-blind (nocaseglob)
    "python3 .claude/hooks/tess-gate.py --task-start~x",          # EXTENDED_GLOB `L~R` (asked before)
    "python3 .claude/hooks/tess-gate.py ^--runtime",              # EXTENDED_GLOB `^x`
    "S='--task-st*'; python3 .claude/hooks/tess-gate.py $S",      # unquoted value: a pattern
    "HOME=--task-start; python3 .claude/hooks/tess-gate.py ~",    # a tilde is $HOME
    "python3 .claude/hooks/tess-gat?.py --task-start",            # the script through a pattern (asked before)
    "python3 .claude/hooks/*.py --task-start",                    # (asked before)
    "python3 -I -B .claude/hooks/run-pinned.py --on-fail warn -- .claude/hooks/tess-gate.py --task-*",
    "cd .claude/hooks && python3 tess-gate.py --task-s?art",
    "bash -c 'python3 .claude/hooks/tess-gate.py --task-st*'",
    # the brain's hook handler, same table
    "python3 scripts/brain/tessbrain.py h?ok session-start",
    "python3 scripts/brain/tessbrain.py --root . [h]ook session-start",
    "python3 scripts/brain/tessbr?in.py hook session-start",
]


@pytest.mark.parametrize("cmd", A_REFUSED)
def test_a_a_word_that_can_expand_to_the_selector_is_refused(world, cmd):
    assert _all(world, cmd) == DENY


A_ASKS = [
    'python3 .claude/hooks/tess-gate.py "$X"',
    "python3 .claude/hooks/tess-gate.py $X",
    "python3 .claude/hooks/tess-gate.py ${X:-x}",
    "python3 .claude/hooks/tess-gate.py $(cat f)",
    "python3 .claude/hooks/tess-gate.py `cat f`",
    'python3 .claude/hooks/tess-gate.py "$(printf %s LS10)"',
    "python3 .claude/hooks/tess-gate.py $((1))",
    "python3 .claude/hooks/tess-gate.py src/*.json",
    "python3 .claude/hooks/tess-gate.py ~/x",
    "python3 .claude/hooks/tess-gate.py =ls",
    "cat f | xargs python3 .claude/hooks/tess-gate.py",
    "find -f --task-start -maxdepth 0 -exec python3 .claude/hooks/tess-gate.py {} \\;",
    'cd .claude/hooks && python3 tess-gate.py "$X"',
    'python3 -I -B .claude/hooks/run-pinned.py --on-fail warn -- .claude/hooks/tess-gate.py "$X"',
    "python3 scripts/brain/tessbrain.py status --root ~/x",
]


@pytest.mark.parametrize("cmd", A_ASKS)
def test_a_a_word_only_known_at_run_time_asks(world, cmd):
    assert _all(world, cmd) == ASK


# Quoting tricks the shell removes were already read; pinned here.
A_PINNED = [
    "python3 .claude/hooks/tess-gate.py --task-\"start\"",
    "python3 .claude/hooks/tess-gate.py --task-st''art",
    "python3 .claude/hooks/tess-gate.py --task-\\start",
    "python3 .claude/hooks/tess-gate.py $'\\055-task-start'",
    "python3 .claude/hooks/tess-gate.py --{task-start,x}",
    "S=--task-start; python3 .claude/hooks/tess-gate.py \"$S\"",
    "S=--task-st; python3 .claude/hooks/tess-gate.py \"${S}art\"",
]


@pytest.mark.parametrize("cmd", A_PINNED)
def test_a_quoting_tricks_stay_refused(world, cmd):
    assert _all(world, cmd) == DENY


A_EVERYDAY = [
    "grep -n foo .claude/hooks/tess-gate.py tests/*.py",
    "wc -l .claude/hooks/*.py",
    "ls -la .claude/hooks/tess-gate.py *",
    "grep -n task_start .claude/hooks/tess-gate.py",
    "python3 .claude/hooks/tess-gate.py --runtime claude < p.json",
    "python3 scripts/brain/tessbrain.py status",
]


@pytest.mark.parametrize("cmd", A_EVERYDAY)
def test_a_neighbours_are_unchanged(world, cmd):
    assert _all(world, cmd) == ALLOW


def test_a_plain_literal_and_readings():
    w = lambda text: G._scan(text)[0]  # noqa: E731
    for text in ("--task-start", "'--task-*'", "a\\*b", "--runtime=claude"):
        assert G._plain_literal(w(text)), text
    for text in ("--task-st*", "$X", "~/x", "{a,b}", "=ls", "{}", "x^y", "a#", "$(cat f)", "`id`"):
        assert not G._plain_literal(w(text)), text
    assert not G._plain_literal(G._field("--task-start"))  # a value the gate expanded
    assert G._reading_may_be([("--task-start", None)], ("--task-start",))
    assert G._reading_may_be([("x", "--TASK-*")], ("--task-start",))
    assert G._reading_may_be([("x", ".claude/hooks/tess-g*")], ("tess-gate.py",), True)
    assert not G._reading_may_be([("src/x.json", "src/*.json")], ("--task-start",))


# ======================================== a. defence in depth: how the input arrives
class _Rec:
    def __init__(self):
        self.calls = []

    def __call__(self, data):
        self.calls.append(data)


HOOK = {"hook_event_name": "UserPromptSubmit", "session_id": "s-a4", "prompt": "hi",
        "transcript_path": "/nonexistent", "cwd": "/"}


def _pipe(text: str):
    r, w = os.pipe()
    os.write(w, text.encode())
    os.close(w)
    return os.fdopen(r, "r")


@pytest.fixture
def rec(monkeypatch):
    r = _Rec()
    monkeypatch.setattr(G, "task_start", r)
    return r


def test_a_task_start_marks_a_task_only_for_the_runtimes_input(rec, monkeypatch, tmp_path, capsys):
    # the runtime: a UserPromptSubmit payload on a pipe
    monkeypatch.setattr(G.sys, "stdin", _pipe(json.dumps(HOOK)))
    assert G.main(["--runtime", "claude", "--task-start"]) == 0
    assert [c["session_id"] for c in rec.calls] == ["s-a4"]
    # an agent's Bash command gets /dev/null as its input
    monkeypatch.setattr(G.sys, "stdin", open(os.devnull))
    assert G.main(["--runtime", "claude", "--task-start"]) == 0
    # a redirected file is not how the runtime sends a hook its input
    f = tmp_path / "p.json"
    f.write_text(json.dumps(HOOK))
    monkeypatch.setattr(G.sys, "stdin", open(f))
    assert G.main(["--runtime", "claude", "--task-start"]) == 0
    # a pipe with a payload that is not a UserPromptSubmit hook's
    for doc in ({"session_id": "s-a4"}, dict(HOOK, hook_event_name="PreToolUse"),
                {k: v for k, v in HOOK.items() if k != "prompt"}, ["s-a4"]):
        monkeypatch.setattr(G.sys, "stdin", _pipe(json.dumps(doc)))
        assert G.main(["--runtime", "claude", "--task-start"]) == 0
    # a closed or unusable stdin
    monkeypatch.setattr(G.sys, "stdin", io.StringIO(json.dumps(HOOK)))
    assert G.main(["--runtime", "claude", "--task-start"]) == 0
    assert len(rec.calls) == 1
    out = capsys.readouterr()
    assert out.out == "" and out.err.count("no new task marked") == 7


# ============================================ b. a value that holds `(`, `|`, `<N-M>`
B_ASKS = [
    "X='(CLAUDE|x).md'; rm -f $X",
    "X='CLAUDE<->.md'; rm -f $X",
    "X='CLAUDE<1-9>.md'; rm -f $X",
    "X='*(e:touch .claude/x:)'; echo $X",     # a glob qualifier runs code (zsh GLOB_SUBST)
    "X='a|b'; rm -f $X",
    "X='@(CLAUDE).md'; rm -f $X",
    "X='!(src)'; rm -rf $X",
    "X='src/*(D)'; rm -rf $X",
    "X=$(echo '(CLAUDE|x).md'); rm -f $X",
    "rm -f $(echo '(CLAUDE|x).md')",
    "f() { rm -f $1; }; f '(CLAUDE|x).md'",
]


@pytest.mark.parametrize("cmd", B_ASKS)
def test_b_an_unquoted_value_holding_a_pattern_tess_does_not_read_asks(world, cmd):
    assert _all(world, cmd) in (ASK, DENY)


B_EVERYDAY = [
    "X='(CLAUDE|x).md'; rm -f \"$X\"",      # quoted: never a pattern
    "X='a|b'; echo \"$X\"",
    "X='(CLAUDE|x).md'; Y=$X; echo ok",     # an assignment is neither split nor globbed
    "X='(CLAUDE|x).md'; export Y=$X",
    "X='src/a.py'; rm -f $X",
    "X='(src)'; echo \"$X\" | tr a b",
]


@pytest.mark.parametrize("cmd", B_EVERYDAY)
def test_b_neighbours_are_unchanged(world, cmd):
    assert _all(world, cmd) == ALLOW


def test_b_the_field_itself_is_unreadable_to_the_path_checks(world, monkeypatch):
    """Without the command-level ask, the path checks still do not read such a
    value as a plain name (_split_fields: only known at run time)."""
    assert G._split_fields([("(CLAUDE|x).md", "(CLAUDE|x).md", True, True)], " \t\n") is None
    assert G._split_fields([("CLAUDE<1-9>.md", "CLAUDE<1-9>.md", False, True)], " \t\n") is None
    assert G._split_fields([("(a|b)", "[(]a|b[)]", False, False)], " \t\n") == [("(a|b)", None)]
    monkeypatch.setattr(G, "_check_value_patterns", lambda *a, **k: None)
    assert _all(world, "X='(CLAUDE|x).md'; rm -f $X") in (ASK, DENY)
