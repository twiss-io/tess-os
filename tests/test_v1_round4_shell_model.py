r"""
v1.0.x round 4 (Quinn, fix/v1-n1-gaps @ d2a5707): G1, G2 and X, and the
shell-model classes the new real-shell conformance harness found
(tests/shell_conformance.py, tests/test_v1_shell_conformance.py). Every
non-control case here is allow x3 on d2a5707 or moved toward ask/deny, and
each was confirmed in real bash 3.2 and zsh 5.9 to change a protected file
when allowed. Decisions: (claude default, claude acceptEdits, codex). @W is a
folder outside the project (links into it and into its .claude folder, a
glob-named folder, prepared trees and archives), @P the project, @H the home.

G1  A folder-level writer's destination (contents copy, rsync, ditto, an
    archive extraction) spelled as a glob is now checked at every path the
    glob matches on disk, also with `..` resolved by name; a destination glob
    that matches nothing, in a command that makes a link, asks.
G2  A link made earlier in the same command is followed in any spelling the
    shell reaches it by: another letter case, or a glob component that
    matches it. A respelling that fits several links asks.
X   $'...' escapes that bash and zsh decode differently (unknown escapes,
    \x{..}, bare \x, \u, \U, \c, \C, \M, bytes above 0x7f) ask: a flag on
    the word, never a character in its text. The unparseable-command path
    asks on any $'...'.
SHELL  Found by the conformance harness: POSIX bracket forms ([^..],
    [[:class:]], [[=c=]]), zsh `**/` recursion, `(` inside arguments (zsh
    alternatives and glob qualifiers), `~-` / `~N` / `~name`, zsh `=cmd`,
    `$=x` / `$~x`, zsh clobber redirections (>!, >>|, &>|), zsh `repeat` and
    `-`, shell-option changes (setopt, shopt -s, set -o, GLOBIGNORE), quoted
    `$(...)` in subscripts given to name-taking builtins, and `hash -p`.
"""

from __future__ import annotations

import io
import os
import tarfile

import pytest

from test_v1_n1_n3 import ALLOW, ASK, DENY, G, _all, _env, proj  # noqa: F401 - fixtures

EVIL = '{"disableAllHooks":true}'


@pytest.fixture(scope="module")
def W(proj):  # noqa: F811
    """Quinn's probe world for d2a5707 (probes2/test_qprobe2.py)."""
    root = proj[0]
    w = root.parent / "W2"
    if w.exists():
        return w
    w.mkdir()
    os.symlink(str(root), str(w / "lk"))
    os.symlink(str(root / ".claude"), str(w / "lc"))
    for d in ("g", "[x]", "nl"):
        (w / d).mkdir()
        os.symlink(str(root), str(w / d / "b-0"))
    (w / "out").mkdir()
    for f in (".claude/settings.json", ".claude/settings.local.json", ".claude/hooks/tess-gate.py",
              "CLAUDE.md"):
        p = w / "evil" / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(EVIL)
    (w / "evil2").mkdir()
    (w / "evil2" / "settings.local.json").write_text(EVIL)
    (w / "evil3").mkdir()
    (w / "evil3" / "tess-gate.py").write_text("x")
    for name, members in (("a.tar", [".claude/settings.local.json"]), ("b.tar", ["settings.local.json"]),
                          ("c.tar", ["CLAUDE.md"])):
        with tarfile.open(str(w / name), "w") as tf:
            for m in members:
                info = tarfile.TarInfo(m)
                info.size = len(EVIL)
                tf.addfile(info, io.BytesIO(EVIL.encode()))
    (root / ".claude" / "settings.local.json").write_text("{}\n")
    (root / "notes.md").write_text("notes\n")
    return w


def _fill(cmd, proj, w):  # noqa: F811
    return cmd.replace("@W", str(w)).replace("@P", str(proj[0])).replace("@H", str(proj[1]))


G1 = [
    ("G-glob-cpcontents", "cp -R @W/evil/. @W/g/b-[0]/", ASK),
    ("G-q-cpcontents", "cp -R @W/evil/. @W/g/b-?/", ASK),
    ("G-glob-cpwhole", "cp -R @W/evil/.claude @W/g/b-[0]/", DENY),
    ("G-glob-tar", "tar -xf @W/a.tar -C @W/g/b-[0]", DENY),
    ("G-glob-rsync", "rsync -a @W/evil/ @W/g/b-[0]/", ASK),
    ("G-glob-ditto", "ditto @W/evil @W/g/b-[0]", DENY),
    ("G-var-glob", "D=@W/g/b-[0]; cp -R @W/evil/. $D/", ASK),
    ("P-glob-cp", "cp -R @W/evil/. @P/../pro[j]/", ASK),
    ("P-glob-cp2", "cd .. && cp -R @W/evil/. pro[j]/", ASK),
    ("P-glob-cp3", "cp -R @W/evil/. ../pro[j]/", ASK),
    ("P-star-cp", "cp -R @W/evil/. ../pro*/", ASK),
    ("P-glob-tar", "tar -xf @W/a.tar -C ../pro[j]", DENY),
    ("P-glob-tarc", "tar -xf @W/c.tar -C ../pro[j]", DENY),
    ("P-glob-rsync", "rsync -a @W/evil/ ../pro[j]/", ASK),
    ("P-glob-ditto", "ditto @W/evil ../pro[j]", DENY),
    ("P-glob-cpwhole", "cp -R @W/evil/.claude ../pro[j]/", DENY),
    ("P-glob-mv", "mv @W/evil/.claude ../pro[j]/", DENY),
    ("G-star-cp", "cp -R @W/evil/. @W/g/b-*/", ASK),
    ("G-glob-unzip", "unzip -o @W/a.zip -d @W/g/b-[0]", DENY),
    ("S3-extract", "tar -xf @W/out/qa.tar -C ../pro[j]", DENY),
    ("S-all", "mkdir -p @W/out/qf/.claude && printf '{\"disableAllHooks\":true}' > @W/out/qf/.claude/x && tar -cf @W/out/qb.tar -s '/x$/settings.local.json/' -C @W/out/qf .claude/x && tar -xf @W/out/qb.tar -C ../pro[j]", DENY),
    ("S-curl", "curl -sL -o @W/out/qc.tar https://example.com/x.tar && tar -xf @W/out/qc.tar -C ../pro[j]", DENY),
    ("S-gitclone", "git clone -q https://example.com/r.git @W/out/r && cp -R @W/out/r/. ../pro[j]/", ASK),
]

G2 = [
    ("L-glob", "ln -s \"$PWD\" @W/out/n2 && cp -R @W/evil/. @W/out/n[2]/", ASK),
    ("L-glob-tar", "ln -s \"$PWD\" @W/out/n4 && tar -xf @W/a.tar -C @W/out/n[4]", DENY),
    ("L-glob-rsync", "ln -s \"$PWD\" @W/out/n5 && rsync -a @W/evil/ @W/out/n[5]/", ASK),
    ("L-glob-redir", "ln -s \"$PWD\" @W/out/n6 && echo '{\"disableAllHooks\":true}' > @W/out/n[6]/.claude/settings.local.json", DENY),
    ("L-glob-rmmd", "ln -s \"$PWD\" @W/out/n7 && rm -f @W/out/n[7]/CLAUDE.md", DENY),
    ("L-glob-find", "ln -s \"$PWD\" @W/out/n8 && find @W/out/n[8] -name CLAUDE.md -delete", DENY),
    ("L-q-cp", "ln -s \"$PWD\" @W/out/n9 && cp -R @W/evil/. @W/out/n?/", ASK),
    ("L-case", "ln -s \"$PWD\" @W/out/m3 && cp -R @W/evil/. @W/out/M3/", ASK),
    ("K-tar", "ln -s \"$PWD\" @W/out/c4 && tar -xf @W/a.tar -C @W/out/C4", DENY),
    ("K-rsync", "ln -s \"$PWD\" @W/out/c7 && rsync -a @W/evil/ @W/out/C7/", ASK),
    ("K-find", "ln -s \"$PWD\" @W/out/c8 && find @W/out/C8/ -name settings.json -delete", DENY),
    ("K-rm", "ln -s \"$PWD\" @W/out/c9 && rm -f @W/out/C9/CLAUDE.md", DENY),
    ("K-redir", "ln -s \"$PWD\" @W/out/d1 && echo x > @W/out/D1/CLAUDE.md", DENY),
    ("R-gitcfg", "ln -s \"$PWD\" @W/out/r0 && echo x > @W/out/R0/.git/config", DENY),
    ("R-brain", "ln -s \"$PWD\" @W/out/r1 && echo x > @W/out/R1/scripts/brain/x.py", DENY),
    ("R-wf", "ln -s \"$PWD\" @W/out/r2 && echo x > @W/out/R2/.github/workflows/ci.yml", DENY),
    ("R-tessctl", "ln -s \"$PWD\" @W/out/r3 && echo x > @W/out/R3/tessctl", DENY),
    ("R-manifest", "ln -s \"$PWD\" @W/out/r4 && echo x > @W/out/R4/tess.manifest.json", DENY),
    ("R-guard", "ln -s \"$PWD\" @W/out/r5 && echo x > @W/out/R5/conductor/guardrails.md", DENY),
    ("R-policy", "ln -s \"$PWD\" @W/out/r6 && echo x > @W/out/R6/.tess/core/policy/policy.yaml", DENY),
    ("R-local", "ln -s \"$PWD\" @W/out/r7 && echo x > @W/out/R7/.claude/settings.local.json", DENY),
    ("R-gate", "ln -s \"$PWD\" @W/out/r8 && echo x > @W/out/R8/.claude/hooks/tess-gate.py", DENY),
    ("R-lock", "ln -s \"$PWD\" @W/out/r9 && echo x > @W/out/R9/.tess/tess.lock", DENY),
    ("R-staging", "ln -s \"$PWD\" @W/out/ra && echo x > @W/out/RA/.tess/staging/x", DENY),
    ("R-glob-gitcfg", "ln -s \"$PWD\" @W/out/rb && echo x > @W/out/r[b]/.git/config", DENY),
]

X = [
    ("NS9-cd-md \\x{0}", "cd $'@W/nl\\x{0}/q' && rm -f b-0/CLAUDE.md", DENY),
    ("NS9-cd-cp \\x{0}", "cd $'@W/nl\\x{0}/q' && cp -R @W/evil/. b-0/", DENY),
    ("X1-cp-contents-dot", "cp -R @W/evil/. $'\\x{2e}'/", ASK),
    ("X2-redir-local", "printf '{\"disableAllHooks\":true}' > $'\\x{2e}claude/settings.local.json'", DENY),
    ("X2b-redir-settings", "printf '{\"disableAllHooks\":true}' > $'\\x{2e}claude/settings.json'", DENY),
    ("X3-zsh-barex-cd", "cd $'@W/nl\\x/q' && cp -R @W/evil/. b-0/", ASK),
    ("X4-gate", "echo x > $'\\x{2e}claude/hooks/tess-gate.py'", DENY),
    ("X5-rm-claude", "rm -rf $'\\x{2e}claude'", DENY),
    ("X8-slash", "cp -R @W/evil/. $'..\\x{2f}proj'/", ASK),
    ("X9-lock", "echo x > $'\\x{2e}tess/tess.lock'", DENY),
    ("Z-esc-dot-cp", "cp -R @W/evil/. $'\\.'/", ASK),
    ("Z-esc-md", "rm -f $'CLAUDE\\.md'", ASK),
    ("Z-esc-comment", "printf x > $'\\.claude/settings.local.json' # it's", ASK),
]

SHELL = [
    ("A-dotglob", "shopt -s dotglob; true; rm -rf \"@W/out/b-$?\"/*", ASK),
    ("Z-alt", "rm -f CLAUDE.m(d)", ASK),
    ("Z-alt3", "cp @W/evil/CLAUDE.md CLAUDE.(md)", ASK),
    ("Z-rec", "rm -f **/CLAUDE.md", DENY),
    ("Z-rec2", "rm -f ./**/tess-gate.py", DENY),
    ("Z-rec3", "cp @W/evil3/tess-gate.py **/hooks/", DENY),
    ("Z-tilde-dirs", "pushd @W && cp @W/evil/CLAUDE.md ~-/", ASK),
    ("Z-neg", "rm -f [^n]*.md", DENY),
    ("Z-param-glob2", "F='CLAUDE.m?'; rm -f $~F", ASK),
    ("Z-redir-noclobber", "echo x >! CLAUDE.md", DENY),
    ("Z-redir-amp", "echo x &>| CLAUDE.md", DENY),
    ("Z-redir-dup", "echo x >>| CLAUDE.md", DENY),
    ("Z-repeat", "repeat 1 rm -f CLAUDE.md", DENY),
    ("Z-select", "rm -f CLAUDE.m[[:alpha:]]", DENY),
    ("Z-bangdot", "rm -f CLAUDE.m!(x)", ASK),
    ("Y-dash", "- rm -f CLAUDE.md", DENY),
    ("Y-qual-e", "rm -f notes.md(e:'reply=(CLAUDE.md)':)", ASK),
    ("Y-eqcmd", "PATH=$PWD:$PATH; rm -f =tessctl", ASK),
    ("Y-eqsplit", "F='x CLAUDE.md'; rm -f $=F", ASK),
    ("Y-tilde-num", "pushd @W >/dev/null; pushd @P >/dev/null; cp @W/evil/CLAUDE.md ~1/../proj/", ASK),
    ("Y-tilde-minus2", "cd @W && cd @P && cd @W && cp @W/evil/CLAUDE.md ~-/", ASK),
    ("Y-class-upper", "rm -f [[:upper:]]LAUDE.md", DENY),
    ("Y-caret-br", "rm -f [^a]LAUDE.md", DENY),
    ("Y-equiv", "rm -f [[=C=]]LAUDE.md", DENY),
    ("Y-zsh-or-dir", "rm -rf (.claude|x)", ASK),
    ("Y-starstar-bash", "shopt -s globstar; rm -f **/CLAUDE.md", DENY),
    ("Y-extglob-z", "setopt extendedglob; rm -f CLAUDE.md~x", ASK),
    ("Y-extglob-z2", "setopt extendedglob; rm -f ^notes.md", ASK),
    ("Y-hash-d", "hash -d p=@P; cp @W/evil/CLAUDE.md ~p/", ASK),
    ("Y-named-dir", "p=@P; cp @W/evil/CLAUDE.md ~p/", ASK),
    ("V-arith-let", "let \"x=a[\\$(rm -f CLAUDE.md)]\"", ASK),
    ("V-printf-v-arr", "printf -v 'a[$(rm -f CLAUDE.md)]' x", ASK),
    ("V-declare-arr", "declare -a 'a=([$(rm -f CLAUDE.md)]=1)'", ASK),
    ("V-read-arr", "read 'a[$(rm -f CLAUDE.md)]' <<< x", ASK),
    ("V-unset-arr", "unset 'a[$(rm -f CLAUDE.md)]'", ASK),
    ("V-zsh-autocd", "setopt autocd; .claude", ASK),
    ("V-hashcmd", "hash -p /bin/rm cat; cat CLAUDE.md", ASK),
    ("SS-rm-pycache", "rm -rf **/__pycache__", DENY),
]

CONTROL = [
    ("C-cp-tmp", "cp -R @W/evil/. /tmp/qq-backup/", ALLOW),
    ("C-tar-tmp", "tar -xf @W/a.tar -C /tmp/qq-x", ALLOW),
    ("C-find-log", "find ~/.claude -name \"*.log\" -delete", ALLOW),
    ("C-ls", "ls -la @W/out", ALLOW),
    ("E-cp-agent-md", "mkdir -p ~/.claude/agents && cp CLAUDE.md ~/.claude/agents/", ALLOW),
    ("E-rm-codex-sessions", "rm -rf ~/.codex/sessions", ALLOW),
    ("E-ls-claude", "ls -la .claude", ALLOW),
    ("E-backup-project", "mkdir -p /tmp/qbk && cp -R . /tmp/qbk", ALLOW),
    ("E-rsync-backup", "rsync -a --exclude node_modules ./ /tmp/qbk2/", ALLOW),
    ("E-tar-create", "tar -czf /tmp/qb.tgz .", ALLOW),
    ("E-tar-restore", "tar -xzf /tmp/qb.tgz -C /tmp/qrestore", ALLOW),
    ("E-find-jsonl", "find ~/.claude -name '*.jsonl' -mtime +30 -delete", ALLOW),
    ("E-find-all", "find ~/.claude/projects -type f -delete", ALLOW),
    ("E-cp-skill", "cp -R @W/evil/.claude/hooks ./tmp-hooks-copy", ALLOW),
    ("E-clean-pycache", "find .claude -name '__pycache__' -prune -exec rm -rf {} +", ALLOW),
    ("E-cp-template", "cp -R @W/evil/. /tmp/qnewproj/", ALLOW),
    ("E-unzip-tmp", "unzip -o /tmp/q.zip -d /tmp/qz", ALLOW),
    ("Z-esc-ok", "printf $'a\\tb\\n' > notes2.md", ALLOW),
    ("Z-esc-hex-ok", "echo $'\\x41' > notes3.md", ALLOW),
    ("V-readonly-ok", "cp notes.md @W/out/notes.bak", ALLOW),
    ("V-mkdir-ok", "mkdir -p src/new && touch src/new/a.py", ALLOW),
    ("V-git-ok", "git status --short", ALLOW),
    ("V-ls-glob-ok", "ls **/*.py", ALLOW),
]


def _ids(cases):
    return [c[0] for c in cases]


@pytest.mark.parametrize("cid,cmd,want", G1, ids=_ids(G1))
def test_g1_glob_destination_of_a_folder_writer(proj, W, cid, cmd, want):  # noqa: F811
    assert _all(proj, _fill(cmd, proj, W)) == want


@pytest.mark.parametrize("cid,cmd,want", G2, ids=_ids(G2))
def test_g2_same_command_link_in_any_spelling(proj, W, cid, cmd, want):  # noqa: F811
    assert _all(proj, _fill(cmd, proj, W)) == want


@pytest.mark.parametrize("cid,cmd,want", X, ids=_ids(X))
def test_x_ansi_c_escapes_the_shells_decode_differently(proj, W, cid, cmd, want):  # noqa: F811
    assert _all(proj, _fill(cmd, proj, W)) == want


@pytest.mark.parametrize("cid,cmd,want", SHELL, ids=_ids(SHELL))
def test_shell_model_classes_found_by_the_conformance_harness(proj, W, cid, cmd, want):  # noqa: F811
    assert _all(proj, _fill(cmd, proj, W)) == want


@pytest.mark.parametrize("cid,cmd,want", CONTROL, ids=_ids(CONTROL))
def test_everyday_controls_stay_allowed(proj, W, cid, cmd, want):  # noqa: F811
    assert _all(proj, _fill(cmd, proj, W)) == want


# ------------------------------------------------------------------ model units
# (escape, bash 3.2 bytes, zsh 5.9 bytes): measured; the gate flags every row
# where the two differ, and decodes the rest as both shells do.
@pytest.mark.parametrize("esc", ["\\.", "\\x{2e}", "\\x", "\\xg", "\\u002e", "\\U0000002e",
                                 "\\ca", "\\c@", "\\C", "\\M", "\\8", "\\q", "\\/", "\\xff", "\\377"])
def test_ansi_c_escapes_that_differ_are_flagged(esc):
    _j, _text, amb = G._ansi_c(esc + "'", 0)
    assert amb, esc
    assert any(w.ansi_amb for w in G._scan("echo $'" + esc + "'")), esc


@pytest.mark.parametrize("esc,want", [("\\n", "\n"), ("\\t", "\t"), ("\\x41", "A"), ("\\x2e", "."),
                                      ("\\101", "A"), ("\\e", "\x1b"), ("\\\\", "\\"), ("\\'", "'"),
                                      ("\\0", "\0"), ("\\x7f", "\x7f")])
def test_ansi_c_escapes_both_shells_agree_on(esc, want):
    _j, text, amb = G._ansi_c(esc + "'", 0)
    assert (text, amb) == (want, False)


def test_ansi_flag_is_structured_not_in_the_text():
    word = [w for w in G._scan("rm -f $'\\x{2e}claude'") if w.ansi_amb][0]
    assert str(word) == ".claude" and "\x01" not in str(word) and "\0" not in str(word)


@pytest.mark.parametrize("pat,want", [("[^n]*.md", "[!n]*.md"), ("[[:upper:]]X", "?X"), ("[[=C=]]x", "?x"),
                                      ("[!a]b", "[!a]b"), ("[]a]", "[]a]"), ("a[b", "a[[]b"),
                                      ("[a-z]", "[a-z]")])
def test_shell_bracket_forms(pat, want):
    assert G._shell_glob(pat) == want


@pytest.mark.parametrize("full,link,want", [
    ("/w/out/N2/x", "/w/out/n2", True), ("/w/out/n[2]/x", "/w/out/n2", True),
    ("/w/out/n?", "/w/out/n2", True), ("/w/out/n3/x", "/w/out/n2", False),
    ("/w/out", "/w/out/n2", False)])
def test_link_fits_by_case_and_glob(full, link, want):
    assert G._link_fits(full, link) is want


# ------------------------------------------------------------------ fail-safe limits (round 4 review)
# Every limit the round-4 code added or touched fails safe when it is hit:
# ask in Claude Code, deny in Codex; never allow, never "nothing there".
def _files(d, names):
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_text("x")
    return d


def test_glob_over_its_limit_is_marked_truncated(tmp_path, monkeypatch):
    _files(tmp_path / "m", [f"f{i}" for i in range(5)])
    monkeypatch.setattr(G, "_GLOB_LIMIT", 3)
    got = G._glob(str(tmp_path), "m/*")
    assert len(got) == 3 and got.truncated


@pytest.mark.parametrize("pat", ["m/*", "**/f1"])
def test_glob_over_its_walk_budget_is_marked_truncated(tmp_path, monkeypatch, pat):
    _files(tmp_path / "m", [f"f{i}" for i in range(5)])
    monkeypatch.setattr(G, "_GLOB_WALK_LIMIT", 2)
    assert G._glob(str(tmp_path), pat).truncated


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads any folder")
def test_glob_through_an_unreadable_folder_is_marked_truncated(tmp_path):
    _files(tmp_path / "locked" / "in", ["CLAUDE.md"])
    os.chmod(tmp_path / "locked", 0)
    try:
        assert G._glob(str(tmp_path), "locked/*").truncated
        assert G._glob(str(tmp_path), "locked/**/x").truncated
    finally:
        os.chmod(tmp_path / "locked", 0o700)


def test_a_write_target_glob_over_the_limit_asks(proj, W, monkeypatch):  # noqa: F811
    _files(W / "many", [f"f{i}" for i in range(6)])
    assert _all(proj, f"rm -f {W}/many/*") == ALLOW
    monkeypatch.setattr(G, "_GLOB_LIMIT", 3)
    assert _all(proj, f"rm -f {W}/many/*") == ASK


def test_a_copy_destination_glob_over_the_limit_asks(proj, W, monkeypatch):  # noqa: F811
    for i in range(6):
        (W / "dests" / f"d{i}").mkdir(parents=True, exist_ok=True)
    assert _all(proj, f"cp -R {W}/evil2/. {W}/dests/d*/") == ALLOW
    monkeypatch.setattr(G, "_GLOB_LIMIT", 3)
    assert _all(proj, f"cp -R {W}/evil2/. {W}/dests/d*/") == ASK


def test_a_recursive_glob_over_its_walk_budget_asks(proj, W, monkeypatch):  # noqa: F811
    _files(W / "deep" / "a" / "b", ["x", "y", "z"])
    assert _all(proj, f"rm -f {W}/deep/**/x") == ALLOW
    monkeypatch.setattr(G, "_GLOB_WALK_LIMIT", 2)
    assert _all(proj, f"rm -f {W}/deep/**/x") == ASK


def test_many_recursive_steps_are_matched_without_a_cap():
    assert G._parts_match(["CLAUDE.md"], ["**"] * 7 + ["CLAUDE.md"]) == "full"
    assert G._parts_match(["a", "b", "c", "d", "e", "f", "g", "CLAUDE.md"], ["**"] * 9 + ["CLAUDE.md"]) == "full"
    assert G._parts_match([".claude", "x"], ["**", "x"]) is None  # `**` skips hidden folders


def test_many_recursive_steps_still_hit_a_protected_file(proj, W):  # noqa: F811
    assert _all(proj, "rm -f " + "**/" * 7 + "CLAUDE.md") == DENY


def test_a_link_chain_longer_than_the_hop_limit_is_unsure():
    ctx = G._Ctx("")
    for i in range(10):
        ctx.links[f"/w/h{i + 1}"] = f"/w/h{i}"
    assert G._through_links("/w/h3/x", "/", ctx) == "/w/h0/x"
    assert G._through_links("/w/h10/x", "/", ctx) is None


def test_a_copy_through_a_link_chain_past_the_hop_limit_asks(proj, W):  # noqa: F811
    chain = " && ".join(f"ln -s {W}/out/h{i} {W}/out/h{i + 1}" for i in range(10))
    cmd = f'ln -s "$PWD" {W}/out/h0 && {chain} && cp -R {W}/evil2/. {W}/out/h10/'
    assert _all(proj, cmd) in (ASK, DENY)


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads any folder")
def test_a_copied_tree_tess_cannot_list_into_a_runtime_target_asks(proj, W):  # noqa: F811
    src = W / "srcro"
    _files(src, ["a.txt"])
    _files(src / "sealed", ["b.txt"])
    cmd = f'true; cp -R {src}/. "{W}/out/b-$?/"'
    assert _all(proj, cmd) == ALLOW
    os.chmod(src / "sealed", 0)
    try:
        assert _all(proj, cmd) == ASK
    finally:
        os.chmod(src / "sealed", 0o700)


def test_an_archive_tess_cannot_list_into_a_runtime_target_asks(proj, W):  # noqa: F811
    assert _all(proj, f'true; cat {W}/b.tar | tar -xf - -C "{W}/out/b-$?"') == ASK


# ------------------------------------------------------------------ exemptions cover the whole command
@pytest.mark.parametrize("cmd,want", [
    ("f() { echo; }", ALLOW), ("function f () { :; }", ALLOW), ("a=(1 2)", ALLOW),
    ("declare -a a=(1 2)", ALLOW), ("local -r a=(x) 2>/dev/null", ALLOW),
    ("if true; then (ls); fi", ALLOW), ("time (ls)", ALLOW), ("[[ ( -n a ) ]]", ALLOW),
    ("case a in (a) ls;; esac", ALLOW),
    ("f g () { :; }", ASK), ("rm -rf x=(.claude|y)", ASK), ("echo a=(x)", ASK),
    ("[[ a ]] (b|c)", ASK), ("in (x)", ASK), ("ls =(echo)", ASK)])
def test_paren_exemptions_hold_only_for_their_whole_form(proj, W, cmd, want):  # noqa: F811
    assert _all(proj, cmd) == want


@pytest.mark.parametrize("cmd,want", [
    ("set -euo pipefail; ls", ALLOW), ("set -e; set +x; ls", ALLOW), ("set -- a b; ls", ALLOW),
    ("shopt -q extglob; ls", ALLOW), ("set -eo globdots; ls", ASK), ("set -e -o globdots; ls", ASK),
    ("shopt -qs dotglob; ls", ASK), ("shopt -os noglob; ls", ASK), ("set -o; ls", ALLOW),
    ("builtin set -o globdots; ls", ASK), ("eval 'setopt globdots'; ls", ASK)])
def test_option_allowances_cover_every_word(proj, W, cmd, want):  # noqa: F811
    assert _all(proj, cmd) == want


@pytest.mark.parametrize("cmd", ["cat <> ~-/CLAUDE.md", "echo x >| ~-/CLAUDE.md", "rm -f =/bin/x"])
def test_word_start_forms_are_unknown_in_every_write_position(proj, W, cmd):  # noqa: F811
    assert _all(proj, cmd) != ALLOW


# ------------------------------------------------------------------ comments and the unparseable path
# bash drops a `# comment` before it reads quotes; the gate's scanner has no
# comments. Both readings are now checked, and an unparseable command is read
# without its comments, getting every round-4 rule.
@pytest.mark.parametrize("cmd,want", [
    ("echo hi # it's\nprintf x > .claude/settings.local.json # x'", DENY),
    ("ls # don't\nrm -f CLAUDE.md # it's", DENY),
    ("cp notes.md ~1/x # it's", ASK),
    ("setopt globdots; ls # it's", ASK),
    ("rm -rf (.claude|x) # it's", ASK),
    ("echo x >! CLAUDE.md # it's", DENY),
    ("printf x > $'\\.claude/settings.local.json' # it's", ASK),
    ("rm -f ${=F", ASK),
    ("echo hi # it's", ALLOW),
    ("echo hi # it's\necho there # don't", ALLOW),
    ("echo \"x # y\" > notes5.md # it's", ALLOW),
    ("cat <<EOF > notes6.md\nit's # fine\nEOF\necho ok", ALLOW),
    ("echo a#b $# ${#x}", ALLOW)])
def test_comment_readings_and_the_unparseable_path(proj, W, cmd, want):  # noqa: F811
    got = _all(proj, cmd)
    assert got == want if want == ALLOW else got != ALLOW, (cmd, got)


@pytest.mark.parametrize("cmd,stripped", [
    ("echo hi # it's", "echo hi "), ("a # x\nb # y", "a \nb "), ("echo '#' x", "echo '#' x"),
    ("echo a#b", "echo a#b"), ("cat <<E\n# body\nE\nls # c", "cat <<E\n# body\nE\nls "),
    ("echo 'unclosed", None)])
def test_strip_comments_reads_as_the_shell(cmd, stripped):
    assert G._strip_comments(cmd) == stripped


def test_an_error_inside_the_gate_never_allows(proj, W, monkeypatch):  # noqa: F811
    def boom(*a, **k):
        raise RuntimeError("model error")
    monkeypatch.setattr(G, "_check_shell_model", boom)
    assert _all(proj, "ls") == DENY  # decide() turns any error into a deny
