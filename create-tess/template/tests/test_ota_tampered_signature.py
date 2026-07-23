"""
Regression coverage for issue #22 (OTA upgrade regression tests) — the third
signature-rejection scenario the issue names alongside "unsigned tag" and
"wrong key": a TAMPERED tag.

test_mandatory_pin.py and test_fail_closed_first_use.py already cover:
  * unsigned (lightweight) tags → hard-refused
  * a valid signature from the WRONG key (pinned mismatch) → rejected

Neither covers a tag whose signature bytes were altered AFTER signing while
the tag object otherwise remains well-formed (still resolves to an annotated
tag object — C4's "is a tag object" check still passes). That is a distinct
failure mode from "no signature" and from "wrong key", and is what this file
proves is rejected on both `fetch_to_staging` and `cmd_self_update` — pinned
and TOFU alike.
"""

from __future__ import annotations

import pytest

from conftest import ENGINE_SRC, corrupt_tag_signature, make_upstream, ns

ORIGINAL_ENGINE = ENGINE_SRC.read_bytes()


def _staged_files(project):
    return [p for p in (project.root / ".tess" / "staging").rglob("*") if p.is_file()]


# ---------------------------------------------------------------------------
# fetch_to_staging
# ---------------------------------------------------------------------------


def test_fetch_rejects_tampered_signature_pinned(project, gpg_key, tmp_path):
    up = make_upstream(tmp_path / "up_tamper_pinned", gpg_key, "v2.0.0", sign="signed")
    corrupt_tag_signature(up, "v2.0.0")

    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr  # correct key pinned
    project.write()

    with pytest.raises(SystemExit) as ei:
        project.mod.fetch_to_staging(project.root, "v2.0.0")
    assert "SECURITY REJECT" in str(ei.value)
    assert _staged_files(project) == [], "tampered signature must not extract any files"


def test_fetch_rejects_tampered_signature_before_tofu_pin(project, gpg_key, tmp_path):
    """A corrupted signature must be caught BEFORE trust-on-first-use pins
    anything — TOFU pinning a fingerprint extracted from a tag whose
    signature doesn't verify would be nonsensical (there is no valid
    fingerprint to extract in the first place)."""
    up = make_upstream(tmp_path / "up_tamper_tofu", gpg_key, "v2.0.0", sign="signed")
    corrupt_tag_signature(up, "v2.0.0")

    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = ""
    project.write()

    with pytest.raises(SystemExit) as ei:
        project.mod.fetch_to_staging(project.root, "v2.0.0", allow_tofu=True)
    assert "SECURITY REJECT" in str(ei.value)

    lock = project.mod.load_lock(project.root)
    assert (lock["framework"].get("trusted_key_fingerprint") or "") == ""
    assert _staged_files(project) == []


# ---------------------------------------------------------------------------
# cmd_self_update
# ---------------------------------------------------------------------------


def test_self_update_rejects_tampered_signature(project, gpg_key, tmp_path):
    project.add("conductor/a.md", "alpha\n")
    up = make_upstream(
        tmp_path / "up_su_tamper", gpg_key, "v2.0.1", sign="signed",
        core_files={".tess/core/conductor/guardrails.md": "g\n"},
        engine_bytes=ORIGINAL_ENGINE + b"\n# SHOULD-NEVER-INSTALL-TAMPERED\n",
    )
    corrupt_tag_signature(up, "v2.0.1")

    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr
    project.write()

    engine_path = project.root / ".tess" / "bin" / "tessctl"
    before = engine_path.read_bytes()

    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_self_update(ns(ref="v2.0.1", to=None, trust_on_first_use=False), project.root)
    assert "SECURITY REJECT" in str(ei.value)

    # Engine untouched — no backup should even be attempted.
    assert engine_path.read_bytes() == before
    backup_path = engine_path.with_suffix(".bak")
    assert not backup_path.exists()


def test_self_update_rejects_tampered_signature_wrong_key_distinct_message(project, gpg_key, tmp_path):
    """Sanity/spot-check: a tampered signature and a wrong-key signature are
    BOTH rejected, but via genuinely different gpg failure modes (this proves
    the tamper fixture isn't accidentally degenerating into the already-
    covered wrong-key case) — tampered trips gpg's own BADSIG/NODATA path
    inside `git verify-tag`, not C3's exact-fingerprint-mismatch branch."""
    up = make_upstream(tmp_path / "up_su_tamper2", gpg_key, "v2.0.1", sign="signed")
    corrupt_tag_signature(up, "v2.0.1")
    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr
    project.write()

    with pytest.raises(SystemExit) as ei:
        project.mod.fetch_to_staging(project.root, "v2.0.1")
    msg = str(ei.value)
    assert "SECURITY REJECT" in msg
    # C3's wrong-key message names the pinned/signing fingerprints explicitly;
    # the tamper path fails earlier, at the isolated-keyring verify-tag call,
    # and never gets far enough to extract/compare a signing fingerprint.
    assert "signed by wrong key" not in msg
    assert "failed isolated-keyring" in msg
