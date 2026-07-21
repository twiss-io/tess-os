"""
The 3-way merge engine: _apply_per_file_resolution.

Covers the per-file decision matrix and the actual file outcomes:
  * fast-forward (core-managed → take staging)
  * clean 3-way merge (locally-modified + non-overlapping upstream change)
  * patch-apply (patch-override → re-apply stored diff onto new core)
  * CONFLICT-HALT (overlapping edits → stop, ask, do NOT clobber the live file)
  * keep / skip (no staging, user-published, held, user-created)
"""

from __future__ import annotations

import subprocess
import tempfile

import pytest


def _apply(project):
    lock = project.write()
    project.mod._apply_per_file_resolution(project.root, lock, dry_run=False)
    return lock


# ---------------------------------------------------------------------------
# fast-forward
# ---------------------------------------------------------------------------

def test_fast_forward_takes_staging(project):
    project.add("conductor/ff.md", "core v1\n", status="core-managed")
    project.stage(".tess/core/conductor/ff.md", "core v2 upstream\n")
    _apply(project)
    assert project.read_live("conductor/ff.md") == "core v2 upstream\n"


def test_fast_forward_no_staging_writes_core(project):
    """core-managed with no staging version → still synced from core."""
    project.add("conductor/ff2.md", "only core\n", status="core-managed",
                render_live=False)
    _apply(project)
    assert project.read_live("conductor/ff2.md") == "only core\n"


# ---------------------------------------------------------------------------
# clean 3-way merge
# ---------------------------------------------------------------------------

def test_clean_merge_combines_nonoverlapping_edits(project):
    base = "L1\nL2\nL3\nL4\nL5\n"
    ours = "L1-local\nL2\nL3\nL4\nL5\n"        # local edit at top
    theirs = "L1\nL2\nL3\nL4\nL5-upstream\n"   # upstream edit at bottom
    project.add("conductor/merge.md", base, status="locally-modified")
    project.write_live("conductor/merge.md", ours)
    project.stage(".tess/core/conductor/merge.md", theirs)
    _apply(project)
    merged = project.read_live("conductor/merge.md")
    assert "L1-local" in merged
    assert "L5-upstream" in merged
    assert "<<<<<<<" not in merged  # no conflict markers


def test_locally_modified_no_staging_is_kept(project):
    """locally-modified + no upstream change → keep the local version untouched."""
    project.add("conductor/keep.md", "core\n", status="locally-modified")
    project.write_live("conductor/keep.md", "my local edit\n")
    _apply(project)
    assert project.read_live("conductor/keep.md") == "my local edit\n"


# ---------------------------------------------------------------------------
# patch-apply
# ---------------------------------------------------------------------------

def _unified_diff(a_bytes, b_bytes, live_rel):
    with tempfile.NamedTemporaryFile(suffix=".a", delete=False) as fa:
        fa.write(a_bytes)
        a_tmp = fa.name
    with tempfile.NamedTemporaryFile(suffix=".b", delete=False) as fb:
        fb.write(b_bytes)
        b_tmp = fb.name
    r = subprocess.run(
        ["diff", "-u", "--label", f"a/{live_rel}", "--label", f"b/{live_rel}",
         a_tmp, b_tmp], capture_output=True, text=True)
    return r.stdout


def test_patch_apply_reapplies_override_onto_new_core(project):
    base = "alpha\nbeta\ngamma\n"
    local = "alpha\nbeta-LOCAL\ngamma\n"          # the recorded customization
    new_core = "alpha\nbeta\ngamma\nDELTA\n"      # upstream adds a trailing line
    diff_text = _unified_diff(base.encode(), local.encode(), "conductor/patch.md")
    assert diff_text  # sanity: there IS a diff to store

    project.add("conductor/patch.md", base, status="patch-override",
                override_diff=diff_text)
    project.stage(".tess/core/conductor/patch.md", new_core)
    _apply(project)

    result = project.read_live("conductor/patch.md")
    assert "beta-LOCAL" in result   # local customization re-applied
    assert "DELTA" in result        # upstream change present
    # patch succeeded → no reject file
    assert not (project.root / "conductor" / "patch.rej").exists()


def test_patch_override_no_staging_is_kept(project):
    project.add("conductor/po.md", "core\n", status="patch-override",
                override_diff="(stored)")
    project.write_live("conductor/po.md", "customized\n")
    _apply(project)
    assert project.read_live("conductor/po.md") == "customized\n"


# ---------------------------------------------------------------------------
# CONFLICT-HALT — the safety-critical path
# ---------------------------------------------------------------------------

def test_conflict_halts_and_does_not_clobber_live(project):
    base = "line-1\nline-2\nline-3\n"
    ours = "line-1\nLOCAL-CHANGE\nline-3\n"     # both edit line-2…
    theirs = "line-1\nUPSTREAM-CHANGE\nline-3\n"  # …differently → CONFLICT
    project.add("conductor/conflict.md", base, status="locally-modified")
    project.write_live("conductor/conflict.md", ours)
    project.stage(".tess/core/conductor/conflict.md", theirs)

    with pytest.raises(SystemExit) as ei:
        _apply(project)
    assert ei.value.code == 1  # update BLOCKED on conflict

    # The live file MUST be untouched — the operator's version stays live.
    assert project.read_live("conductor/conflict.md") == ours

    # The merged-with-markers output is parked under .tess/conflicts/ for review.
    conflict_file = project.root / ".tess" / "conflicts" / "conductor_conflict.md"
    assert conflict_file.exists()
    parked = conflict_file.read_text()
    assert "LOCAL-CHANGE" in parked and "UPSTREAM-CHANGE" in parked
    assert "<<<<<<<" in parked  # real conflict markers, not a silent overwrite


def test_conflict_does_not_touch_other_clean_files(project):
    # A clean fast-forward file alongside a conflicting merge file: the clean one
    # is still applied, but the run halts non-zero because of the conflict.
    project.add("conductor/clean.md", "v1\n", status="core-managed")
    project.stage(".tess/core/conductor/clean.md", "v2\n")

    base = "a\nb\nc\n"
    project.add("conductor/bad.md", base, status="locally-modified")
    project.write_live("conductor/bad.md", "a\nOURS\nc\n")
    project.stage(".tess/core/conductor/bad.md", "a\nTHEIRS\nc\n")

    with pytest.raises(SystemExit):
        _apply(project)
    assert project.read_live("conductor/clean.md") == "v2\n"


# ---------------------------------------------------------------------------
# skip statuses
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["user-published", "held", "user-created"])
def test_skip_statuses_leave_live_untouched(project, status):
    project.add("conductor/skip.md", "core\n", status=status)
    project.write_live("conductor/skip.md", "user owns this\n")
    project.stage(".tess/core/conductor/skip.md", "upstream wants this\n")
    _apply(project)
    assert project.read_live("conductor/skip.md") == "user owns this\n"


def test_dry_run_changes_nothing(project):
    project.add("conductor/dry.md", "core v1\n", status="core-managed")
    project.stage(".tess/core/conductor/dry.md", "core v2\n")
    lock = project.write()
    project.mod._apply_per_file_resolution(project.root, lock, dry_run=True)
    assert project.read_live("conductor/dry.md") == "core v1\n"  # unchanged
