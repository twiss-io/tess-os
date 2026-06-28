"""
E2E CLEAN-UPGRADE acceptance — encodes the end-state of a successful `tessctl
update`, which the unit suite never asserted (the suite passed 110 while the
upgrade was broken because nothing checked that core advanced, new files were
adopted, the version bumped, or that verify stayed honest).

Runs cmd_update THROUGH THE CLI against a real GPG-signed local upstream, then
asserts the six acceptance criteria:
  (a) doctor EXIT 0
  (b) a NEW upstream file is present in live + in the lock
  (c) base_sha ADVANCED — core now holds the new upstream bytes
  (d) framework.version bumped to the fetched tag
  (e) an operator local edit PRESERVED (3-way merged, not clobbered)
  (f) verify EXIT 0

Plus cmd_update ref-precedence (--ref > --to > framework.upstream_ref).
"""

from __future__ import annotations

import pytest

from conftest import make_upstream, ns


def _scaffold_render(project):
    """cmd_update Step 7 renders CLAUDE.md + settings.json; give it the minimal
    template + settings-core.json so render does not hard-exit. Neither file is
    tracked in tess.lock, so doctor/verify ignore them."""
    tpl = project.root / ".tess" / "core" / "templates" / "CLAUDE.md.tpl"
    tpl.parent.mkdir(parents=True, exist_ok=True)
    tpl.write_text("# Tess OS\n\nRoot: {{TESS_ROOT}}\n", encoding="utf-8")
    sc = project.root / ".tess" / "core" / "settings-core.json"
    sc.write_text('{"root": "{{TESS_ROOT}}"}\n', encoding="utf-8")


def test_clean_upgrade_e2e_acceptance(project, gpg_key, tmp_path, run_cli):
    # -- Instance state at v2.0.0 --------------------------------------------
    # A plain core-managed file that upstream advances.
    project.add("conductor/intro.md", "intro v1\n", status="core-managed")
    # A locally-modified file: the operator edited line 1; upstream will edit
    # line 3 → a clean 3-way merge must preserve the operator's edit.
    project.add("conductor/custom.md", "A\nB\nC\n", status="locally-modified")
    project.write_live("conductor/custom.md", "A-LOCAL\nB\nC\n")
    _scaffold_render(project)

    # -- Signed upstream at v2.1.0: advances intro, edits custom, ADDS newcmd --
    up = make_upstream(
        tmp_path / "upstream", gpg_key, "v2.1.0", sign="signed",
        core_files={
            ".tess/core/conductor/intro.md": "intro v2\n",
            ".tess/core/conductor/custom.md": "A\nB\nC-UP\n",
            ".tess/core/conductor/newcmd.md": "brand new\n",
        },
        lock_files={
            ".tess/core/conductor/intro.md":
                {"status": "core-managed", "tier": "normal", "live_path": "conductor/intro.md"},
            ".tess/core/conductor/custom.md":
                {"status": "core-managed", "tier": "normal", "live_path": "conductor/custom.md"},
            ".tess/core/conductor/newcmd.md":
                {"status": "core-managed", "tier": "normal", "live_path": "conductor/newcmd.md"},
        },
    )
    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr  # production path: key pinned
    lock0 = project.write()
    v1_intro_sha = lock0["files"][".tess/core/conductor/intro.md"]["base_sha"]

    # -- THE UPGRADE (through the CLI) ---------------------------------------
    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    assert r.returncode == 0, f"update failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"

    lock = project.lock()

    # (a) doctor EXIT 0
    d = run_cli(project.root, "doctor")
    assert d.returncode == 0, f"doctor not clean after upgrade:\n{d.stdout}\n{d.stderr}"

    # (b) NEW upstream file present in live + in the lock
    assert project.read_live("conductor/newcmd.md") == "brand new\n"
    assert ".tess/core/conductor/newcmd.md" in lock["files"], "new file not adopted into lock"
    assert lock["files"][".tess/core/conductor/newcmd.md"]["live_path"] == "conductor/newcmd.md"

    # (c) base_sha ADVANCED — core holds the new upstream bytes, pin reflects them
    assert project.core(".tess/core/conductor/intro.md").read_bytes() == b"intro v2\n"
    new_intro_sha = lock["files"][".tess/core/conductor/intro.md"]["base_sha"]
    assert new_intro_sha == project.mod.sha256_bytes(b"intro v2\n")
    assert new_intro_sha != v1_intro_sha, "base_sha did not advance (broken fast-forward)"

    # (d) framework.version bumped to the fetched tag (v stripped)
    assert lock["framework"]["version"] == "2.1.0"
    assert lock["framework"]["upstream_ref"] == "v2.1.0"

    # (e) operator local edit PRESERVED — and the upstream change merged in
    merged = project.read_live("conductor/custom.md")
    assert "A-LOCAL" in merged, "operator's local edit was clobbered by the upgrade"
    assert "C-UP" in merged, "upstream change was not merged in"
    assert "<<<<<<<" not in merged

    # (f) verify EXIT 0
    v = run_cli(project.root, "verify")
    assert v.returncode == 0, f"verify not clean after upgrade:\n{v.stdout}\n{v.stderr}"
    assert "verify: OK" in v.stdout


# ---------------------------------------------------------------------------
# ref precedence: --ref > --to > framework.upstream_ref
# ---------------------------------------------------------------------------

def test_ref_precedence_ref_wins_over_to_and_lock(engine):
    lock = {"framework": {"upstream_ref": "v_lock"}}
    assert engine._resolve_update_ref(ns(ref="v_ref", to="v_to"), lock) == "v_ref"


def test_ref_precedence_to_wins_over_lock(engine):
    lock = {"framework": {"upstream_ref": "v_lock"}}
    assert engine._resolve_update_ref(ns(ref=None, to="v_to"), lock) == "v_to"


def test_ref_precedence_falls_back_to_lock(engine):
    lock = {"framework": {"upstream_ref": "v_lock"}}
    assert engine._resolve_update_ref(ns(ref=None, to=None), lock) == "v_lock"


def test_ref_precedence_no_ref_anywhere_exits(engine):
    lock = {"framework": {"upstream_ref": ""}}
    with pytest.raises(SystemExit):
        engine._resolve_update_ref(ns(ref=None, to=None), lock)
