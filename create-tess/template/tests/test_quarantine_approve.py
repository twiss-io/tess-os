"""
Quarantine-on-security-tamper + approve-requires-rationale.

Security-tier doctrine edited in place must NOT auto-flip to locally-modified:
the authoritative version is pinned back to live, the attempted edit is parked in
.tess/quarantine/, and the only way out is `tessctl approve --rationale ...`.
"""

from __future__ import annotations

import pytest

from conftest import ns

LR = "conductor/guardrails.md"          # security-tier (in SECURITY_TIER_PATHS)
AUTHORITATIVE = "GUARDRAILS\n"
WEAKENED = "GUARDRAILS weakened by an agent\n"


def _quarantine_setup(project):
    project.add(LR, AUTHORITATIVE, tier="security")
    project.write()
    project.write_live(LR, WEAKENED)
    project.mod.cmd_capture(
        ns(path=LR, all=False, dry_run=False, rationale="", source="agent"),
        project.root,
    )
    return project.mod.load_lock(project.root)


def test_capture_security_tier_quarantines(project):
    lock = _quarantine_setup(project)
    # Authoritative version pinned back as live — the weakened edit never survives.
    assert project.read_live(LR) == AUTHORITATIVE
    # The attempted edit is preserved for review.
    q = project.root / ".tess" / "quarantine" / LR
    assert q.exists()
    assert q.read_text() == WEAKENED
    # Lock status flipped to quarantined.
    ck = ".tess/core/" + LR
    assert lock["files"][ck]["status"] == "quarantined"


def test_approve_requires_rationale(project):
    _quarantine_setup(project)
    with pytest.raises(SystemExit):
        project.mod.cmd_approve(ns(path=LR, rationale=""), project.root)
    # Still quarantined; authoritative still live.
    lock = project.mod.load_lock(project.root)
    ck = ".tess/core/" + LR
    assert lock["files"][ck]["status"] == "quarantined"
    assert project.read_live(LR) == AUTHORITATIVE


def test_approve_with_rationale_applies_edit(project):
    _quarantine_setup(project)
    project.mod.cmd_approve(
        ns(path=LR, rationale="operator authorized this tightening"),
        project.root,
    )
    lock = project.mod.load_lock(project.root)
    ck = ".tess/core/" + LR
    assert lock["files"][ck]["status"] == "locally-modified"
    assert lock["files"][ck]["approved_rationale"] == "operator authorized this tightening"
    # The approved edit is now the live content.
    assert project.read_live(LR) == WEAKENED


def test_capture_nonnormal_tier_requires_rationale(project):
    project.add("conductor/doc.md", "DOC\n", tier="doctrine")
    project.write()
    project.write_live("conductor/doc.md", "DOC edited\n")
    with pytest.raises(SystemExit):
        project.mod.cmd_capture(
            ns(path="conductor/doc.md", all=False, dry_run=False,
               rationale="", source="agent"),
            project.root,
        )


def test_capture_normal_tier_flips_locally_modified(project):
    project.add("conductor/n.md", "N\n", tier="normal")
    project.write()
    project.write_live("conductor/n.md", "N edited\n")
    project.mod.cmd_capture(
        ns(path="conductor/n.md", all=False, dry_run=False,
           rationale="", source="agent"),
        project.root,
    )
    lock = project.mod.load_lock(project.root)
    ck = ".tess/core/conductor/n.md"
    assert lock["files"][ck]["status"] == "locally-modified"
    # Normal-tier edit is kept (not pinned back).
    assert project.read_live("conductor/n.md") == "N edited\n"
