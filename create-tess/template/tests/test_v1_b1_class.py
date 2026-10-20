"""
v1.0.x QA (Quinn, fix/v1-n1-gaps @ 7de6eef, attempt 3): finding B1 and its
class, as tests that fail on 7de6eef and pass after the fix. Harness
(fixture, decisions, ALLOW/ASK/DENY): tests/test_v1_n1_n3.py. @W is a folder
outside the project.

B1  The "may be empty" mark of a run-time path part was a character inside
    the glob text, and a path can hold that character. A folder whose name
    holds it was skipped by the link walk, so a link inside it into the
    project went unseen. Now the mark is a separate piece of the shape (and
    so are the other in-band markers the gate carried: see SENTINELS).
B1 part 2 / backstop  An operation that ENDS on a folder that holds Tess's
    control files (.claude, .codex, .gemini, .tess, .tess/core, .tess/bin,
    .git/hooks) asks wherever the folders in front of it lead: delete, move,
    copy or extract into, link, change permissions. So does a copy, move or
    extraction that puts such a folder or file inside its target.
Same class  The commands that write into a folder they are given (tar/unzip
    -C/-d, ditto, cp -R/rsync into a folder, find -delete) followed links
    made earlier in the same command only for some spellings, and an
    extractor's or ditto's folder known only at run time was not checked.
"""

from __future__ import annotations

import os
import tarfile
import zipfile

import pytest

from test_v1_n1_n3 import ALLOW, ASK, DENY, G, _all, _env, proj  # noqa: F401 — fixtures

MARK = "\x01"  # the character 7de6eef used as its in-band "may be empty" mark


@pytest.fixture(scope="module")
def W(proj):  # noqa: F811
    root = proj[0]
    w = root.parent / "W"
    if w.exists():
        return w

    def link(path, target=root):
        path.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(str(target), str(path))

    link(w / "e2" / MARK / "b-0")          # a whole folder name that is the mark
    link(w / "e3" / ("q" + MARK) / "b-0")  # the mark inside a folder name
    link(w / "k" / "b-0")                  # a plain outside link into the project
    link(w / "g" / "[x]" / "b-0")          # a folder name that is also a glob
    link(w / "g3" / "x" / "b-0")           # a folder a value's glob matches
    link(w / "o9" / "lnk")
    (w / "o9" / "b-0").mkdir(parents=True)
    evil = w / "e" / "evil"
    (evil / ".claude").mkdir(parents=True)
    (evil / ".claude" / "settings.json").write_text('{"disableAllHooks":true}')
    (w / "e" / "plain" / "src").mkdir(parents=True)
    (w / "e" / "plain" / "src" / "a.txt").write_text("a")
    with tarfile.open(str(w / "e" / "h.tar"), "w") as tf:
        tf.add(str(evil / ".claude"), arcname=".claude")
    with tarfile.open(str(w / "e" / "plain.tar"), "w") as tf:
        tf.add(str(w / "e" / "plain" / "src"), arcname="src")
    with zipfile.ZipFile(str(w / "e" / "h.zip"), "w") as zf:
        zf.writestr(".claude/settings.json", '{"disableAllHooks":true}')
    return w


def _cmd(W, root, cmd):
    return cmd.replace("@W", str(W)).replace("@P", str(root))


def _never_allow(proj, W, cmd):  # noqa: F811
    got = _all(proj, _cmd(W, proj[0], cmd))
    assert got in (ASK, DENY), (cmd, got)
    return got


# ====================================================================== B1: the mark character in a path
B1_INPUTS = {
    "rm-claude-whole": 'true; rm -rf "@W/e2/"$\'\\x01\'"/b-$?/.claude"',
    "rm-claudemd-whole": 'true; rm -rf "@W/e2/"$\'\\x01\'"/b-$?/CLAUDE.md"',
    "rm-claude-raw": 'true; rm -rf "@W/e2/' + MARK + '/b-$?/.claude"',
    "rm-claude-mid": 'true; rm -rf "@W/e3/q"$\'\\x01\'"/b-$?/.claude"',
    "rm-claudemd-mid": 'true; rm -rf "@W/e3/q"$\'\\x01\'"/b-$?/CLAUDE.md"',
    "cp-into-claude": 'true; cp "@W/e/evil/.claude/settings.json" "@W/e2/"$\'\\x01\'"/b-$?/.claude/"',
    "mv-into-claude": 'true; mv "@W/e/plain/src/a.txt" "@W/e2/"$\'\\x01\'"/b-$?/.claude/"',
    "tar-into-claude": 'true; tar -xf "@W/e/h.tar" -C "@W/e2/"$\'\\x01\'"/b-$?/.claude"',
    "cp-into-claude-mid": 'true; cp "@W/e/evil/.claude/settings.json" "@W/e3/q"$\'\\x01\'"/b-$?/.claude/"',
}


@pytest.mark.parametrize("key", sorted(B1_INPUTS))
def test_b1_the_mark_character_in_a_folder_name_is_matched_as_itself(proj, W, key):  # noqa: F811
    assert _all(proj, _cmd(W, proj[0], B1_INPUTS[key])) == ASK, key


def test_b1_literal_spellings_stay_refused(proj, W):  # noqa: F811
    for cmd in ('rm -rf "@W/e2/"$\'\\x01\'"/b-0/.claude"', 'rm -rf "@W/e3/q"$\'\\x01\'"/b-0/.claude"',
                'cp "@W/e/evil/.claude/settings.json" "@W/e2/"$\'\\x01\'"/b-0/.claude/"'):
        assert _all(proj, _cmd(W, proj[0], cmd)) == DENY, cmd


def test_b1_shapes_carry_the_empty_part_out_of_band(proj, W):  # noqa: F811
    # No character a path can hold marks a part as possibly empty: the
    # "empty" piece is a separate object in the shape, never text.
    assert not hasattr(G, "_EMPTY_MARK")
    word = G._mkword([("lit", f"{W}/e2/{MARK}/b-"), ("dyn", "!"), ("lit", "/x")])
    shapes = G._runtime_shapes(word, str(proj[0]), G._Ctx(""))
    assert shapes and all(isinstance(sh, tuple) for sh in shapes)
    assert any(G._EMPTY in sh for sh in shapes)
    for sh in shapes:
        assert all(p is G._EMPTY or isinstance(p, str) for p in sh)
        segs = G._shape_segments(sh)
        assert any(MARK in t for t, _f in segs), segs  # the folder name keeps its character


@pytest.mark.parametrize("cmd", [
    # bash keeps a glob that matches nothing as written, so `[x]` is the folder `[x]`
    'true; rm -rf @W/g/[x]/b-$?/CLAUDE.md',
    'true; rm -rf @W/g/[x]/b-$?/.claude',
    'ln -s "$PWD" \'@W/e/[y]\' && true; rm -rf @W/e/[y]/CLAUDE.md$!',
    "X='[x]'; true; rm -rf @W/g3/$X/b-$?/CLAUDE.md",               # an unquoted value is a glob
])
def test_b1_class_a_glob_that_matches_nothing_is_walked_as_written(proj, W, cmd):  # noqa: F811
    assert _all(proj, _cmd(W, proj[0], cmd)) == ASK, cmd


# ====================================================================== sentinel audit
def test_sentinels_runtime_links_are_kept_apart_from_link_paths(proj):  # noqa: F811
    assert not hasattr(G, "_RUNTIME_LINK")
    ctx = G._Ctx("")
    G._mark_runtime_link(str(proj[0]), [], ctx)
    assert ctx.rt_links and all(not k.startswith("\0") for k in ctx.links)


def test_sentinels_a_nul_in_a_link_name_counts_as_unknown(proj, W):  # noqa: F811
    # bash cuts a value at NUL; Tess does not model that, so it never allows.
    _never_allow(proj, W, 'ln -s "$PWD" "@W/e/"$\'n\\x00x\' && rm -rf "@W/e/n/CLAUDE.md"')


def test_sentinels_dotdot_check_models_an_empty_part(proj, W):  # noqa: F811
    # `.$!.` is `..` when $! is empty (no background job yet).
    word = G._mkword([("lit", f"{W}/o9/b-"), ("dyn", "?"), ("lit", "/."), ("dyn", "!"),
                      ("lit", "./lnk/CLAUDE.md")])
    assert G._slash_free_runtime(word, str(proj[0]), G._Ctx("")) is False
    _never_allow(proj, W, 'true; rm -f "@W/o9/b-$?/.$!./lnk/CLAUDE.md"')


def test_sentinels_copy_message_names_its_source(proj, W):  # noqa: F811
    root = proj[0]
    v = G.Verdict()
    G.check_command(root, str(root), f"cp -R {W}/e/plain/src/. .", v)
    assert any("src/." in r for r in v.reasons) and not any("\0" in r for r in v.reasons)


# ====================================================================== backstop: the control folders
CONTROL_DIRS = (".claude", ".codex", ".gemini", ".tess", ".tess/core", ".tess/bin", ".git/hooks")
OPS = {
    "rm": 'true; rm -rf "@W/e/m-$?/{d}"',
    "rm-trailing-slash": 'true; rm -rf "@W/e/m-$?/{d}/"',
    "mv-away": 'true; mv "@W/e/m-$?/{d}" "@W/e/away"',
    "cp-into": 'true; cp "@W/e/evil/.claude/settings.json" "@W/e/m-$?/{d}/"',
    "cp-t": 'true; cp -t "@W/e/m-$?/{d}" "@W/e/evil/.claude/settings.json"',
    "rsync-into": 'true; rsync -a "@W/e/evil/.claude/" "@W/e/m-$?/{d}/"',
    "tar-into": 'true; tar -xf "@W/e/plain.tar" -C "@W/e/m-$?/{d}"',
    "unzip-into": 'true; unzip -o "@W/e/h.zip" -d "@W/e/m-$?/{d}"',
    "ln-over": 'true; ln -sfn "@W/e/evil" "@W/e/m-$?/{d}"',
    "chmod": 'true; chmod -R 000 "@W/e/m-$?/{d}"',
    "find-delete": 'true; find "@W/e/m-$?/{d}" -delete',
    "find-type-delete": 'true; find "@W/e/m-$?/{d}" -type f -delete',
}


@pytest.mark.parametrize("op", sorted(OPS))
@pytest.mark.parametrize("d", CONTROL_DIRS)
def test_backstop_operations_on_control_folders_ask(proj, W, op, d):  # noqa: F811
    # @W/e/m-0 does not exist: no link Tess can see, as when a program the
    # gate has no rule for made it earlier.
    _never_allow(proj, W, OPS[op].format(d=d))


@pytest.mark.parametrize("cmd", [
    'true; rm -rf "@W/e/m-$?/".claude',                      # split quoting
    'true; D=.claude; rm -rf "@W/e/m-$?/$D"',                # the name in a variable
    'true; rm -rf "@W/e/m-$?"/.{claude,x}',                  # a brace
    'true; rm -rf "@W/e/m-$?"/.c*',                          # a glob
    'true; rm -rf "@W/e/m-$?/./.CLAUDE"',                    # case, a `.` step
    'true; D=.claude; echo x > "@W/e/m-$?/$D/settings.json"',
    'true; echo x > "@W/e/m-$?/.claude/$(date +%s)"',        # a run-time name inside
])
def test_backstop_spellings_of_a_control_folder_ask(proj, W, cmd):  # noqa: F811
    _never_allow(proj, W, cmd)


@pytest.mark.parametrize("cmd", [
    'true; cp -R "@W/e/evil/.claude" "@W/e/m-$?/"',          # puts .claude inside the target
    'true; cp -R "@W/e/evil/." "@W/e/m-$?/"',                # contents holding .claude
    'true; rsync -a "@W/e/evil/" "@W/e/m-$?/"',
    'true; mv "@W/e/evil/.claude" "@W/e/m-$?/"',
    'true; ditto "@W/e/evil" "@W/e/m-$?"',
    'true; tar -xf "@W/e/h.tar" -C "@W/e/m-$?"',             # an archive holding .claude/settings.json
    'true; unzip -o "@W/e/h.zip" -d "@W/e/m-$?"',
])
def test_backstop_a_copy_or_extraction_that_puts_a_control_folder_in_its_target_asks(proj, W, cmd):  # noqa: F811
    _never_allow(proj, W, cmd)


# ====================================================================== same class: folder writers and links
@pytest.mark.parametrize("cmd", [
    # a link made earlier in the same command, then a command that writes into it
    'ln -s "$PWD" "@W/e/n1" && tar -xf "@W/e/h.tar" -C "@W/e/n1"',
    'ln -s "$PWD" "@W/e/n2" && find "@W/e/n2/.claude" -delete',
    'ln -s "$PWD" "@W/e/n3" && cp -R "@W/e/evil/." "@W/e/n3/"',
    'ln -s "$PWD" "@W/e/n4" && rsync -a "@W/e/evil/" "@W/e/n4/"',
    'ln -s "$PWD" "@W/e/n5" && cp -R "@W/e/evil/.claude" "@W/e/n5/"',
    'ln -s "$PWD" "@W/e/n6" && mv "@W/e/evil/.claude" "@W/e/n6/"',
    'ln -s "$PWD" "@W/e/n7" && ditto "@W/e/evil" "@W/e/n7"',
    # a folder only known at run time, through a link on disk
    'true; tar -xf "@W/e/h.tar" -C "@W/k/b-$?"',
    'true; tar -xf "@W/e/plain.tar" -C "@W/k/b-$?"',
    'true; unzip -o "@W/e/h.zip" -d "@W/k/b-$?"',
    'true; ditto "@W/e/plain" "@W/k/b-$?"',
    'true; tar -x -f "@W/e/plain.tar" --directory="@W/k/b-$?"',
    'true; tar xfC "@W/e/h.tar" "@W/k/b-$?"',                # old-style bundle: f, then C
    'tar xfC "@W/e/h.tar" "@W/k/b-0"',
])
def test_folder_writers_follow_links_and_run_time_folders(proj, W, cmd):  # noqa: F811
    _never_allow(proj, W, cmd)


def test_folder_writers_literal_link_spellings_stay_refused(proj, W):  # noqa: F811
    for cmd in ('tar -xf "@W/e/h.tar" -C "@W/k/b-0"', 'find "@W/k/b-0/.claude" -delete'):
        assert _all(proj, _cmd(W, proj[0], cmd)) == DENY, cmd


# ====================================================================== controls: everyday work stays allowed
@pytest.mark.parametrize("cmd", [
    'rm -rf "/var/tmp/b-$$"',
    'rm -rf "@W/e/m-$?/.cache"',
    'rm -rf "@W/e/m-$?/claude"',
    'rm -rf "@W/e/m-$?"/*',
    'cp "@W/e/plain/src/a.txt" "@W/e/out/"',
    'cp -R "@W/e/plain/src" "@W/e/out2"',
    'rsync -a "@W/e/plain/src/" "@W/e/out3/"',
    'tar -xf "@W/e/plain.tar" -C "@W/e/out4"',
    'true; tar -xf "@W/e/plain.tar" -C "@W/e/out-$?"',
    'find "@W/e/plain" -name "*.o" -delete',
    'mkdir -p "@W/e/m/.claude"',
    'true; rm -rf @W/e/[p]lain/out-$?',                        # a glob that matches a real folder
    # a target written out in full is resolved on disk: what it receives is not
    # looked inside (the corpora hold such backups and unpacks)
    'tar -xf "@W/e/h.tar" -C "@W/e/z"',
    'cp -R "@W/e/evil/." "@W/e/backup/"',
    # find under a control folder that cannot change a control file there
    'true; find "@W/e/m-$?/.claude" -maxdepth 1 -name "*.log" -delete',
    'find "@W/e/evil/.claude" -name "*.log" -delete',
    'ln -s "$PWD" "@W/e/n9" && tar -xf "@W/e/plain.tar" -C "@W/e/n9"',  # nothing protected in it
    'ls -la "@W/e/evil/.claude"',
    'cat "@W/e/evil/.claude/settings.json"',
])
def test_controls_stay_allowed(proj, W, cmd):  # noqa: F811
    assert _all(proj, _cmd(W, proj[0], cmd)) == ALLOW, cmd
