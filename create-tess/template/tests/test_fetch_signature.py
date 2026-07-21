"""
FETCH signature verification (fetch_to_staging).

Signed annotated tags are accepted and extracted into .tess/staging/; unsigned
tags (annotated-no-sig and lightweight) are REJECTED with no extraction; a
pinned-but-mismatched key fingerprint is REJECTED even with a valid signature.

Uses a real local upstream git repo signed with a generated GPG key, and a real
`git verify-tag`. Pure parsing logic is unit-tested without GPG.
"""

from __future__ import annotations

import pytest

from conftest import make_upstream


# ---------------------------------------------------------------------------
# _parse_gpg_fingerprint — pure, no GPG required
# ---------------------------------------------------------------------------

def test_parse_fingerprint_validsig(engine):
    raw = (
        "[GNUPG:] NEWSIG\n"
        "[GNUPG:] GOODSIG ABC Tess <t@x>\n"
        "[GNUPG:] VALIDSIG 0CAF02648D3EAE8EE7422A5260047367D37F1179 2026-06-27 0\n"
    )
    assert engine._parse_gpg_fingerprint(raw) == "0CAF02648D3EAE8EE7422A5260047367D37F1179"


def test_parse_fingerprint_human_readable_fallback(engine):
    raw = "gpg: Signature made ...\ngpg:                using RSA key ABCDEF0123456789ABCD\n"
    assert engine._parse_gpg_fingerprint(raw) == "ABCDEF0123456789ABCD"


def test_parse_fingerprint_none(engine):
    assert engine._parse_gpg_fingerprint("nothing here\n") == ""


# ---------------------------------------------------------------------------
# fetch_to_staging — end-to-end with real signatures
# ---------------------------------------------------------------------------

def _lock_with_upstream(project, upstream_path, fingerprint=""):
    project.framework["upstream"] = str(upstream_path)
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = fingerprint
    project.write()


def test_signed_tag_is_accepted_and_extracted(project, gpg_key, tmp_path):
    up = make_upstream(
        tmp_path / "upstream", gpg_key, "v2.0.0", sign="signed",
        core_files={
            ".tess/core/conductor/guardrails.md": "signed guardrails\n",
            ".tess/core/conductor/ff.md": "signed ff\n",
        },
    )
    _lock_with_upstream(project, up)
    # Empty pin → fail-closed by default; opt into TOFU explicitly (first use).
    project.mod.fetch_to_staging(project.root, "v2.0.0", allow_tofu=True)

    staged = project.root / ".tess" / "staging" / ".tess" / "core" / "conductor"
    assert (staged / "guardrails.md").read_text() == "signed guardrails\n"
    assert (staged / "ff.md").read_text() == "signed ff\n"


def test_lightweight_unsigned_tag_is_rejected(project, gpg_key, tmp_path):
    up = make_upstream(tmp_path / "up_lw", gpg_key, "v2.0.0", sign="lightweight")
    _lock_with_upstream(project, up)
    with pytest.raises(SystemExit) as ei:
        project.mod.fetch_to_staging(project.root, "v2.0.0")
    assert "SECURITY REJECT" in str(ei.value)
    # No extraction took place.
    staged = list((project.root / ".tess" / "staging").rglob("*"))
    assert [p for p in staged if p.is_file()] == []


def test_annotated_unsigned_tag_is_rejected(project, gpg_key, tmp_path):
    up = make_upstream(tmp_path / "up_anno", gpg_key, "v2.0.0", sign="annotated")
    _lock_with_upstream(project, up)
    # allow_tofu=True so we reach the signature check (not the empty-pin refuse);
    # an annotated-but-unsigned tag must still be REJECTED, nothing extracted.
    with pytest.raises(SystemExit) as ei:
        project.mod.fetch_to_staging(project.root, "v2.0.0", allow_tofu=True)
    assert "SECURITY REJECT" in str(ei.value)


def test_pinned_matching_fingerprint_is_accepted(project, gpg_key, tmp_path):
    up = make_upstream(tmp_path / "up_pin_ok", gpg_key, "v2.0.0", sign="signed")
    _lock_with_upstream(project, up, fingerprint=gpg_key.fpr)
    project.mod.fetch_to_staging(project.root, "v2.0.0")
    staged = project.root / ".tess" / "staging" / ".tess" / "core" / "conductor"
    assert (staged / "guardrails.md").exists()


def test_pinned_wrong_fingerprint_is_rejected(project, gpg_key, tmp_path):
    up = make_upstream(tmp_path / "up_pin_bad", gpg_key, "v2.0.0", sign="signed")
    # Pin a fingerprint that does NOT match the real signing key.
    _lock_with_upstream(project, up, fingerprint="DEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF")
    with pytest.raises(SystemExit) as ei:
        project.mod.fetch_to_staging(project.root, "v2.0.0")
    assert "wrong key" in str(ei.value).lower() or "SECURITY REJECT" in str(ei.value)
    staged = [p for p in (project.root / ".tess" / "staging").rglob("*") if p.is_file()]
    assert staged == []
