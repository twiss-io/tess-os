"""
lock --check (CI integrity gate) + lock --regen (maintainer re-baseline).

Exercised through the real CLI so the exit codes (the whole point of a CI gate)
are genuinely asserted.
"""

from __future__ import annotations


def _seed(project):
    project.add("conductor/a.md", "alpha\n")
    project.add("agents/leah/README.md", "leah\n")
    return project.write()


def test_lock_check_passes_on_clean_tree(project, run_cli):
    _seed(project)
    r = run_cli(project.root, "lock", "--check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_lock_check_fails_nonzero_on_drift(project, run_cli):
    _seed(project)
    project.write_live("conductor/a.md", "alpha drifted\n")
    r = run_cli(project.root, "lock", "--check")
    assert r.returncode == 1
    assert "FAIL" in r.stdout
    assert "DRIFT" in r.stdout


def test_lock_regen_rebaselines_to_current_core(project, run_cli):
    _seed(project)
    core_a = project.root / ".tess" / "core" / "conductor" / "a.md"
    # Deliberate, reviewed core change: update BOTH core and the matching live.
    core_a.write_text("alpha v2 reviewed\n")
    project.write_live("conductor/a.md", "alpha v2 reviewed\n")

    # base_sha is now stale → CORE TAMPER, CI gate fails.
    r1 = run_cli(project.root, "lock", "--check")
    assert r1.returncode == 1
    assert "CORE-TAMPER" in r1.stdout

    # Re-baseline blesses the current core.
    r2 = run_cli(project.root, "lock", "--regen", "--yes")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "re-baselined" in r2.stdout

    # Gate is green again.
    r3 = run_cli(project.root, "lock", "--check")
    assert r3.returncode == 0, r3.stdout + r3.stderr
    assert "OK" in r3.stdout


def test_lock_regen_refused_without_yes_noninteractive(project, run_cli):
    _seed(project)
    # No --yes and stdin not a TTY (subprocess pipe) → refuse, non-zero.
    r = run_cli(project.root, "lock", "--regen", input_text="")
    assert r.returncode != 0
    assert "refused" in (r.stdout + r.stderr).lower()
