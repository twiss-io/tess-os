"""
FAIL-CLOSED FIRST USE (Cyra) — an EMPTY trusted_key_fingerprint is not an
implicit "trust whatever signs it".  With no pin and no explicit opt-in, a SIGNED
upstream is still HARD-REFUSED on both fetch and self-update.  Trust-on-first-use
only happens when the operator passes --trust-on-first-use (CLI) / allow_tofu
(API), and when it does, the signing fingerprint is pinned to tess.lock.

Distinct from test_mandatory_pin.py, which covers UNSIGNED upstreams (always
rejected) and wrong-pin rejection.  Here the upstream is correctly signed — the
refusal is purely the fail-closed first-use posture.
"""

from __future__ import annotations

import pytest

from conftest import ENGINE_SRC, make_upstream, ns

ORIGINAL_ENGINE = ENGINE_SRC.read_bytes()
SU_MARKER = b"\n# FAILCLOSED-SELFUPDATE-MARKER v2.0.1\n"


def _lock(project, up, fingerprint=""):
    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = fingerprint
    project.write()


def _staged(project):
    return [p for p in (project.root / ".tess" / "staging").rglob("*") if p.is_file()]


def _scaffold_render(project):
    """Minimal template + settings-core so a full CLI update's render step does
    not hard-exit (untracked → doctor/verify ignore them)."""
    tpl = project.root / ".tess" / "core" / "templates" / "CLAUDE.md.tpl"
    tpl.parent.mkdir(parents=True, exist_ok=True)
    tpl.write_text("# Tess OS\n\nRoot: {{TESS_ROOT}}\n", encoding="utf-8")
    (project.root / ".tess" / "core" / "settings-core.json").write_text(
        '{"root": "{{TESS_ROOT}}"}\n', encoding="utf-8")


# ---------------------------------------------------------------------------
# FETCH (fetch_to_staging) — API level
# ---------------------------------------------------------------------------

def test_fetch_signed_empty_pin_no_tofu_hard_refuses(project, gpg_key, tmp_path):
    up = make_upstream(tmp_path / "up_fc1", gpg_key, "v2.0.0", sign="signed")
    _lock(project, up, fingerprint="")                     # no pin, no opt-in
    with pytest.raises(SystemExit) as ei:
        project.mod.fetch_to_staging(project.root, "v2.0.0")  # allow_tofu defaults False
    assert "SECURITY REFUSE" in str(ei.value)
    assert "trust-on-first-use" in str(ei.value)
    # Nothing pinned, nothing extracted.
    lock = project.mod.load_lock(project.root)
    assert (lock["framework"].get("trusted_key_fingerprint") or "") == ""
    assert _staged(project) == []


def test_fetch_signed_empty_pin_with_tofu_pins(project, gpg_key, tmp_path):
    up = make_upstream(tmp_path / "up_fc2", gpg_key, "v2.0.0", sign="signed")
    _lock(project, up, fingerprint="")
    project.mod.fetch_to_staging(project.root, "v2.0.0", allow_tofu=True)
    lock = project.mod.load_lock(project.root)
    assert (lock["framework"].get("trusted_key_fingerprint") or "").upper() == gpg_key.fpr.upper()
    assert _staged(project)                                # verified content extracted


# ---------------------------------------------------------------------------
# SELF-UPDATE (cmd_self_update) — API level
# ---------------------------------------------------------------------------

def test_self_update_signed_empty_pin_no_tofu_hard_refuses(project, gpg_key, tmp_path):
    project.add("conductor/a.md", "alpha\n")
    up = make_upstream(
        tmp_path / "up_fc3", gpg_key, "v2.0.1", sign="signed",
        engine_bytes=ORIGINAL_ENGINE + SU_MARKER,
    )
    _lock(project, up, fingerprint="")
    engine_path = project.root / ".tess" / "bin" / "tessctl"
    before = engine_path.read_bytes()
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_self_update(ns(ref="v2.0.1", to=None, trust_on_first_use=False), project.root)
    assert "SECURITY REFUSE" in str(ei.value)
    assert engine_path.read_bytes() == before              # engine untouched
    lock = project.mod.load_lock(project.root)
    assert (lock["framework"].get("trusted_key_fingerprint") or "") == ""


def test_self_update_signed_empty_pin_with_tofu_pins(project, gpg_key, tmp_path):
    project.add("conductor/a.md", "alpha\n")
    up = make_upstream(
        tmp_path / "up_fc4", gpg_key, "v2.0.1", sign="signed",
        core_files={".tess/core/conductor/guardrails.md": "g\n"},
        engine_bytes=ORIGINAL_ENGINE + SU_MARKER,
    )
    _lock(project, up, fingerprint="")
    project.mod.cmd_self_update(ns(ref="v2.0.1", to=None, trust_on_first_use=True), project.root)
    engine_path = project.root / ".tess" / "bin" / "tessctl"
    assert SU_MARKER in engine_path.read_bytes()           # new engine installed
    lock = project.mod.load_lock(project.root)
    assert (lock["framework"].get("trusted_key_fingerprint") or "").upper() == gpg_key.fpr.upper()


# ---------------------------------------------------------------------------
# CLI level — proves the --trust-on-first-use flag is wired in build_parser
# ---------------------------------------------------------------------------

def test_cli_update_no_flag_refuses(project, gpg_key, tmp_path, run_cli):
    project.add("conductor/intro.md", "intro v1\n", status="core-managed")
    _scaffold_render(project)
    up = make_upstream(
        tmp_path / "up_cli1", gpg_key, "v2.1.0", sign="signed",
        core_files={".tess/core/conductor/intro.md": "intro v2\n"},
        lock_files={".tess/core/conductor/intro.md":
                    {"status": "core-managed", "tier": "normal", "live_path": "conductor/intro.md"}},
    )
    _lock(project, up, fingerprint="")
    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    assert r.returncode != 0
    assert "SECURITY REFUSE" in (r.stdout + r.stderr)
    # No pin recorded.
    lock = project.mod.load_lock(project.root)
    assert (lock["framework"].get("trusted_key_fingerprint") or "") == ""


def test_cli_update_with_trust_flag_pins_and_succeeds(project, gpg_key, tmp_path, run_cli):
    project.add("conductor/intro.md", "intro v1\n", status="core-managed")
    _scaffold_render(project)
    up = make_upstream(
        tmp_path / "up_cli2", gpg_key, "v2.1.0", sign="signed",
        core_files={".tess/core/conductor/intro.md": "intro v2\n"},
        lock_files={".tess/core/conductor/intro.md":
                    {"status": "core-managed", "tier": "normal", "live_path": "conductor/intro.md"}},
    )
    _lock(project, up, fingerprint="")
    r = run_cli(project.root, "update", "--ref", "v2.1.0", "--trust-on-first-use")
    assert r.returncode == 0, f"update --trust-on-first-use failed:\n{r.stdout}\n{r.stderr}"
    lock = project.mod.load_lock(project.root)
    assert (lock["framework"].get("trusted_key_fingerprint") or "").upper() == gpg_key.fpr.upper()
    assert project.read_live("conductor/intro.md") == "intro v2\n"
