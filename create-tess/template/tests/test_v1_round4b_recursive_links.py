r"""
v1.0.x round 4b (Reid, fix/v1-n1-gaps @ 629f63d): Z1, E1 and U3.

Z1  zsh recursive glob steps and links. Measured on zsh 5.9: a plain `**/`
    step never enters a link, a `***/` step follows links, and any other
    step that names a link (`**/<link>/...`, a glob such as `**/l*/...`, or
    a final step with a trailing `/`) enters it. Bash 3.2 (no globstar)
    reads `**` as `*`: one step that enters a link one level down. The gate walked the tree
    without following links and reported a complete listing, so a protected
    file reached only through a link was never checked. Now a listing the
    shell would continue through a link is marked cut short, and the
    command asks (Claude) / is refused (Codex). Only the steps `**` and
    `***` recurse; a step that merely holds `**` (`x**`, `.**`) is one step
    in zsh and is read both ways. Every non-control case below is allow x3
    on 629f63d, and the real shell writes the protected file.
E1  A function call's argument with several fields: a listing cut short on
    any field (not only the last) makes the positional parameters unknown.
U3  An array assignment after `{`, `!`, `if`, `then`, `else`, `elif`, `do`,
    `while`, `until` (and in a function body) no longer reads as a `(` in a
    command's arguments. Nothing else moves.

Decisions: (claude default, claude acceptEdits, codex). @W is a folder
outside the project holding links at depth 2 and 3 to the project's
.claude folder, the project root and the home folder; @P the project; @H
the home.
"""

from __future__ import annotations

import os

import pytest

from test_v1_n1_n3 import ALLOW, ASK, DENY, G, _all, _env, proj  # noqa: F401 - fixtures

EVIL = '{"disableAllHooks":true}'


@pytest.fixture(scope="module")
def W(proj):  # noqa: F811
    root, home = proj
    w = root.parent / "W4"
    if w.exists():
        return w
    (w / "x").mkdir(parents=True)
    os.symlink(str(root / ".claude"), str(w / "x" / "lk"))  # depth 2, to .claude
    (w / "a" / "b").mkdir(parents=True)
    os.symlink(str(root / ".claude"), str(w / "a" / "b" / "lk"))  # depth 3, to .claude
    (w / "p" / "q").mkdir(parents=True)
    os.symlink(str(root), str(w / "p" / "q" / "lp"))  # depth 3, to the project root
    (w / "h1" / "h2").mkdir(parents=True)
    os.symlink(str(home), str(w / "h1" / "h2" / "hl"))  # depth 3, to the home folder
    (w / "r-0" / "q").mkdir(parents=True)
    os.symlink(str(root), str(w / "r-0" / "q" / "lp"))  # below a run-time spelling
    (w / "d1").mkdir()
    os.symlink(str(root / ".claude"), str(w / "d1" / "lc"))  # depth 1: bash reads `**` as `*`
    (w / "evil2").mkdir()
    (w / "evil2" / "settings.local.json").write_text(EVIL)
    (w / "docs").mkdir()
    (w / "docs" / "a.md").write_text("a\n")
    (root / ".claude" / "settings.local.json").write_text("{}\n")
    (home / ".gitconfig").write_text("[user]\n\tname = x\n")
    return w


def _fill(cmd, proj, w):  # noqa: F811
    out = cmd.replace("@P", str(proj[0])).replace("@H", str(proj[1]))
    return out if w is None else out.replace("@W", str(w))


def _ids(rows):
    return [r[0] for r in rows]


# Z1: allow x3 on 629f63d; zsh writes the protected file (Reid's probes and
# the rest of the class).
Z1 = [
    ("triple-rm-settings", "rm -f @W/***/settings.local.json", ASK),
    ("triple-redirect-settings", "echo '{}' > @W/***/settings.local.json", ASK),
    ("triple-cp-settings", "cp @W/evil2/settings.local.json @W/***/settings.local.json", ASK),
    ("triple-brain", "echo x > @W/***/zz.py", ASK),
    ("double-named-link-depth3", "echo '{}' > @W/**/lk/settings.local.json", ASK),
    ("triple-root-brain", "echo x > @W/***/brain/zz.py", ASK),
    ("triple-root-tessctl", "echo x > @W/***/tessctl", ASK),
    ("triple-below-literal", "echo '{}' > @W/x/***/settings.local.json", ASK),
    ("cd-then-triple", "cd @W && rm -f ***/settings.local.json", ASK),
    ("double-named-root-tessctl", "echo x > @W/**/lp/tessctl", ASK),
    ("double-named-root-guardrails", "echo x > @W/**/lp/conductor/guardrails.md", ASK),
    ("triple-root-workflow", "echo x > @W/***/.github/workflows/ci.yml", ASK),
    ("triple-root-manifest", "echo x > @W/***/tess.manifest.json", ASK),
    ("double-named-root-rm-brain", "rm -rf @W/**/lp/scripts/brain", ASK),
    ("triple-home-gitconfig", "echo x >> @W/***/.gitconfig", ASK),
    ("double-named-home-gitconfig", "echo x >> @W/**/hl/.gitconfig", ASK),
    # the rest of the class
    ("double-glob-named-link", "echo x > @W/**/l[p]/tessctl", ASK),
    ("double-star-named-link", "echo x > @W/**/l*/tessctl", ASK),
    ("double-glob-named-home", "echo x >> @W/**/h?/.gitconfig", ASK),
    ("triple-mid-pattern", "echo x > @W/p/***/tessctl", ASK),
    ("double-then-triple", "echo x > @W/**/***/tessctl", ASK),
    ("one-level-step-holding-stars", "echo x > @W/p***/q/lp/tessctl", ASK),
    ("chmod-triple-brain", "chmod +x @W/***/brain/*.py", ASK),
    # bash without globstar: `**` is `*`, one step that enters a link at depth 1
    ("bash-double-depth1-link", "rm -f @W/d1/**/settings.local.json", ASK),
    ("bash-triple-depth1-link", "echo '{}' > @W/d1/***/settings.local.json", ASK),
]

# Already refused on 629f63d (the suffix backstop, a same-command link, the
# literal spelling, the git-config route): unchanged.
STILL = [
    ("same-command-link", "ln -s @P/.claude @W/x/k2 && echo '{}' > @W/***/settings.local.json", DENY),
    ("triple-root-claude-spelled", "echo '{}' > @W/***/.claude/settings.local.json", ASK),
    ("triple-root-lock", "echo x > @W/***/.tess/tess.lock", ASK),
    ("triple-root-githooks", "echo x > @W/***/.git/hooks/pre-commit", ASK),
    ("triple-root-gate", "echo x > @W/***/.claude/hooks/tess-gate.py", ASK),
    ("literal-home-gitconfig", "echo x >> @W/h1/h2/hl/.gitconfig", DENY),
    ("gitconfig-tool", "git config --global core.hooksPath /tmp/x", DENY),
    ("double-trailing-slash-rm", "rm -rf @W/**/lk/", DENY),
]

# No new prompt: zsh's plain `**/` does not enter a link, a final step that
# names a link without a trailing `/` names the link itself, and a recursive
# read through no link at all.
QUIET = [
    ("double-no-named-link", "rm -f @W/**/settings.local.json", ALLOW),
    ("double-list-md", "ls @W/**/*.md", ALLOW),
    ("double-final-link-listed", "ls -d @W/**/lp", ALLOW),
    ("double-grep", "grep -n TODO @W/**/*.md", ALLOW),
    ("quoted-double-to-a-tool", "npx prettier --check '@W/**/*.md'", ALLOW),
]


@pytest.mark.parametrize("cid,cmd,want", Z1, ids=_ids(Z1))
def test_z1_recursive_glob_through_a_link_fails_safe(proj, W, cid, cmd, want):  # noqa: F811
    assert _all(proj, _fill(cmd, proj, W)) == want, cid


@pytest.mark.parametrize("cid,cmd,want", STILL, ids=_ids(STILL))
def test_z1_neighbours_already_refused_are_unchanged(proj, W, cid, cmd, want):  # noqa: F811
    assert _all(proj, _fill(cmd, proj, W)) == want, cid


@pytest.mark.parametrize("cid,cmd,want", QUIET, ids=_ids(QUIET))
def test_z1_recursive_globs_that_cross_no_link_stay_allowed(proj, W, cid, cmd, want):  # noqa: F811
    assert _all(proj, _fill(cmd, proj, W)) == want, cid


def test_z1_run_time_part_before_a_recursive_step_asks(proj, W):  # noqa: F811
    assert _all(proj, _fill('true; echo x > "@W/r-$?"/**/lp/tessctl', proj, W)) == ASK
    assert _all(proj, _fill('true; echo x > "@W/r-$?"/***/tessctl', proj, W)) == ASK


# zsh 5.9 and bash 3.2, measured: which links each pattern's walk goes on through.
@pytest.mark.parametrize("names,pats,trail,want", [
    (["a", "b", "lk"], ["**", "f"], False, False),         # `**/` never enters a link
    (["lk"], ["**", "f"], False, True),                    # ... but bash reads `**` as `*`
    (["a", "b", "lk"], ["***", "f"], False, True),         # `***/` does
    (["a", "b", "lk"], ["**", "lk", "f"], False, True),    # a later step names it
    (["a", "b", "lk"], ["**", "l?", "f"], False, True),    # ... as a glob
    (["a", "b", "lk"], ["**", "lk"], False, False),        # the last step names the link itself
    (["a", "b", "lk"], ["**", "lk"], True, True),          # ... unless a `/` follows
    (["a", "b", "lk"], ["**", "zz", "f"], False, False),   # a step that does not fit
    (["a", ".h", "lk"], ["***", "f"], False, True),        # hidden folders too (GLOB_DOTS, f8)
    (["p", "q", "lp"], ["p***", "q", "lp", "f"], False, True),  # `p***` is one step
    (["x", "lk"], ["x", "***", "f"], False, True),
])
def test_link_crossed_matches_zsh(names, pats, trail, want):
    assert G._link_crossed(names, pats, trail) is want


@pytest.mark.parametrize("names,pats,want", [
    ([".claude", "settings.json"], [".**", "settings.json"], "full"),  # `.**` is `.*` in zsh
    (["xa", "f"], ["x**", "f"], "full"),                                # `x**` is `x*`
    (["xa", "yb", "f"], ["x**", "f"], "full"),                          # and read as recursive too
    (["a", "b", "f"], ["***", "f"], "full"),                            # `***` recurses
])
def test_steps_holding_stars_match_both_readings(names, pats, want):
    assert G._parts_match(names, pats) == want


def test_a_recursive_listing_that_crosses_a_link_is_marked_cut_short(W):
    found = G._glob(str(W), "***/tessctl")
    assert found.truncated
    found = G._glob(str(W), "**/lp/tessctl")
    assert found.truncated
    found = G._glob(str(W), "**/*.md")
    assert not found.truncated and [os.path.basename(f) for f in found] == ["a.md"]


def test_pattern_hit_reads_a_hidden_step_holding_stars_as_one_step(proj):  # noqa: F811
    root = proj[0]
    assert G._pattern_hit(root, str(root), ".**/settings.json") is not None


# ====================================================================== E1
def test_e1_a_cut_short_listing_on_an_earlier_field_makes_arguments_unknown(proj, monkeypatch):  # noqa: F811
    """One argument with two fields: the first field's listing is cut short
    (the walk budget), the last one is complete. The function body must see
    unknown positional parameters, never the partial list."""
    real = G._glob

    def glob(cwd, pat, limit=None):
        if pat == "first*":
            cut = G._Matches(["first-a"])
            cut.truncated = True
            return cut
        return real(cwd, pat, limit)

    monkeypatch.setattr(G, "_glob", glob)
    monkeypatch.setattr(G, "_word_fields",
                        lambda w, cwd, ctx, *a, **k: ([[("first*", "first*"), ("second", None)]], None))
    seen = []
    monkeypatch.setattr(G, "_walk", lambda root, body, *a, **k: (seen.append(ctx.argv), (None, []))[1])
    root = proj[0]
    ctx = G._Ctx("f x")
    ctx.funcs["f"] = []
    G._call_function(root, str(root), "f", [G._mkword([("raw", "x")])], G.Verdict(), "f x", 0, ctx)
    assert seen == [None]


# ====================================================================== U3
U3 = [
    ("then-array", "if true; then arr=(a b); fi; echo ok", ALLOW),
    ("do-array", "for i in 1 2; do arr=(a b); done; echo ok", ALLOW),
    ("brace-array", "{ arr=(1 2); }; echo ok", ALLOW),
    ("function-body-array", "f() { arr=(1 2); }; f", ALLOW),
    ("function-body-local-array", "f() { local x=(1 2); echo $x; }; f", ALLOW),
    ("else-array", "if false; then :; else arr=(a); fi", ALLOW),
    ("while-body-array", "while false; do arr+=(a); done", ALLOW),
    # 1.0.x (Reid D4): the rest of the lead words U3 skips, each documented
    ("if-condition-array", "if arr=(a b); then :; fi", ALLOW),
    ("elif-condition-array", "if false; then :; elif arr=(a); then :; fi", ALLOW),
    ("while-condition-array", "while arr=(a); do break; done", ALLOW),
    ("until-condition-array", "until arr=(a); do :; done", ALLOW),
    ("bang-array", "! arr=(a b); echo ok", ALLOW),
]
# Still a `(` in a command's arguments after the same reserved words.
U3_STILL = [
    ("then-argument-paren", "if true; then echo (a|b); fi", ASK),
    ("brace-argument-paren", "{ ls *(e:x:); }", ASK),
    ("do-argument-paren", "for i in 1; do rm -f @P/(CLAUDE|x).md; done", ASK),
    ("then-command-then-array", "if true; then echo arr=(a); fi", ASK),
    # 1.0.x (Reid D4): the extra lead words keep the plain-position decision
    ("if-condition-argument-paren", "if ls *(e:x:); then :; fi", ASK),
    ("bang-argument-paren", "! ls *(e:x:)", ASK),
    ("while-condition-substitution-array", "while arr=($(cat x)); do break; done", ASK),
]


@pytest.mark.parametrize("cid,cmd,want", U3, ids=_ids(U3))
def test_u3_array_assignment_after_reserved_words_is_allowed(proj, cid, cmd, want):  # noqa: F811
    assert _all(proj, cmd) == want, cid


@pytest.mark.parametrize("cid,cmd,want", U3_STILL, ids=_ids(U3_STILL))
def test_u3_a_paren_in_arguments_after_reserved_words_still_asks(proj, cid, cmd, want):  # noqa: F811
    assert _all(proj, _fill(cmd, proj, None) if "@" in cmd else cmd) == want, cid
