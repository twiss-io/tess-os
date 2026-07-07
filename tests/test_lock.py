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


# ---------------------------------------------------------------------------
# lock --regen --only <path> — surgical re-baseline (Ada, 2026-07-07,
# dispatch-guard.sh headless-fix task). Scopes the re-baseline to a named
# entry instead of blessing the whole tree, so a reviewed fix to ONE file
# never silently blesses unrelated, unreviewed drift elsewhere in core.
# ---------------------------------------------------------------------------


def _tamper_both(project):
    """Simulate two independent, deliberate core edits — both currently
    reported as CORE-TAMPER since their base_sha is now stale."""
    core_a = project.root / ".tess" / "core" / "conductor" / "a.md"
    core_a.write_text("alpha v2 reviewed\n")
    project.write_live("conductor/a.md", "alpha v2 reviewed\n")

    core_b = project.root / ".tess" / "core" / "agents" / "leah" / "README.md"
    core_b.write_text("leah v2 reviewed\n")
    project.write_live("agents/leah/README.md", "leah v2 reviewed\n")


def test_lock_regen_only_scopes_to_named_entry_leaves_others_untouched(project, run_cli):
    _seed(project)
    _tamper_both(project)

    # Both entries tampered before any regen.
    r0 = run_cli(project.root, "lock", "--check")
    assert r0.returncode == 1
    assert "conductor/a.md" in r0.stdout
    assert "agents/leah/README.md" in r0.stdout

    # Scoped regen: bless ONLY conductor/a.md.
    r1 = run_cli(project.root, "lock", "--regen", "--only", "conductor/a.md", "--yes")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    assert "re-baselined 1 entry" in r1.stdout
    assert "conductor/a.md" in r1.stdout

    # a.md is now pristine; leah/README.md is STILL a tamper — untouched by
    # the scoped regen, proving it did not bless the whole tree.
    r2 = run_cli(project.root, "lock", "--check")
    assert r2.returncode == 1
    assert "conductor/a.md" not in r2.stdout
    assert "agents/leah/README.md" in r2.stdout

    # An unscoped regen still cleans up the remaining entry.
    r3 = run_cli(project.root, "lock", "--regen", "--yes")
    assert r3.returncode == 0, r3.stdout + r3.stderr
    r4 = run_cli(project.root, "lock", "--check")
    assert r4.returncode == 0, r4.stdout + r4.stderr


def test_lock_regen_only_accepts_core_key_form(project, run_cli):
    _seed(project)
    _tamper_both(project)

    # --only also accepts the core_key (".tess/core/...") form, not just live_path.
    r = run_cli(
        project.root, "lock", "--regen",
        "--only", ".tess/core/conductor/a.md", "--yes",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "re-baselined 1 entry" in r.stdout

    r2 = run_cli(project.root, "lock", "--check")
    assert r2.returncode == 1
    assert "conductor/a.md" not in r2.stdout
    assert "agents/leah/README.md" in r2.stdout


def test_lock_regen_only_unknown_path_fails_loud(project, run_cli):
    _seed(project)
    r = run_cli(project.root, "lock", "--regen", "--only", "nonexistent/path.md", "--yes")
    assert r.returncode != 0
    assert "not found in tess.lock" in (r.stdout + r.stderr)


def test_lock_regen_only_still_gated_behind_yes(project, run_cli):
    _seed(project)
    _tamper_both(project)
    r = run_cli(project.root, "lock", "--regen", "--only", "conductor/a.md", input_text="")
    assert r.returncode != 0
    assert "refused" in (r.stdout + r.stderr).lower()
