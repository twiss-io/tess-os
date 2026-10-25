r"""
v1.0.x follow-ups (Reid, verify of f66d393 and 629f63d): E2, E3, E4, H3, H4.

E2  `find`'s walk of a tree under the project read a folder it could not
    list as empty. Now a folder Tess cannot list asks (Claude) / is refused
    (Codex). A start that does not exist, or is a file, is unchanged.
E3  An extract destination glob whose text as written is also one of its
    own matches dropped the last match instead of the text. Every match is
    now checked.
E4  The recursive walk below a run-time path part counted a link under a
    link-following step only when it was listed as a folder. A link to a
    file, or a dangling one, is listed with the files; it now counts too.
H3  Conformance harness: `.git/objects/info/` (alternates) counts.
H4  Conformance harness: a restore snapshot or manifest must match the
    project file's mode as well as its kind and content.

Decisions: (claude default, claude acceptEdits, codex). Each E test fails
on f66d393 and passes on the fix; the controls pass on both.
"""

from __future__ import annotations

import io
import json
import os
import tarfile

import pytest

import shell_conformance as sc
from test_v1_n1_n3 import ALLOW, ASK, DENY, G, _all, _env, proj  # noqa: F401 - fixtures


def _fill(cmd, proj, extra=None):  # noqa: F811
    out = cmd.replace("@P", str(proj[0])).replace("@H", str(proj[1]))
    for k, v in (extra or {}).items():
        out = out.replace(k, str(v))
    return out


# ====================================================================== E2
@pytest.fixture
def locked(proj):  # noqa: F811
    """A project folder holding a sub-folder Tess cannot list (mode 000)."""
    root = proj[0]
    zone = root / "e2zone"
    (zone / "locked").mkdir(parents=True, exist_ok=True)
    (zone / "a.tmp").write_text("x\n")
    (root / "e2open" / "sub").mkdir(parents=True, exist_ok=True)
    (root / "e2open" / "sub" / "b.tmp").write_text("x\n")
    os.chmod(zone / "locked", 0)
    try:
        yield zone
    finally:
        os.chmod(zone / "locked", 0o755)


needs_perms = pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                                 reason="root can list a mode-000 folder")


@needs_perms
def test_e2_find_under_a_folder_tess_cannot_list_fails_safe(proj, locked):  # noqa: F811
    assert _all(proj, "find e2zone -name '*.tmp' -delete") == ASK
    assert _all(proj, "find e2zone -type f -exec rm -f {} +") == ASK


@needs_perms
def test_e2_neighbours_are_unchanged(proj, locked):  # noqa: F811
    assert _all(proj, "find e2open -name '*.tmp' -delete") == ALLOW  # every folder listable
    assert _all(proj, "find e2-missing -name '*.tmp' -delete") == ALLOW  # nothing there
    assert _all(proj, "find e2zone/a.tmp -delete") == ALLOW  # a file, not a folder
    assert _all(proj, "find e2zone -maxdepth 1 -name '*.tmp' -delete") == ALLOW  # never entered
    assert _all(proj, "find e2zone -name '*.tmp'") == ALLOW  # changes nothing


@needs_perms
def test_n1_maxdepth_0_on_an_unreadable_start_is_not_walked(proj, locked):  # noqa: F811
    # 1.0.0 (Reid N1, approved toward-allow): find never lists below a
    # -maxdepth 0 start, so Tess does not try to list it either.
    assert _all(proj, "find e2zone/locked -maxdepth 0 -delete") == ALLOW
    assert _all(proj, "find e2zone/locked -maxdepth 0 -exec rm -rf {} +") == ALLOW


@needs_perms
def test_n1_neighbours_still_fail_safe(proj, locked):  # noqa: F811
    assert _all(proj, "find e2zone/locked -delete") == ASK  # walked: cannot list it
    assert _all(proj, "find e2zone/locked -maxdepth 1 -delete") == ASK
    assert _all(proj, "find e2zone -maxdepth 2 -delete") == ASK  # reaches the locked folder
    assert _all(proj, "find .claude -maxdepth 0 -delete") == DENY  # the start itself still counts
    assert _all(proj, "find .tess -maxdepth 0 -exec rm -rf {} +") == DENY


# ====================================================================== E3
@pytest.fixture
def E3(proj, tmp_path):  # noqa: F811
    """`w/e*` is a folder whose name is its own glob; `w/ez` is a link to
    the project root, which the same glob also matches. `v` holds only the
    link. The archive holds a member named like a protected file."""
    root = proj[0]
    w = tmp_path / "e3w"
    (w / "e*").mkdir(parents=True)
    os.symlink(str(root), str(w / "ez"))
    v = tmp_path / "e3v"
    v.mkdir()
    os.symlink(str(root), str(v / "ez"))
    arc = tmp_path / "a.tar"
    with tarfile.open(arc, "w") as tf:
        data = b"x\n"
        info = tarfile.TarInfo("tessctl")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    return {"@W": w, "@V": v, "@A": arc}


def test_e3_every_match_of_an_extract_destination_glob_is_checked(proj, E3):  # noqa: F811
    assert _all(proj, _fill("tar -xf @A -C @W/e*", proj, E3)) == DENY


def test_e3_neighbours_are_unchanged(proj, E3):  # noqa: F811
    assert _all(proj, _fill("tar -xf @A -C @V/e*", proj, E3)) == DENY  # the link alone
    # 1.0.0 (a769130 review, M1 class): `e[*]` is a glob, which null-glob can
    # drop, leaving `-C` without its folder; Tess then reads the extraction as
    # into the current folder (the project), where the archive's member is a
    # protected name. Refused under that worst case (it allowed before).
    assert _all(proj, _fill("tar -xf @A -C @W/e[*]", proj, E3)) == DENY
    assert _all(proj, _fill("tar -xf @A -C '@W/e*'", proj, E3)) == ALLOW  # the quoted folder


# ====================================================================== E4
@pytest.fixture
def E4(proj, tmp_path):  # noqa: F811
    """Below a run-time spelling (`r-$?` is `r-0`): a dangling link and a
    link to a file, each listed with the files of its folder."""
    root = proj[0]
    w = tmp_path / "e4w"
    (w / "r-0" / "q").mkdir(parents=True)
    os.symlink(str(root / "e4-not-yet"), str(w / "r-0" / "q" / "dl"))
    f = tmp_path / "e4f"
    (f / "r-0" / "q").mkdir(parents=True)
    os.symlink(str(root / "tessctl"), str(f / "r-0" / "q" / "fl"))
    c = tmp_path / "e4c"
    (c / "r-0" / "q").mkdir(parents=True)
    (c / "r-0" / "q" / "plain.txt").write_text("x\n")
    return {"@W": w, "@F": f, "@C": c}


def test_e4_a_dangling_link_under_a_link_following_step_is_unsure(proj, E4):  # noqa: F811
    assert _all(proj, _fill('true; echo x > "@W/r-$?"/***/zz', proj, E4)) == ASK


def test_e4_a_link_to_a_file_under_a_link_following_step_is_unsure(proj, E4):  # noqa: F811
    assert _all(proj, _fill('true; echo x > "@F/r-$?"/***/zz', proj, E4)) == ASK


def test_e4_neighbours_are_unchanged(proj, E4):  # noqa: F811
    # no link below the step
    assert _all(proj, _fill('true; echo x > "@C/r-$?"/***/zz', proj, E4)) == ALLOW


# ====================================================================== H3
def test_h3_git_alternates_count_in_a_replay(tmp_path):
    gate = sc.load_gate()
    p = tmp_path / "proj"
    (p / ".git").mkdir(parents=True)
    (p / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    s = {"P": str(p), "H": str(tmp_path / "home")}
    for rel in (".git/objects/info/alternates", ".git/objects/info/http-alternates",
                ".git/objects/info/commit-graph"):
        assert sc._git_normal_write(rel, s) is False, rel
        assert sc.controlled(rel, gate, s) is True, rel
    for rel in (".git/objects/ab/cdef", ".git/objects/pack/pack-1.pack", ".git/objects"):
        assert sc.controlled(rel, gate, s) is False, rel


# ====================================================================== H4
def test_h4_a_restore_snapshot_with_another_mode_counts():
    before = {"tessctl": ("file", 0o755, "h1")}
    snap = ".tess/snapshots/t1/tessctl"
    base = {**before, ".tess/snapshots": ("dir", 0o755), ".tess/snapshots/t1": ("dir", 0o755)}
    assert sc._true_snapshot(snap, before, {**base, snap: ("file", 0o755, "h1")}) is True
    assert sc._true_snapshot(snap, before, {**base, snap: ("file", 0o4755, "h1")}) is False


def test_h4_a_restore_manifest_with_another_mode_counts(tmp_path):
    before = {"tessctl": ("file", 0o755, "h1")}
    rel = ".tess/snapshots/t1/manifest.json"
    after = {**before, ".tess/snapshots": ("dir", 0o755), ".tess/snapshots/t1": ("dir", 0o755),
             rel: ("file", 0o644, "m")}
    (tmp_path / ".tess/snapshots/t1").mkdir(parents=True)
    for mode, ok in ((0o755, True), (0o4755, False), (0o777, False), (None, False)):
        man = {"tessctl": {"existed": True, "sha256": "sha256:h1", "mode": mode}}
        (tmp_path / rel).write_text(json.dumps(man))
        assert sc._true_snapshot(rel, before, after, str(tmp_path)) is ok, mode
