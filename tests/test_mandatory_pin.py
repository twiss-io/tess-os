"""
MANDATORY PINNING + TOFU (C1 / C3).

  * Empty trusted_key_fingerprint does NOT mean "skip verification": an unsigned
    upstream is still HARD-REFUSED on both fetch and self-update — signing is
    mandatory regardless of pin state.
  * Empty pin + a properly signed tag → TOFU: the signing fingerprint is recorded
    (pinned) in tess.lock on first use.
  * A pinned-but-wrong fingerprint is REJECTED even with a valid signature, and
    nothing is extracted.

Uses a real local upstream signed with a generated GPG key.
"""

from __future__ import annotations

import pytest

from conftest import make_upstream, ns


def _lock_with_upstream(project, up, fingerprint=""):
    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = fingerprint
    project.write()


def _staged_files(project):
    return [p for p in (project.root / ".tess" / "staging").rglob("*") if p.is_file()]


def test_tofu_records_fingerprint_on_first_use(project, gpg_key, tmp_path):
    up = make_upstream(tmp_path / "up_tofu", gpg_key, "v2.0.0", sign="signed")
    _lock_with_upstream(project, up, fingerprint="")          # no pin → TOFU
    # TOFU is now opt-in (fail-closed default); pass allow_tofu to take the path.
    project.mod.fetch_to_staging(project.root, "v2.0.0", allow_tofu=True)

    lock = project.mod.load_lock(project.root)
    pinned = (lock["framework"].get("trusted_key_fingerprint") or "")
    assert pinned.upper() == gpg_key.fpr.upper(), "TOFU did not pin the signing key"
    # ...and the fetch still extracted the verified content.
    assert _staged_files(project)


def test_empty_pin_unsigned_tag_is_hard_refused_on_fetch(project, gpg_key, tmp_path):
    up = make_upstream(tmp_path / "up_uns", gpg_key, "v2.0.0", sign="lightweight")
    _lock_with_upstream(project, up, fingerprint="")          # empty pin is NOT a bypass
    with pytest.raises(SystemExit) as ei:
        project.mod.fetch_to_staging(project.root, "v2.0.0")
    assert "SECURITY REJECT" in str(ei.value)
    # No pin recorded, nothing extracted.
    lock = project.mod.load_lock(project.root)
    assert (lock["framework"].get("trusted_key_fingerprint") or "") == ""
    assert _staged_files(project) == []


def test_empty_pin_unsigned_tag_is_hard_refused_on_self_update(project, gpg_key, tmp_path):
    project.add("conductor/a.md", "alpha\n")
    up = make_upstream(
        tmp_path / "up_su_uns", gpg_key, "v2.0.1", sign="lightweight",
        engine_bytes=b"#!/usr/bin/env python3\n# new engine\n",
    )
    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = ""
    project.write()

    engine_path = project.root / ".tess" / "bin" / "tessctl"
    before = engine_path.read_bytes()
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_self_update(ns(ref="v2.0.1", to=None), project.root)
    assert "SECURITY REJECT" in str(ei.value)
    assert engine_path.read_bytes() == before                # engine untouched


def test_pinned_wrong_fingerprint_is_rejected(project, gpg_key, tmp_path):
    up = make_upstream(tmp_path / "up_wrong", gpg_key, "v2.0.0", sign="signed")
    # Valid 40-hex fingerprint, but NOT the real signing key.
    _lock_with_upstream(project, up, fingerprint="DEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF")
    with pytest.raises(SystemExit) as ei:
        project.mod.fetch_to_staging(project.root, "v2.0.0")
    assert "SECURITY REJECT" in str(ei.value)
    assert _staged_files(project) == []
