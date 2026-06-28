"""
doctor + verify.

  * clean tree → doctor/verify green (no SystemExit)
  * uncaptured live drift → doctor FAILs (exit 1)
  * .tess/core tamper (bytes != base_sha) → verify FAILs (exit 1)
  * security-tier live edit (status core-managed) → verify SECURITY DRIFT (exit 1)
"""

from __future__ import annotations

import pytest

from conftest import ns


def _clean_project(project):
    project.add("conductor/a.md", "alpha\n")
    project.add("agents/leah/README.md", "leah\n")
    project.add("conductor/guardrails.md", "GUARDRAILS\n", tier="security")
    project.write()
    return project


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

def test_doctor_clean_tree_is_green(project, capsys):
    _clean_project(project)
    project.mod.cmd_doctor(ns(json_out=False, fix=False, path=None), project.root)
    out = capsys.readouterr().out
    assert "doctor: OK" in out


def test_doctor_detects_uncaptured_drift(project, capsys):
    _clean_project(project)
    project.write_live("conductor/a.md", "alpha TAMPERED\n")
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_doctor(ns(json_out=False, fix=False, path=None), project.root)
    assert ei.value.code == 1
    out = capsys.readouterr().out
    assert "DRIFT" in out


def test_doctor_check_file_pristine(project):
    ck = project.add("conductor/p.md", "pristine\n")
    lock = project.write()
    r = project.mod.doctor_check_file(ck, lock["files"][ck], project.root)
    assert r["pristine"] is True
    assert r["drift"] is False
    assert r["issues"] == []


def test_doctor_check_file_flags_drift(project):
    ck = project.add("conductor/p.md", "pristine\n")
    lock = project.write()
    project.write_live("conductor/p.md", "edited\n")
    r = project.mod.doctor_check_file(ck, lock["files"][ck], project.root)
    assert r["pristine"] is False
    assert r["drift"] is True
    assert any("UNCAPTURED DRIFT" in i for i in r["issues"])


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def test_verify_clean_tree_is_green(project, capsys):
    _clean_project(project)
    project.mod.cmd_verify(ns(), project.root)
    out = capsys.readouterr().out
    assert "verify: OK" in out


def test_verify_detects_core_tamper(project, capsys):
    ck = _clean_project(project)  # returns project, not key
    # Tamper .tess/core bytes so they no longer match the pinned base_sha.
    (project.root / ".tess" / "core" / "conductor" / "a.md").write_text("HACKED CORE\n")
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_verify(ns(), project.root)
    assert ei.value.code == 1
    out = capsys.readouterr().out
    assert "CORE TAMPER" in out


def test_verify_detects_security_tier_drift(project, capsys):
    _clean_project(project)
    # Edit a security-tier file in place without quarantine.
    project.write_live("conductor/guardrails.md", "GUARDRAILS weakened\n")
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_verify(ns(), project.root)
    assert ei.value.code == 1
    out = capsys.readouterr().out
    assert "SECURITY DRIFT" in out
