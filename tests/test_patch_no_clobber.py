"""
PATCH-APPLY conflict NO-CLOBBER.

When a stored override_diff CANNOT apply onto the new upstream core, the engine
must: halt the update (exit 1), park a .rej, and leave the operator's customized
file LIVE byte-for-byte. The "Your version is LIVE" promise has to hold on the
patch-apply route, not just the 3-way-merge route.
"""

from __future__ import annotations

import subprocess
import tempfile

import pytest


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


def test_patch_apply_conflict_does_not_clobber_live(project):
    base = "alpha\nbeta\ngamma\n"
    local = "alpha\nbeta-LOCAL\ngamma\n"                  # operator's customization → LIVE
    new_core = "totally\ndifferent\nupstream\ncontent\n"  # diff context cannot be found here
    diff_text = _unified_diff(base.encode(), local.encode(), "conductor/cpatch.md")
    assert diff_text and "beta-LOCAL" in diff_text       # sanity: a real diff is stored

    project.add("conductor/cpatch.md", base, status="patch-override",
                override_diff=diff_text)
    project.write_live("conductor/cpatch.md", local)     # the operator's version is what's live
    project.stage(".tess/core/conductor/cpatch.md", new_core)

    lock = project.write()
    with pytest.raises(SystemExit) as ei:
        project.mod._apply_per_file_resolution(project.root, lock, dry_run=False)
    assert ei.value.code == 1                            # update BLOCKED on the failed patch

    # .rej parked next to the file, carrying the diff that failed to apply.
    # patch(1) convention: <name>.rej (full filename + .rej), so cpatch.md → cpatch.md.rej
    rej = project.root / "conductor" / "cpatch.md.rej"
    assert rej.exists()
    assert "beta-LOCAL" in rej.read_text()

    # The operator's customized version is STILL live — byte-for-byte unchanged.
    assert project.read_live("conductor/cpatch.md") == local
