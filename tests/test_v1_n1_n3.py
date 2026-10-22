"""
v1.0.x review (Cyra, release/v1.0 @ d5601ec): the new findings N1-N3, as
tests that fail on d5601ec and pass after the fix.

N1 (medium)  The F6 rule trusted $RANDOM, $SECONDS, $LINENO (and the other
             shell-set variables) never to hold a "/". After `unset RANDOM;
             read RANDOM < f` (or an assignment, declare, export, printf -v,
             mapfile, getopts, a for loop, a function-local, an eval or sh -c
             body, or a value from the environment) that is false, and
             `rm -rf "/var/tmp/b-$RANDOM/CLAUDE.md"` can climb back into the
             project. Now: a variable the command can rebind, in any segment,
             or one Tess is unsure about, is not trusted, and the F6 rule
             applies (ask in Claude Code, deny in Codex).
N2 (low)     `xargs ./tessctl` (any tessctl spelling) with `run` arriving on
             stdin was allowed. Now it is treated like `xargs codex`.
             Residual, documented below: a program an interpreter builds at
             run time is not parsed.
N3 (low)     SECURITY.md wording (checked in test_security_md_states_the_residual).

Decisions are checked for Claude Code default mode, Claude Code acceptEdits
and Codex, as (claude default, claude acceptEdits, codex).
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / ".claude" / "hooks" / "tess-gate.py"
SLASHFREE = ("RANDOM", "SRANDOM", "SECONDS", "LINENO", "UID", "EUID", "PPID", "BASHPID",
             "EPOCHSECONDS", "EPOCHREALTIME", "HISTCMD", "OPTIND", "SHLVL", "COLUMNS", "LINES")


def _gate():
    sys.dont_write_bytecode = True  # never leave __pycache__ in .claude/hooks
    spec = importlib.util.spec_from_file_location("tess_gate_n1_n3", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _gate()


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    """A Tess instance copy (lock, pins, hooks) with a fake HOME."""
    tmp = tmp_path_factory.mktemp("n1n3")
    root = tmp / "proj"
    for rel in (".tess/tess.lock", ".tess/core/pinned-scripts.sha256", "tessctl",
                "tess.manifest.json", "conductor/guardrails.md", "CLAUDE.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    for tree in (".claude/hooks", "scripts/brain", ".tess/bin", ".tess/vendor"):
        shutil.copytree(REPO / tree, root / tree, ignore=shutil.ignore_patterns("__pycache__"))
    (root / ".claude" / "settings.json").write_text("{}\n")
    home = tmp / "home"
    (home / ".config").mkdir(parents=True)
    return root, home


@pytest.fixture(autouse=True)
def _env(proj, monkeypatch):
    monkeypatch.setenv("HOME", str(proj[1]))
    for k in ("XDG_CONFIG_HOME", "TESS_BRAIN_PROVENANCE_DIR", "GIT_DIR", "GIT_WORK_TREE",
              "TESS_CONSULT_DEPTH", "CDPATH", "TESS_HEADLESS", "TESS_DISPATCHED", *SLASHFREE):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(G, "_ancestry", lambda limit=40: ["python3", "zsh", "login"], raising=False)


def _decide(proj, cmd, runtime="claude", mode="default"):
    root = proj[0]
    data = {"tool_name": "Bash", "cwd": str(root), "tool_input": {"command": cmd}}
    if runtime == "codex":
        data["turn_id"] = "t"
    else:
        data["permission_mode"] = mode
    return G.decide(data, root, runtime)


def _all(proj, cmd):
    """(claude default, claude acceptEdits, codex) decisions."""
    return tuple(_decide(proj, cmd, rt, mode)[0] or "allow"
                 for rt, mode in (("claude", "default"), ("claude", "acceptEdits"), ("codex", None)))


ALLOW = ("allow", "allow", "allow")
ASK = ("ask", "ask", "deny")  # Codex cannot pause to ask: an ask is a deny there
DENY = ("deny", "deny", "deny")

T = '; rm -rf "/var/tmp/b-$RANDOM/CLAUDE.md"'

# ====================================================================== N1: rebound variables

N1_ASKED = [
    # Cyra's probe, verbatim
    'unset RANDOM; read RANDOM < id2.txt' + T,
    # every way of binding it
    'unset RANDOM; RANDOM=$(cat id2.txt)' + T,
    'unset RANDOM; declare RANDOM="$(cat id2.txt)"' + T,
    'unset RANDOM; typeset RANDOM="$(cat id2.txt)"' + T,
    'unset RANDOM; export RANDOM="$(cat id2.txt)"' + T,
    'unset RANDOM; readonly RANDOM="$(cat id2.txt)"' + T,
    'unset RANDOM; printf -v RANDOM %s "$(cat id2.txt)"' + T,
    'unset RANDOM; mapfile -t RANDOM < id2.txt' + T,
    'unset RANDOM; readarray RANDOM < id2.txt' + T,
    'unset RANDOM; getopts "$(cat o.txt)" RANDOM' + T,
    'unset RANDOM; : "${RANDOM:=$(cat id2.txt)}"' + T,
    'unset RANDOM; for RANDOM in $(cat id2.txt); do rm -rf "/var/tmp/b-$RANDOM/CLAUDE.md"; done',
    'unset RANDOM; select RANDOM in $(cat id2.txt); do rm -rf "/var/tmp/b-$RANDOM/CLAUDE.md"; done',
    'declare -n r=RANDOM; unset RANDOM; read r < id2.txt' + T,
    # a function-local binding
    'f() { local RANDOM; read RANDOM < id2.txt; rm -rf "/var/tmp/b-$RANDOM/CLAUDE.md"; }; f',
    'function f { unset RANDOM; read RANDOM < id2.txt; }; f' + T,
    # subshells, eval and sh -c bodies
    '(unset RANDOM; read RANDOM < id2.txt; rm -rf "/var/tmp/b-$RANDOM/CLAUDE.md")',
    '{ unset RANDOM; read RANDOM < id2.txt; }' + T,
    "eval 'unset RANDOM; read RANDOM < id2.txt'" + T,
    """bash -c 'unset RANDOM; read RANDOM < id2.txt; rm -rf "/var/tmp/b-$RANDOM/CLAUDE.md"'""",
    """sh -c 'unset RANDOM; read RANDOM < id2.txt; rm -rf "/var/tmp/b-$RANDOM/CLAUDE.md"'""",
    # the name spelled in pieces, or only known at run time
    'unset RAN""DOM; read RAN\\DOM < id2.txt' + T,
    "unset 'RANDOM'; read 'RANDOM' < id2.txt" + T,
    'n=RAN; unset ${n}DOM; read ${n}DOM < id2.txt' + T,
    "unset $'\\x52'ANDOM; read $'\\x52'ANDOM < id2.txt" + T,
    'unset {R,}ANDOM; read {R,}ANDOM < id2.txt' + T,
    'c=read; n=$(cat name.txt); unset $n; $c $n < id2.txt' + T,
    'source ./vars.sh' + T,
    '. ./vars.sh' + T,
    # the other trusted variables
    'unset SECONDS; read SECONDS < id2.txt; rm -rf "/var/tmp/b-$SECONDS/CLAUDE.md"',
    'unset LINENO; read LINENO < id2.txt; rm -rf "/var/tmp/b-$LINENO/CLAUDE.md"',
    'read EPOCHSECONDS < id2.txt; rm -rf "/var/tmp/b-$EPOCHSECONDS/CLAUDE.md"',
    'read BASHPID < id2.txt; rm -rf "/var/tmp/b-${BASHPID}/CLAUDE.md"',
    'OPTIND=$(cat id2.txt); rm -rf "/var/tmp/b-$OPTIND/CLAUDE.md"',
    # a program name in $(...) redefined by the command
    'date() { cat id2.txt; }; rm -rf "/var/tmp/b-$(date +%s)/CLAUDE.md"',
    'PATH=./bin:$PATH; rm -rf "/var/tmp/b-$(date +%s)/CLAUDE.md"',
]


@pytest.mark.parametrize("cmd", N1_ASKED)
def test_a_rebound_shell_variable_is_not_trusted(proj, cmd):
    assert _all(proj, cmd) == ASK, cmd


@pytest.mark.parametrize("name", ["RANDOM", "SECONDS", "EPOCHSECONDS", "COLUMNS"])
def test_a_shell_variable_from_the_environment_is_not_trusted(proj, monkeypatch, name):
    # In sh (dash) or an older bash these are plain variables: the environment decides.
    cmd = f'sh -c \'rm -rf "/var/tmp/b-${name}/CLAUDE.md"\''
    monkeypatch.setenv(name, "x/../../proj")
    assert _all(proj, cmd) == ASK, cmd
    monkeypatch.setenv(name, "42")  # a plain number holds no "/"
    assert _all(proj, cmd) == ALLOW, cmd


N1_ALLOWED = [
    # the current decision, unchanged, when nothing rebinds the variable
    'rm -rf "/var/tmp/b-$RANDOM"',
    'rm -rf "/var/tmp/b-$RANDOM/CLAUDE.md"',
    'rm -f "/var/tmp/out-$RANDOM.txt"',
    'rm -rf /var/tmp/b-${RANDOM}',
    'echo "$RANDOM"; rm -rf "/var/tmp/b-$RANDOM"',
    'mkdir -p "/var/tmp/run-$SECONDS-$LINENO"',
    'rm -rf "/var/tmp/b-$$/CLAUDE.md"',
    'rm -rf "/var/tmp/build-$$"',
    'mkdir -p "/var/tmp/run-$(date +%s)"',
    'rm -rf "/var/tmp/b-${#X}"',
    'rm -rf "/var/tmp/b-$((1 + 2))"',
    'ID=abc; rm -rf "/var/tmp/build-$ID"',
    'X=1; read line < f.txt; rm -rf "/var/tmp/b-$RANDOM"',
    'for i in 1 2; do rm -rf "/var/tmp/b-$RANDOM-$i"; done',
]


@pytest.mark.parametrize("cmd", N1_ALLOWED)
def test_shell_variables_nothing_rebinds_stay_trusted(proj, cmd):
    assert _all(proj, cmd) == ALLOW, cmd


N1_ASKED_BEFORE = [
    # these already asked before N1 and still do (no regression)
    'rm -rf "/var/tmp/build-$ID"',
    'read ID; rm -rf "/var/tmp/build-$ID"',
    'rm -rf "/var/tmp/b-$$/../../x"',
    'eval "$(cat setup.sh)"' + T,
]


@pytest.mark.parametrize("cmd", N1_ASKED_BEFORE)
def test_untrusted_run_time_parts_still_ask(proj, cmd):
    assert _all(proj, cmd) == ASK, cmd


def test_rebound_variable_inside_a_peer_call_is_still_only_an_ask(proj, monkeypatch):
    # the F6 rule, not the agent rule: an ask (deny in Codex), never allowed
    assert _all(proj, N1_ASKED[0]) == ASK


# ====================================================================== N2: xargs tessctl

N2_ASKED = [
    # Cyra's probe, and run arriving on stdin through every spelling
    "echo run | xargs ./tessctl",
    "printf 'run\\nplan.json\\n' | xargs ./tessctl",
    "echo run plan.json | xargs .tess/bin/tessctl",
    "echo run plan.json | xargs tessctl",
    "echo run plan.json | xargs python3 -I .tess/bin/tessctl",
    "echo run plan.json | xargs python3 -I -B .tess/bin/tessctl",
    "echo run plan.json | xargs -n 2 ./tessctl",
    "xargs -a args.txt ./tessctl",
    "xargs ./tessctl < args.txt",
    "echo run | xargs -I{} ./tessctl {} plan.json",
    "echo run | xargs -I X ./tessctl X plan.json",
    "echo run | xargs -I{} ./tessctl status {}",
    # a later --driver arriving on stdin overrides the fake one
    "echo --driver claude | xargs ./tessctl run --driver fake plan.json",
    "echo plan.json | xargs ./tessctl run --driver fake",
    # already an ask before; unchanged
    "echo plan.json | xargs ./tessctl run",
    "echo plan.json | xargs ./tessctl run --driver codex",
]


@pytest.mark.parametrize("cmd", N2_ASKED)
def test_xargs_tessctl_is_treated_like_xargs_codex(proj, cmd):
    assert _all(proj, cmd) == ASK, cmd
    assert _all(proj, "echo hi | xargs codex") == ASK  # the existing rule it now matches


@pytest.mark.parametrize("cmd", N2_ASKED[:6])
def test_xargs_tessctl_inside_a_peer_call_is_refused(proj, monkeypatch, cmd):
    monkeypatch.setenv("TESS_CONSULT_DEPTH", "1")
    assert _all(proj, cmd) == DENY, cmd


N2_ALLOWED = [
    "echo x | xargs ./tessctl status",
    "echo m1 | xargs ./tessctl verify",
    "echo x | xargs ./tessctl --help",
    "./tessctl status",
    "./tessctl run --driver fake plan.json",
]


@pytest.mark.parametrize("cmd", N2_ALLOWED)
def test_tessctl_forms_xargs_cannot_turn_into_run_stay_allowed(proj, cmd):
    assert _all(proj, cmd) == ALLOW, cmd


# Residual (N2): Tess does not parse arbitrary interpreter programs. A program
# that builds `tessctl run` at run time is decided by the interpreter rules
# alone, not as an agent launch; inside a peer call, tessctl's own
# TESS_CONSULT_DEPTH check still refuses to dispatch, and Claude Code's own
# permission prompt still applies when the gate allows. This test pins the
# current decision so a change to it is a deliberate one.
RESIDUAL = ("python3 -c 'import subprocess; "
            "subprocess.run([\"./tess\" + \"ctl\", \"r\" + \"un\", \"plan.json\"])'")


def test_residual_interpreter_built_tessctl_run_is_not_seen_as_an_agent_launch(proj, monkeypatch):
    claude_default, reason = _decide(proj, RESIDUAL)
    assert "dispatches" not in (reason or "")
    monkeypatch.setenv("TESS_CONSULT_DEPTH", "1")
    # not refused as a peer-call launch either: the gate cannot see it
    assert "peer call" not in (_decide(proj, RESIDUAL)[1] or "")
    monkeypatch.delenv("TESS_CONSULT_DEPTH")
    assert _all(proj, RESIDUAL) == RESIDUAL_DECISION


RESIDUAL_DECISION = ALLOW


# ====================================================================== N3: SECURITY.md

def test_security_md_states_the_residual():
    text = re.sub(r"\s+", " ", (REPO / "SECURITY.md").read_text(encoding="utf-8"))
    assert "only while `TESS_CONSULT_DEPTH` survives" in text
    assert "at run time inside an interpreter" in text
    assert "Claude Code's own permission prompt" in text
    assert "`unset RANDOM; read RANDOM < f`" in text
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Cyra N1" in changelog and "xargs ./tessctl" in changelog
