"""1.0.0: Cyra's delta review of a769130, null-glob word removal as a class.

M1. Under zsh NULL_GLOB / CSH_NULL_GLOB or bash nullglob a glob that matches
    nothing is removed before the command runs, and every later word moves one
    position left. a769130 counted only a word written as a glob as one that
    can vanish, and only re-read the write-target binding. A word whose
    glob-ness comes from expansion (an unquoted variable or command
    substitution, a brace result) can vanish too, and every rule that reads a
    command by position is affected (a code argument, a function's $2, ...).
    Fix: one predicate (_globbed) decides "can this word be a glob" from the
    gate's own expansion model, and the whole command is checked again for
    every word list the shell can be left with (_nullglob_lists).
L1. That predicate uses the worst-case glob set (zsh EXTENDED_GLOB `^ ~ #`),
    also for the program word (a builtin it can name) and a GLOB_ASSIGN value.

Decisions: (claude default, claude acceptEdits, codex). The refused rows are
allowed (or, where noted, asked) by a769130's gate; the everyday rows are
allowed by both.
"""
from __future__ import annotations

import pytest

from test_v1_0_0_cyra_f8_gate import _all, _env, world  # noqa: F401 — fixtures
from test_v1_n1_n3 import ALLOW, ASK, DENY, G

# ======================================= M1: a word that is a glob once expanded
PARAM_REFUSED = [
    "P='*.none'; curl -o $P .claude/settings.json",
    "P='zz*.none'; sort -o $P .claude/hooks/tess-gate.py",
    "P='zz*.none'; sort -o ${P} .claude/settings.json",
]
SUBST_REFUSED = [
    "curl -o $(echo '*.none') .claude/settings.json",
    "sort -o `printf %s 'zz*.none'` .claude/settings.json",
]
BRACE_REFUSED = [
    "curl -o {x,y}*.none .claude/settings.json",
    "sort -o zz{1,2}.no* .claude/settings.json",
]
# L1: a glob only under zsh EXTENDED_GLOB
EXT_REFUSED = [
    "curl -o x#.none .claude/settings.json",
    "sort -o zznone# .claude/settings.json",
    "sort -o ^zz.none .claude/hooks/tess-gate.py",
]


@pytest.mark.parametrize("cmd", PARAM_REFUSED)
def test_m1_an_unquoted_value_that_is_a_glob_can_vanish(world, cmd):
    assert _all(world, cmd) == DENY


@pytest.mark.parametrize("cmd", SUBST_REFUSED)
def test_m1_a_command_substitution_that_is_a_glob_can_vanish(world, cmd):
    assert _all(world, cmd) == DENY


@pytest.mark.parametrize("cmd", BRACE_REFUSED)
def test_m1_a_brace_result_that_is_a_glob_can_vanish(world, cmd):
    assert _all(world, cmd) == DENY


@pytest.mark.parametrize("cmd", EXT_REFUSED)
def test_l1_an_extended_glob_word_can_vanish(world, cmd):
    assert _all(world, cmd) == DENY


# A word only known at run time may be a no-match glob (asked on a769130).
def test_m1_a_run_time_word_can_vanish(world):
    assert _all(world, "curl -o $UNSET_THING .claude/settings.json") == DENY


# ============================ M1 as a class: every rule that reads by position
CLASS_REFUSED = [
    "python3 -c zz*.none 'open(\".claude/settings.json\",\"w\")'",
    "node -e zz*.none 'require(\"fs\").writeFileSync(\".claude/settings.json\",\"x\")'",
    "f() { cp src/a.py \"$2\"; }; f zz*.none src/b .claude/settings.json",
    "P='zz*.none'; f() { cp src/a.py \"$2\"; }; f $P src/b .claude/settings.json",
    # asked on a769130 for another reason; refused now that the shift is read
    "bash -c *.none 'cp src/a.py .claude/settings.json'",
    "zz*.none cp src/a.py .claude/settings.json",
]


@pytest.mark.parametrize("cmd", CLASS_REFUSED)
def test_m1_a_vanishing_word_cannot_move_code_or_a_positional_into_place(world, cmd):
    assert _all(world, cmd) == DENY


# run-3 audit C1: one row per position-dependent check. Each check sees the
# command again with the vanishing word removed. Rows marked "both" were
# already refused on a769130 for another reason; they pin the coverage.
POSITION_REFUSED = [
    "git -c zz*.none core.hooksPath=x commit -m m",              # git option value (allowed before)
    "git --git-dir zz*.none config core.hooksPath x",            # git option value (both)
    "cp -t zz*.none .claude/hooks src/a.py",                     # copy-into folder (both)
    "mv -t zz*.none .claude/hooks src/a.py",                     # (both)
    "install -t zz*.none .claude/hooks src/a.py",                # (both)
    "ditto src zz*.none .claude",                                # (both)
    "rsync -a src/a.py zz*.none .claude/settings.json",          # (both)
    "tar -xf src/a.tar -C zz*.none .claude",                     # extractor folder (both)
    "ln -s src/a.py zz*.none .claude/settings.json",             # link path (both)
    "sed -i -e zz*.none 's/x/y/' .claude/settings.json",         # sed script / files (both)
    "find zz*.none .claude -delete",                             # find operands (both)
    "claude --permission-mode zz*.none --dangerously-skip-permissions -p hi",  # agent CLI (both)
]


@pytest.mark.parametrize("cmd", POSITION_REFUSED)
def test_c1_every_position_dependent_check_sees_the_shift(world, cmd):
    assert _all(world, cmd) == DENY


def test_c1_a_tessctl_subcommand_behind_a_vanishing_word_still_asks(world):
    assert _all(world, "./tessctl zz*.none anchor off") == ASK


# run-3 audit C2: the GLOB_ASSIGN mark survives what keeps the value possible
# (asked on a769130: the quoted use was read as literal text there).
C2_REFUSED = [
    "X=.cla*/settings.json; true && X=src/a.py; cp src/a.py \"$X\"",
    "X=.cla*/settings.json; if true; then X=src/a.py; fi; cp src/a.py \"$X\"",
    "eval 'X=.cla*/settings.json'; cp src/a.py \"$X\"",
    "X=.cla*/settings.json; for X in src/a.py; do :; done; cp src/a.py \"$X\"",
    "X=.cla*/settings.json; for X in; do :; done; cp src/a.py \"$X\"",
]


@pytest.mark.parametrize("cmd", C2_REFUSED)
def test_c2_a_glob_assigned_value_keeps_its_mark_when_it_may_survive(world, cmd):
    assert _all(world, cmd) == DENY


def test_c2_an_ordinary_reassignment_is_unchanged(world):
    assert _all(world, "X=src/*.py; true && X=src/a.py; cp src/a.py \"$X\"") == ALLOW
    assert _all(world, "X=.cla*/settings.json; X=src/a.py; cp src/a.py \"$X\"") == ALLOW


def test_m1_set_with_a_glob_makes_the_positionals_run_time_values(world):
    assert _all(world, "set -- zz*.none .claude/settings.json; cp src/a.py \"$1\"") == ASK


def test_m1_glob_assign_with_glob_subst_reads_an_expanded_value_as_a_pattern(world):
    # zsh GLOB_ASSIGN + GLOB_SUBST: X=$Y globs Y's value when it is assigned
    assert _all(world, "Y='.cla*/settings.json'; X=$Y; cp src/a.py \"$X\"") == DENY


def test_l1_a_program_word_that_is_cd_under_extended_glob(world):
    # `c#d` names `cd` under EXTENDED_GLOB: the relative path after it is unknown
    assert _all(world, "c#d .claude && touch settings.json") == DENY


# Reid M3: past six possibly-vanishing words Tess asks only where a word that
# moves left can matter (a write or option slot, code, a function, git options).
CAP_ASKS = [
    "cp a* b* c* d* e* f* g* src/a.py",
    "sort -o out a* b* c* d* e* f* g*",
    "git -c a* b* c* d* e* f* g* status",
    "pytest a* b* c* d* e* f* g*",      # pytest options take values (--basetemp DIR)
    "f() { :; }; f a* b* c* d* e* f* g*",
    "wc -l a* b* c* d* e* f* g*",        # any option disqualifies the shortcut (fail closed)
]
CAP_READ_ONLY = [
    "ls *.a *.b *.c *.d *.e *.f *.g",
    "echo a* b* c* d* e* f* g*",
    "cat a* b* c* d* e* f* g*",
    "grep x a* b* c* d* e* f* g*",
    "wc a* b* c* d* e* f* g*",
    "git add a* b* c* d* e* f* g*",
    "echo $a $b $c $d $e $f $g",
]


@pytest.mark.parametrize("cmd", CAP_ASKS)
def test_m1_more_possibly_vanishing_words_than_tess_checks_asks(world, cmd):
    assert _all(world, cmd) == ASK


@pytest.mark.parametrize("cmd", CAP_READ_ONLY)
def test_m3_read_only_globs_do_not_prompt(world, cmd):
    assert _all(world, cmd) == ALLOW


# Reid M2: the key-folder read check lists a word that mixes `^ ~ #` with an
# ordinary wildcard under the worst case too, as the write side does.
KEY_MIXED = [
    "grep -r tess ~/.co^nfig*",
    "grep -r x ~/.c*~foo",
    "rg x ~/.co^x*",
]


@pytest.mark.parametrize("cmd", KEY_MIXED)
def test_m2_a_mixed_extended_glob_cannot_reach_the_key_folder(world, cmd):
    assert _all(world, cmd) == DENY


EVERYDAY = [
    "[ -f src/a.py ] && echo ok",
    "[[ -f src/a.py ]] && echo ok",
    "curl -o out.json https://example.invalid/x#frag",
    "curl -o out.json https://example.invalid/x",
    "cp src/*.py web/dist/",
    "sort -o src/out.txt $(echo src/a.py)",
    "printf '%s\\n' {a,b}*.none",
    "P='src/*.py'; ls $P",
    "f() { echo \"$1\"; }; f src/*.py",
    "python3 -c 'print(1)' src/*.py",
    "cat *.log",
    "cp a* b* src/a.py",
    "tar czf backup.tgz src",
]


@pytest.mark.parametrize("cmd", EVERYDAY)
def test_neighbours_are_unchanged(world, cmd):
    assert _all(world, cmd) == ALLOW


# ===================================================== the shared predicate
def _w(cmd):
    return G._segments(cmd)[0]


@pytest.mark.parametrize("cmd,idx,want", [
    ("x *.py", 1, True),
    ("x x#y", 1, True),            # EXTENDED_GLOB
    ("x ^y", 1, True),
    ("x {a,b}*", 1, True),         # a brace result
    ("x $UNKNOWN", 1, True),       # only known at run time, unquoted
    ('x "$UNKNOWN"', 1, False),    # quoted: never globbed
    ("x <(true)", 1, False),       # a /dev/fd path
    ("x [", 1, False),             # a lone [ stays as written in both shells
    ("x '*'", 1, False),
    ("x a.py", 1, False),
])
def test_one_predicate_from_the_expansion_model(cmd, idx, want):
    assert G._globbed(_w(cmd)[idx]) is want


def test_a_field_counts_by_its_pattern():
    assert G._globbed(G._field("a*", "a*")) is True
    assert G._globbed(G._field("a*", None)) is False
    assert G._globbed(G._field("[", "[[]")) is False


def test_known_values_decide_a_variable():
    ctx = G._Ctx("")
    ctx.assign("P", ["zz*.none"], False)
    ctx.assign("Q", ["plain"], False)
    assert G._globbed(_w("x $P")[1], None, ctx) is True
    assert G._globbed(_w("x $Q")[1], None, ctx) is False
    assert G._globbed(_w('x "$P"')[1], None, ctx) is False
