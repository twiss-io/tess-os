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
# `--only` — scoped re-baseline (added alongside `tessctl verdict keygen`,
# which needs to re-pin the ONE core file it just touched without blessing
# any OTHER file's unrelated drift/tamper as a side effect — see
# `_lock_regen_core` in .tess/bin/tessctl and tests/test_verdict_keygen.py).
# ---------------------------------------------------------------------------

def test_lock_regen_only_scopes_to_named_entry(project, run_cli):
    lock = _seed(project)
    core_a = project.root / ".tess" / "core" / "conductor" / "a.md"
    core_b = project.root / ".tess" / "core" / "agents" / "leah" / "README.md"
    # Deliberate, reviewed changes to BOTH core files + their live mirrors.
    core_a.write_text("alpha v2 reviewed\n")
    project.write_live("conductor/a.md", "alpha v2 reviewed\n")
    core_b.write_text("leah v2 reviewed\n")
    project.write_live("agents/leah/README.md", "leah v2 reviewed\n")

    r1 = run_cli(project.root, "lock", "--check")
    assert r1.returncode == 1
    assert r1.stdout.count("CORE-TAMPER") == 2

    # Scoped regen — only re-pin conductor/a.md's entry, by its live_path.
    r2 = run_cli(project.root, "lock", "--regen", "--yes", "--only", "conductor/a.md")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "re-baselined 1 entry" in r2.stdout

    # conductor/a.md is now clean; agents/leah/README.md is STILL a tamper —
    # the scoped regen never touched it, proving it cannot silently bless an
    # unrelated file's drift as a side effect.
    r3 = run_cli(project.root, "lock", "--check")
    assert r3.returncode == 1
    assert r3.stdout.count("CORE-TAMPER") == 1
    assert "agents/leah/README.md" in r3.stdout
    assert "conductor/a.md" not in r3.stdout


def test_lock_regen_only_matches_by_core_key_too(project, run_cli):
    lock = _seed(project)
    core_key = ".tess/core/conductor/a.md"
    (project.root / core_key).write_text("alpha v2 reviewed\n")
    project.write_live("conductor/a.md", "alpha v2 reviewed\n")

    r = run_cli(project.root, "lock", "--regen", "--yes", "--only", core_key)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "re-baselined 1 entry" in r.stdout

    r2 = run_cli(project.root, "lock", "--check")
    assert r2.returncode == 0, r2.stdout + r2.stderr


def test_lock_regen_without_only_is_unchanged_behavior(project, run_cli):
    """Omitting --only must reproduce the exact prior all-entries behavior —
    no regression for existing callers/tests."""
    _seed(project)
    core_a = project.root / ".tess" / "core" / "conductor" / "a.md"
    core_a.write_text("alpha v2 reviewed\n")
    project.write_live("conductor/a.md", "alpha v2 reviewed\n")

    r = run_cli(project.root, "lock", "--regen", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "re-baselined 2 entries" in r.stdout  # both seeded entries considered

    r2 = run_cli(project.root, "lock", "--check")
    assert r2.returncode == 0, r2.stdout + r2.stderr
