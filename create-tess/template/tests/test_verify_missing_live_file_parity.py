"""
Issue #139 — `cmd_verify` deleted-live-file fail-open + lock-check annotation
wording (3 findings from #138's review, filed as a follow-up per both
reviewers' recommendation).

  1. [MEDIUM, Cyra + Reid] `cmd_verify` FAIL-OPENED on a deleted LIVE file for
     a non-security-tier `core-managed` entry with an intact core file:
     `doctor` and `lock --check` (post-#138) both FAILed, but `verify`
     reported OK / exit 0. Root cause: Check C (security-tier drift) only
     runs `if sec`, and Check D (normal-tier drift) is gated on
     `core_path.exists() and live_path.exists()` — if the live file is gone,
     both conditions are false, no issue is appended, and the entry silently
     falls through to `ok_count += 1`. Fixed by routing `cmd_verify` through
     the SAME shared classifier (`_doctor_result_is_error`) `cmd_doctor` and
     (as of #138) `cmd_lock --check` already call for this exact deletion
     case, instead of a fourth independent inline rule.
  2. [LOW, Reid] `cmd_lock`'s docstring claim ("the shared classifier
     `_doctor_result_is_error` all three commands call") is now literally
     true post-fix — pinned indirectly by the parity assertions below (all
     three commands agreeing) rather than a docstring-text test.
  3. [LOW, Cyra] `lock --check`'s MISSING (deletion) sub-case for a
     core-internal entry now prints `(core-internal — file missing)`,
     matching `verify`'s own wording for the identical case, instead of the
     generic `(core-internal — no live path)` annotation shared with the
     CORE-TAMPER (hash-mismatch) sub-case.

Issue #143 — follow-up from #142's review (Cyra APPROVE-MERGE, Reid
APPROVE-WITH-NITS on this file's own #139 fix):

  4. [MEDIUM, Reid] No test pinned a `held` / `locally-modified` /
     `user-published` entry with a DELETED live file — the coverage above
     only exercised the default `core-managed` status. `cmd_verify` has had
     3 sequential fail-open PRs on this exact class (#124/#138/#139); added
     a parametrized regression test covering Check B2's actual exclusion-set
     boundary (`("user-created", "staged")`, not just "core-managed") so
     `verify` FAILing on a deleted live file for those three statuses too —
     matching `doctor`/`lock --check` — is genuinely pinned, not just true
     by accident of the exclusion-set code shape.

The [LOW] Check B2 code nits from #143 (redundant re-hash comment, dead-code
`else` branch comment) are documented inline at their call site in
`cmd_verify` (`.tess/bin/tessctl`), not here.
"""

from __future__ import annotations

import pytest

from conftest import ns


# ---------------------------------------------------------------------------
# 1. THE fail-open (MEDIUM) — the core regression this issue exists to close.
#    Exercised end-to-end through the real CLI so the exit codes are
#    genuinely asserted, mirroring test_lock_check_deletion_parity.py's own
#    convention for the #124/#138 sibling regression.
# ---------------------------------------------------------------------------

def _seed_normal_entry(project):
    """A normal-tier, core-managed entry with live_path set and rendered —
    the exact shape Reid reproduced the fail-open on."""
    project.add("conductor/probe.md", "probe body v1\n")
    project.write()


def test_verify_fails_on_deleted_live_file_for_normal_tier_core_managed_entry(
    project, run_cli
):
    """Before: deleting the live file (core intact) left `verify` OK / exit 0
    while `doctor` and `lock --check` both FAILed. After: all three FAIL
    together."""
    _seed_normal_entry(project)

    # Baseline — clean tree, all three surfaces green.
    assert run_cli(project.root, "doctor").returncode == 0
    assert run_cli(project.root, "verify").returncode == 0
    assert run_cli(project.root, "lock", "--check").returncode == 0

    # Delete (not tamper) ONLY the live file — the core file stays intact.
    (project.root / "conductor" / "probe.md").unlink()

    d = run_cli(project.root, "doctor")
    assert d.returncode == 1, f"doctor did not catch the deletion:\n{d.stdout}{d.stderr}"

    lk = run_cli(project.root, "lock", "--check")
    assert lk.returncode == 1, (
        f"lock --check did not catch the deletion:\n{lk.stdout}{lk.stderr}"
    )

    v = run_cli(project.root, "verify")
    assert v.returncode == 1, (
        f"verify did NOT catch the deleted live file — the #139 fail-open "
        f"(doctor + lock --check both FAIL on this exact tree):\n"
        f"{v.stdout}{v.stderr}"
    )
    assert "verify: FAIL" in v.stdout
    assert "LIVE MISSING" in v.stdout
    assert "conductor/probe.md" in v.stdout


def test_verify_deleted_live_file_regression_is_reversible(project, run_cli):
    """Restoring the deleted live file returns `verify` to green — the fix
    must not introduce a permanent/irreversible failure."""
    _seed_normal_entry(project)
    live_path = project.root / "conductor" / "probe.md"
    original = live_path.read_bytes()

    live_path.unlink()
    assert run_cli(project.root, "verify").returncode == 1

    live_path.write_bytes(original)
    r = run_cli(project.root, "verify")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "verify: OK" in r.stdout


def test_verify_still_fails_on_deleted_security_tier_live_file(project, run_cli):
    """The SAME fail-open shape also applied to a SECURITY-tier entry (Check
    C's `if sec` guard also requires `live_path.exists()`, so a deleted
    security-tier live file fell through it too) — confirm the fix closes
    this broader case, not just the non-security-tier example in the issue."""
    project.add("conductor/guardrails.md", "GUARDRAILS\n", tier="security")
    project.write()

    (project.root / "conductor" / "guardrails.md").unlink()

    d = run_cli(project.root, "doctor")
    assert d.returncode == 1

    v = run_cli(project.root, "verify")
    assert v.returncode == 1, f"verify did not catch a deleted SECURITY-tier live file:\n{v.stdout}{v.stderr}"
    assert "LIVE MISSING" in v.stdout
    assert "[SECURITY]" in v.stdout
    assert "conductor/guardrails.md" in v.stdout


# ---------------------------------------------------------------------------
# Issue #143 (MEDIUM, Reid, follow-up from #142's review): Check B2's
# exclusion set is `file_status not in ("user-created", "staged")` — every
# OTHER status, including held / locally-modified / user-published, routes
# through the shared classifier and should FAIL on a deleted live file. No
# test pinned this boundary directly; the coverage above only exercises the
# default "core-managed" status. `cmd_verify` has had 3 sequential fail-open
# PRs on this exact live-file-deletion class (#124, #138, #139) — this closes
# the gap by asserting all three of the non-default, non-excluded statuses
# fail the same way `doctor` and `lock --check` already do.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["held", "locally-modified", "user-published"])
def test_verify_fails_on_deleted_live_file_for_exclusion_set_boundary_statuses(
    project, run_cli, status
):
    """held / locally-modified / user-published are NOT in Check B2's
    ("user-created", "staged") exclusion set — a deleted live file for any
    of them must FAIL verify, matching doctor and lock --check, exactly like
    the default core-managed case already covered above."""
    project.add(f"conductor/{status.replace('-', '_')}.md", "body v1\n", status=status)
    project.write()

    live_path = project.root / "conductor" / f"{status.replace('-', '_')}.md"

    # Baseline — clean tree, all three surfaces green regardless of status.
    assert run_cli(project.root, "doctor").returncode == 0, f"status={status}"
    assert run_cli(project.root, "verify").returncode == 0, f"status={status}"
    assert run_cli(project.root, "lock", "--check").returncode == 0, f"status={status}"

    live_path.unlink()

    d = run_cli(project.root, "doctor")
    assert d.returncode == 1, (
        f"doctor did not catch the deletion for status={status}:\n{d.stdout}{d.stderr}"
    )

    lk = run_cli(project.root, "lock", "--check")
    assert lk.returncode == 1, (
        f"lock --check did not catch the deletion for status={status}:\n{lk.stdout}{lk.stderr}"
    )

    v = run_cli(project.root, "verify")
    assert v.returncode == 1, (
        f"verify did NOT fail on a deleted live file for the exclusion-set "
        f"boundary status={status} — Check B2's exclusion set is "
        f"(\"user-created\", \"staged\") only, so this status must route "
        f"through the shared classifier and fail, matching doctor + lock "
        f"--check on the identical tree:\n{v.stdout}{v.stderr}"
    )
    assert "LIVE MISSING" in v.stdout, f"status={status}"


def test_verify_does_not_fail_on_deleted_live_file_for_user_created_status(
    project, run_cli
):
    """Non-regression boundary check: `user-created` IS in the exclusion set
    (a user-created file is never materialized by tessctl in the first
    place, so its absence is expected, not a deletion) — confirm it is
    excluded even after the fix, distinguishing it from the three statuses
    above that must fail."""
    project.add(
        "conductor/user_boundary.md", "user body\n",
        status="user-created", render_live=False,
    )
    project.write()

    r = run_cli(project.root, "verify")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "LIVE MISSING" not in r.stdout


# ---------------------------------------------------------------------------
# Clean-tree non-regression — the fix must not introduce a new false
# positive. Broader than test_doctor_verify.py's existing
# test_verify_clean_tree_is_green: exercises a mix of core-managed, staged,
# and user-created entries through the real CLI (not just the in-process
# cmd_verify call) so the new Check B2's exclusion set is genuinely pinned.
# ---------------------------------------------------------------------------

def test_verify_clean_tree_still_passes_with_mixed_statuses(project, run_cli):
    project.add("conductor/a.md", "alpha\n")
    project.add("conductor/guardrails.md", "GUARDRAILS\n", tier="security")
    # staged: intentionally benched — live_path set in the lock but no live
    # file is ever rendered for it. This must NOT be flagged as "missing".
    project.add(
        "conductor/staged-thing.md", "staged body\n",
        status="staged", render_live=False,
    )
    # user-created: never materialized by tessctl — same non-flagging
    # requirement as staged.
    project.add(
        "conductor/user-thing.md", "user body\n",
        status="user-created", render_live=False,
    )
    project.write()

    r = run_cli(project.root, "verify")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "verify: OK" in r.stdout
    assert "LIVE MISSING" not in r.stdout


def test_verify_missing_live_file_does_not_fire_for_staged_entries(project, run_cli):
    """A staged entry's live_path is CORRECTLY absent from disk (benched, not
    yet recruited) — Check B2 must not misclassify this as a deletion."""
    project.add(
        "conductor/staged-thing.md", "staged body\n",
        status="staged", render_live=False,
    )
    project.write()

    r = run_cli(project.root, "verify")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "LIVE MISSING" not in r.stdout


def test_verify_missing_live_file_does_not_fire_for_user_created_entries(project, run_cli):
    """A user-created entry is never materialized by tessctl — its live_path
    being absent from disk is the expected state, not a deletion."""
    project.add(
        "conductor/user-thing.md", "user body\n",
        status="user-created", render_live=False,
    )
    project.write()

    r = run_cli(project.root, "verify")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "LIVE MISSING" not in r.stdout


# ---------------------------------------------------------------------------
# In-process check on the shared-classifier routing itself — pins that the
# fix genuinely delegates to `doctor_check_file` + `_doctor_result_is_error`
# rather than re-implementing an equivalent inline rule (the structural
# distinction #124/#138's own parity tests draw for `cmd_lock`).
# ---------------------------------------------------------------------------

def test_verify_routes_missing_live_file_through_doctor_check_file(project, monkeypatch):
    _seed_normal_entry(project)
    (project.root / "conductor" / "probe.md").unlink()

    calls = []
    real_check = project.mod.doctor_check_file

    def spy(core_key, attrs, root):
        calls.append(core_key)
        return real_check(core_key, attrs, root)

    monkeypatch.setattr(project.mod, "doctor_check_file", spy)

    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_verify(ns(), project.root)
    assert ei.value.code == 1

    assert ".tess/core/conductor/probe.md" in calls, (
        "cmd_verify did not call doctor_check_file for the deleted-live-file "
        "entry — the #139 fix must route through the shared classifier, not "
        "re-implement an equivalent inline rule"
    )


# ---------------------------------------------------------------------------
# 3. [LOW, Cyra] annotation wording alignment — `lock --check` and `verify`
#    must print the SAME string for the MISSING (deletion) sub-case on a
#    core-internal (live_path: null) entry.
# ---------------------------------------------------------------------------

def _seed_core_internal_entry(project):
    project.add(
        None, "persona body v1\n",
        core_key=".tess/core/personas/fixture.md", render_live=False,
    )
    project.write()


def test_verify_and_lock_check_agree_on_core_internal_missing_wording(project, run_cli):
    _seed_core_internal_entry(project)
    (project.root / ".tess" / "core" / "personas" / "fixture.md").unlink()

    v = run_cli(project.root, "verify")
    assert v.returncode == 1
    assert "(core-internal — file missing)" in v.stdout

    lk = run_cli(project.root, "lock", "--check")
    assert lk.returncode == 1
    assert "(core-internal — file missing)" in lk.stdout, (
        "lock --check's MISSING sub-case annotation does not match verify's "
        "own wording for the identical deleted-core-internal-file case"
    )


def test_lock_check_core_internal_tamper_annotation_unchanged(project, run_cli):
    """Non-regression: the CORE-TAMPER (hash-mismatch, not deletion)
    sub-case for a core-internal entry keeps its existing "(core-internal —
    no live path)" annotation — only the MISSING sub-case's wording changed."""
    _seed_core_internal_entry(project)
    core_path = project.root / ".tess" / "core" / "personas" / "fixture.md"
    core_path.write_text("persona body v1 — TAMPERED\n", encoding="utf-8")

    lk = run_cli(project.root, "lock", "--check")
    assert lk.returncode == 1
    assert "CORE-TAMPER" in lk.stdout
    assert "(core-internal — no live path)" in lk.stdout
    assert "(core-internal — file missing)" not in lk.stdout


# ---------------------------------------------------------------------------
# Determinism — repeated runs over the identical broken tree must produce
# byte-identical stdout and the same exit code (dict-iteration order over
# `files.items()` is insertion-stable, but the new missing_live_files
# accumulator is pinned explicitly rather than assumed).
# ---------------------------------------------------------------------------

def test_verify_missing_live_file_output_is_deterministic_across_runs(project, run_cli):
    project.add("conductor/a.md", "alpha\n")
    project.add("conductor/b.md", "bravo\n")
    project.add("conductor/guardrails.md", "GUARDRAILS\n", tier="security")
    project.write()

    (project.root / "conductor" / "a.md").unlink()
    (project.root / "conductor" / "guardrails.md").unlink()

    r1 = run_cli(project.root, "verify")
    r2 = run_cli(project.root, "verify")

    assert r1.returncode == 1 == r2.returncode
    assert r1.stdout == r2.stdout, "verify output is not deterministic across identical runs"
