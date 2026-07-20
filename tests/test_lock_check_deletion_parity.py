"""
Issue #124 — `cmd_lock --check` parity hardening (3 findings from #123's review).

  1. [MEDIUM, Cyra] `lock --check` FAIL-OPENED on the DELETION tamper class:
     deleting a core-internal file (e.g. `.tess/core/MANIFEST.md`) made
     `doctor` FAIL and `verify` FAIL, but `lock --check` reported OK / exit 0.
     Root cause: `cmd_lock`'s per-entry loop only ever classified a result as
     blocking via `core_tamper` / `lock_status == "quarantined"` / (`drift`
     and `lock_status == "core-managed"`) — a deleted file matches NONE of
     those three (`doctor_check_file` records it as a plain issue string,
     "core file missing: ..." / "live file missing: ..."), so it silently
     fell through to "no issues". Fixed by gating the loop on the SAME
     shared classifier (`_doctor_result_is_error`) `cmd_doctor` already uses
     for its own --json exit code.
  2. [LOW, Reid] `cmd_lock`'s skip predicate didn't structurally mirror
     `cmd_doctor`'s `status == "staged"` fallthrough (harmless today — 0
     such entries exist in the shipped lock) — a pinning test guards the
     structural parity going forward.
  3. [LOW] `lock --check` now annotates null-live-path (core-internal)
     reports with `(core-internal — no live path)`, matching `verify`'s own
     "(core-internal — no live path)" print for the same class of entry.
"""

from __future__ import annotations

import pytest

from conftest import ns


# ---------------------------------------------------------------------------
# 1. THE deletion-tamper fail-open (MEDIUM, Cyra) — the core regression this
#    issue exists to close. Exercised end-to-end through the real CLI so the
#    exit codes are genuinely asserted, mirroring test_lock.py's own
#    convention for `lock --check`.
# ---------------------------------------------------------------------------

def _seed_core_internal_entry(project):
    """A live_path: null / base_sha-pinned entry — the exact R1 core-internal
    shape `personas/*.md` and `.tess/core/MANIFEST.md` both use (the issue's
    own worked example)."""
    project.add(
        None, "persona body v1\n",
        core_key=".tess/core/personas/fixture.md", render_live=False,
    )
    project.write()


def test_lock_check_fails_on_deleted_core_internal_file(project, run_cli):
    """Before: deleting a core-internal file left `lock --check` OK / exit 0
    while `doctor`/`verify` both FAILed. After: all three FAIL together."""
    _seed_core_internal_entry(project)

    # Baseline — clean tree, all three surfaces green.
    assert run_cli(project.root, "lock", "--check").returncode == 0
    assert run_cli(project.root, "doctor").returncode == 0
    assert run_cli(project.root, "verify").returncode == 0

    # Delete (not tamper) the core-internal file.
    (project.root / ".tess" / "core" / "personas" / "fixture.md").unlink()

    d = run_cli(project.root, "doctor")
    assert d.returncode == 1, f"doctor did not catch the deletion:\n{d.stdout}{d.stderr}"

    v = run_cli(project.root, "verify")
    assert v.returncode == 1, f"verify did not catch the deletion:\n{v.stdout}{v.stderr}"

    lk = run_cli(project.root, "lock", "--check")
    assert lk.returncode == 1, (
        f"lock --check did NOT catch the deleted core-internal file — the "
        f"#124 fail-open:\n{lk.stdout}{lk.stderr}"
    )
    assert "FAIL" in lk.stdout
    assert "MISSING" in lk.stdout
    assert ".tess/core/personas/fixture.md" in lk.stdout
    # #139 (was #3 pre-#139): the MISSING (deletion) sub-case gets its own
    # annotation, matching `verify`'s own "(core-internal — file missing)"
    # print for the same class of entry — the generic "no live path"
    # annotation (still used for the CORE-TAMPER/hash-mismatch sub-case
    # below) never actually matched verify's wording for a deletion.
    assert "(core-internal — file missing)" in lk.stdout


def test_lock_check_deletion_regression_is_the_only_new_failure_mode(project, run_cli):
    """Restoring the deleted file returns all three surfaces to green — the
    fix must not introduce a permanent/irreversible failure."""
    _seed_core_internal_entry(project)
    core_path = project.root / ".tess" / "core" / "personas" / "fixture.md"
    original = core_path.read_bytes()

    core_path.unlink()
    assert run_cli(project.root, "lock", "--check").returncode == 1

    core_path.write_bytes(original)
    r = run_cli(project.root, "lock", "--check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


# ---------------------------------------------------------------------------
# 3. Annotation for a null-live-path CORE-TAMPER (hash mismatch, not
#    deletion) — `verify` already prints "(core-internal — no live path)"
#    for this class; `lock --check` did not.
# ---------------------------------------------------------------------------

def test_lock_check_annotates_core_internal_tamper(project, run_cli):
    _seed_core_internal_entry(project)
    core_path = project.root / ".tess" / "core" / "personas" / "fixture.md"
    core_path.write_text("persona body v1 — TAMPERED\n", encoding="utf-8")

    r = run_cli(project.root, "lock", "--check")
    assert r.returncode == 1
    assert "CORE-TAMPER" in r.stdout
    assert ".tess/core/personas/fixture.md" in r.stdout
    assert "(core-internal — no live path)" in r.stdout

    # An ordinary (non-core-internal) tamper must NOT be annotated — the
    # annotation only applies to live_path: null entries.
    v = run_cli(project.root, "verify")
    assert v.returncode == 1


def test_lock_check_ordinary_tamper_has_no_core_internal_annotation(project, run_cli):
    """Regression guard for the annotation's scope: a normal core-managed
    entry (live_path set) that is tampered must NOT be mislabeled
    "core-internal" — the annotation is conditioned on `live_rel` being
    falsy, not on the report just happening to be a CORE-TAMPER."""
    project.add("conductor/a.md", "alpha\n")
    project.write()
    core_a = project.root / ".tess" / "core" / "conductor" / "a.md"
    core_a.write_text("alpha v2 reviewed\n")
    project.write_live("conductor/a.md", "alpha v2 reviewed\n")

    r = run_cli(project.root, "lock", "--check")
    assert r.returncode == 1
    assert "CORE-TAMPER" in r.stdout
    assert "conductor/a.md" in r.stdout
    assert "(core-internal — no live path)" not in r.stdout


# ---------------------------------------------------------------------------
# 2. [LOW, Reid] structural parity pin — `cmd_lock`'s skip predicate must
#    fall through to `doctor_check_file` for a staged, live_path: null, NO
#    base_sha entry the same way `cmd_doctor`'s own predicate does, instead
#    of skipping it outright. Harmless for the exit code today (the staged
#    branch is a no-op for blocking status either way — see
#    tests/test_agents_md_template_lock_wiring.py's own
#    test_lock_check_still_skips_staged_entries_with_no_base_sha for that
#    outcome-level guarantee); this test pins the STRUCTURE — that
#    `doctor_check_file` is genuinely invoked for this entry by `cmd_lock`,
#    not merely that the exit code happens to still be 0 — so a future
#    change to the staged branch's failure semantics can't silently apply to
#    `doctor` while never reaching `lock --check`.
# ---------------------------------------------------------------------------

def test_lock_check_staged_no_base_sha_falls_through_to_doctor_check_file(
    project, monkeypatch
):
    project.files[".tess/core/personas/staged-fixture.md"] = {
        "status": "staged",
        "tier": "normal",
        "base_sha": "",
        "live_path": None,
    }
    (project.root / ".tess" / "core" / "personas").mkdir(parents=True, exist_ok=True)
    project.write()

    calls = []
    real_check = project.mod.doctor_check_file

    def spy(core_key, attrs, root):
        calls.append(core_key)
        return real_check(core_key, attrs, root)

    monkeypatch.setattr(project.mod, "doctor_check_file", spy)

    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_lock(ns(check=True, regen=False), project.root)
    assert ei.value.code == 0

    assert ".tess/core/personas/staged-fixture.md" in calls, (
        "lock --check skipped the staged/no-base_sha entry outright instead "
        "of falling through to doctor_check_file the way cmd_doctor's own "
        "status == 'staged' fallthrough does — structural parity broke even "
        "though the exit code (0) happened to stay the same"
    )


def test_lock_check_still_exempts_truly_uncheckable_entries(project, run_cli):
    """Non-regression, restated end-to-end (companion to the in-process spy
    test above): a staged, no-base_sha, no-live_path entry must still leave
    `lock --check` green and must never be named in its output — falling
    through to `doctor_check_file` must stay a structural-only change, not a
    new blocking condition."""
    project.files[".tess/core/personas/staged-fixture.md"] = {
        "status": "staged",
        "tier": "normal",
        "base_sha": "",
        "live_path": None,
    }
    (project.root / ".tess" / "core" / "personas").mkdir(parents=True, exist_ok=True)
    project.write()

    r = run_cli(project.root, "lock", "--check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "staged-fixture.md" not in r.stdout
