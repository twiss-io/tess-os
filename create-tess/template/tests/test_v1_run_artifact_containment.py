"""
1.0.0 (cleanup inventory, artifact containment): `tessctl run` accepts a
returned artifact only when its path resolves, by inode identity, to an
existing entry strictly inside the Tess root.

Before, `_run_check_return_manifest_artifacts_exist_under_root` only asked
whether `root / path` existed. `root / "/abs/path"` is `/abs/path`, so a
return manifest naming any existing absolute path on the machine passed as
"existing under the root"; so did a `..` that climbs out, and a link inside
the root that points out of it.
"""

from __future__ import annotations

import json
import os

import pytest

from test_run import _new_mission, _real_artifact_return_instance, rroot  # noqa: F401 - fixture


def _check(engine, root, mission_id, artifact_path):
    """Write a return manifest naming `artifact_path` and run `run`'s own check."""
    rel = engine._run_artifact_path(mission_id, "t1", "return-manifest")
    instance = _real_artifact_return_instance(mission_id, "t1", artifact_path)
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(instance), encoding="utf-8")
    ok, violations, *_ = engine._run_check_artifact(root, rel, "return-manifest",
                                                    {"ok": True, "timed_out": False})
    return ok, violations


@pytest.fixture(autouse=True)
def _cwd_is_root(rroot, monkeypatch):  # noqa: F811
    # `tessctl run` runs from the root; `_lint_return_manifest` checks CWD-relative.
    monkeypatch.chdir(rroot)


@pytest.fixture
def outside(rroot):  # noqa: F811
    f = rroot.parent / "outside" / "secret.txt"
    f.parent.mkdir()
    f.write_text("not Tess's\n", encoding="utf-8")
    return f


@pytest.fixture
def inside(rroot):  # noqa: F811
    f = rroot / "out" / "result.txt"
    f.parent.mkdir()
    f.write_text("real output\n", encoding="utf-8")
    return f


def _outside_violation(violations):
    return any("resolves outside the Tess root" in v for v in violations)


# ------------------------------------------------------------------ refused

def test_absolute_path_outside_the_root_is_refused(engine, rroot, outside):  # noqa: F811
    m = _new_mission(engine, rroot)
    ok, violations = _check(engine, rroot, m, str(outside))
    assert ok is False and _outside_violation(violations), violations


def test_absolute_system_path_is_refused(engine, rroot):  # noqa: F811
    m = _new_mission(engine, rroot)
    sysfile = "/etc/hosts" if os.path.exists("/etc/hosts") else os.__file__
    ok, violations = _check(engine, rroot, m, sysfile)
    assert ok is False and _outside_violation(violations), violations


def test_dotdot_out_of_the_root_is_refused(engine, rroot, outside):  # noqa: F811
    m = _new_mission(engine, rroot)
    ok, violations = _check(engine, rroot, m, "../outside/secret.txt")
    assert ok is False and _outside_violation(violations), violations


def test_link_inside_the_root_pointing_out_is_refused(engine, rroot, outside):  # noqa: F811
    m = _new_mission(engine, rroot)
    (rroot / "out").mkdir()
    os.symlink(outside, rroot / "out" / "link.txt")
    ok, violations = _check(engine, rroot, m, "out/link.txt")
    assert ok is False and _outside_violation(violations), violations


def test_folder_link_inside_the_root_pointing_out_is_refused(engine, rroot, outside):  # noqa: F811
    m = _new_mission(engine, rroot)
    os.symlink(outside.parent, rroot / "via")
    ok, violations = _check(engine, rroot, m, "via/secret.txt")
    assert ok is False and _outside_violation(violations), violations


def test_the_root_itself_is_not_an_artifact(engine, rroot):  # noqa: F811
    m = _new_mission(engine, rroot)
    for spelling in (".", str(rroot)):
        ok, violations = _check(engine, rroot, m, spelling)
        assert ok is False and _outside_violation(violations), (spelling, violations)


def test_missing_artifact_is_still_reported_as_missing(engine, rroot):  # noqa: F811
    m = _new_mission(engine, rroot)
    ok, violations = _check(engine, rroot, m, "out/never-written.txt")
    assert ok is False
    assert any("does not exist under the Tess root" in v for v in violations), violations
    assert not _outside_violation(violations)


# ------------------------------------------------------------------ allowed

def test_relative_path_inside_the_root_is_accepted(engine, rroot, inside):  # noqa: F811
    m = _new_mission(engine, rroot)
    ok, violations = _check(engine, rroot, m, "out/result.txt")
    assert ok is True, violations


def test_absolute_path_inside_the_root_is_accepted(engine, rroot, inside):  # noqa: F811
    m = _new_mission(engine, rroot)
    ok, violations = _check(engine, rroot, m, str(inside))
    assert ok is True, violations


def test_link_inside_the_root_to_another_inside_file_is_accepted(engine, rroot, inside):  # noqa: F811
    m = _new_mission(engine, rroot)
    os.symlink(inside, rroot / "out" / "alias.txt")
    ok, violations = _check(engine, rroot, m, "out/alias.txt")
    assert ok is True, violations


def test_root_reached_through_another_spelling_is_accepted(engine, rroot, inside):  # noqa: F811
    # Inode identity, not path text: the root spelled through a link to it
    # (an absolute path that never names the root's own folder) is still the root.
    m = _new_mission(engine, rroot)
    alias = rroot.parent / "root-alias"
    os.symlink(rroot, alias)
    ok, violations = _check(engine, rroot, m, str(alias / "out" / "result.txt"))
    assert ok is True, violations


# ------------------------------------------------------------------ helper

def test_helper_fails_closed_on_errors(engine, rroot, inside):  # noqa: F811
    under = engine._run_artifact_resolves_under_root
    assert under(rroot, "out/result.txt") is True
    assert under(rroot, "out/missing.txt") is False  # cannot stat: not under
    assert under(rroot / "no-such-root", "out/result.txt") is False
    assert under(rroot, "out/\x00bad") is False  # unrepresentable path: not under
