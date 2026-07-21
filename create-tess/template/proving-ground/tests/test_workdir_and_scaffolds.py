"""Unit tests for scaffold mounting: `bare` copies nothing beyond the task
fixture; `tess-os` also mounts CLAUDE.md/conductor/agents/.claude/core
from the real repo root — verified against this checkout itself.
"""
from __future__ import annotations

from pg_lib.paths import REPO_ROOT_DEFAULT, TASKS_ROOT
from pg_lib.scaffolds import scaffold_source_paths, validate_tess_os_scaffold_available
from pg_lib.manifest import load_manifest
from pg_lib.workdir import stage_workdir


def test_bare_scaffold_has_no_source_paths():
    assert scaffold_source_paths(REPO_ROOT_DEFAULT, "bare") == []


def test_tess_os_scaffold_lists_the_governance_surface():
    paths = scaffold_source_paths(REPO_ROOT_DEFAULT, "tess-os")
    names = {p.name for p in paths}
    assert names == {"CLAUDE.md", "conductor", "agents", ".claude", "core"}


def test_tess_os_scaffold_sources_actually_exist_in_this_checkout():
    assert validate_tess_os_scaffold_available(REPO_ROOT_DEFAULT) == []


def test_stage_workdir_bare_contains_only_fixture_files(tmp_path):
    manifest = load_manifest(TASKS_ROOT / "01-bug-average-empty-list")
    workdir = stage_workdir(manifest, "bare", REPO_ROOT_DEFAULT, tmp_path, "cell-a1")
    names = {p.name for p in workdir.iterdir()}
    assert names == {"calc.py", "test_calc.py"}
    assert not (workdir / "CLAUDE.md").exists()
    assert not (workdir / "conductor").exists()


def test_stage_workdir_tess_os_adds_the_governance_surface(tmp_path):
    manifest = load_manifest(TASKS_ROOT / "01-bug-average-empty-list")
    workdir = stage_workdir(manifest, "tess-os", REPO_ROOT_DEFAULT, tmp_path, "cell-a1")
    assert (workdir / "calc.py").exists()
    assert (workdir / "test_calc.py").exists()
    assert (workdir / "CLAUDE.md").is_file()
    assert (workdir / "conductor").is_dir()
    assert (workdir / "agents").is_dir()


def test_stage_workdir_wipes_a_prior_attempt_clean(tmp_path):
    manifest = load_manifest(TASKS_ROOT / "01-bug-average-empty-list")
    workdir = stage_workdir(manifest, "bare", REPO_ROOT_DEFAULT, tmp_path, "cell-a1")
    (workdir / "calc.py").write_text("# an agent's edit from attempt 1\n")
    (workdir / "leftover_junk.txt").write_text("should not survive a restage")

    restaged = stage_workdir(manifest, "bare", REPO_ROOT_DEFAULT, tmp_path, "cell-a1")
    assert restaged == workdir
    assert not (workdir / "leftover_junk.txt").exists()
    assert "an agent's edit" not in (workdir / "calc.py").read_text()
