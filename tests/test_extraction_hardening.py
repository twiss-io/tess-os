"""
Extraction hardening (C2 / C4): a poisoned upstream archive cannot land files in
the tree even after the signature verifies.

  * A symlink under .tess/core/ is rejected (C2 — symlink-escape / TOCTOU); the
    symlink never materializes in staging.
  * A '.git'-component path is rejected: the engine's C4 check refuses any path
    component that normalizes to '.git', and git's own protectHFS refuses to
    check it out at clone time (defense in depth). Either way the upgrade aborts
    and no '.git' path ever appears in staging.

Both run after a valid signature (the guards live in the extraction loop, which
only runs once verification passes), so a real signed upstream is used.
"""

from __future__ import annotations

import pytest

from conftest import make_upstream


def _lock_with_upstream(project, up, fingerprint=""):
    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = fingerprint
    project.write()


def test_symlink_in_upstream_core_is_rejected(project, gpg_key, tmp_path):
    up = make_upstream(
        tmp_path / "up_sym", gpg_key, "v2.0.0", sign="signed",
        core_files={".tess/core/conductor/guardrails.md": "g\n"},
        symlinks={".tess/core/conductor/evil.md": "/etc/passwd"},
    )
    _lock_with_upstream(project, up, fingerprint=gpg_key.fpr)

    with pytest.raises(SystemExit) as ei:
        project.mod.fetch_to_staging(project.root, "v2.0.0")
    msg = str(ei.value)
    assert "symlink" in msg.lower() or "SECURITY REJECT" in msg

    staging = project.root / ".tess" / "staging"
    # The poisoned symlink never lands, and nothing under staging is a symlink.
    assert not (staging / ".tess" / "core" / "conductor" / "evil.md").exists()
    assert [p for p in staging.rglob("*") if p.is_symlink()] == []


def test_dotgit_component_in_upstream_is_rejected(project, gpg_key, tmp_path):
    # '.git.' normalizes to '.git' (trailing-dot strip). Committed with
    # protections off so it reaches the upstream at all.
    up = make_upstream(
        tmp_path / "up_dotgit", gpg_key, "v2.0.0", sign="signed",
        core_files={
            ".tess/core/conductor/guardrails.md": "g\n",
            ".tess/core/conductor/.git./hooks/post-checkout": "#!/bin/sh\necho pwned\n",
        },
        unsafe_paths=True,
    )
    _lock_with_upstream(project, up, fingerprint=gpg_key.fpr)

    with pytest.raises(SystemExit) as ei:
        project.mod.fetch_to_staging(project.root, "v2.0.0")
    msg = str(ei.value)
    assert (
        "SECURITY REJECT" in msg
        or "PATH TRAVERSAL" in msg
        or "clone failed" in msg.lower()
        or ".git" in msg.lower()
    ), f"unexpected rejection message: {msg!r}"

    # No '.git'-normalized component ever materializes under staging.
    staging = project.root / ".tess" / "staging"
    for p in staging.rglob("*"):
        assert not any(part.lower().rstrip(". ") == ".git" for part in p.parts)
