"""v1.0 security audit — lifecycle fixes (tessctl update, approve, rollback,
resolve and the other status-changing commands).

Each test names its finding fingerprint. Every test here fails on 3eba77d:
  * tessctl:update:staging-bytes-not-rebound-to-verified-tag
  * tessctl:update-ref:no-version-floor-signed-rollback
  * tessctl:cmd_approve:quarantine-bytes-unbound-to-confirmation
  * tessctl:_rollback_from_manifest:self-attested-snapshot-restore-source
  * tessctl:cmd_resolve:security-tier-write-without-presence
  * coverage critic: override / reset / recruit / bench without presence
Anchors from in-process updates go to a fake OS-record home, never ~/.config.
"""
from __future__ import annotations

import io
import json
import os
import sys

import pytest

from conftest import HAS_GPG, make_upstream, ns
from fixtures.os_home import operator_home  # noqa: F401 — autouse: fake OS-record home

needs_gpg = pytest.mark.skipif(not HAS_GPG, reason="gpg not installed")

GUARD = "conductor/guardrails.md"          # security tier
GUARD_KEY = ".tess/core/" + GUARD
AUTHORITATIVE = "GUARDRAILS\n"
WEAKENED = "GUARDRAILS weakened by an agent\n"


class _Stream(io.StringIO):
    def __init__(self, text: str = "", tty: bool = True):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


def _tty(monkeypatch, typed: str = "", tty: bool = True):
    monkeypatch.setattr(sys, "stdin", _Stream(typed, tty=tty))
    out = _Stream("", tty=tty)
    monkeypatch.setattr(sys, "stdout", out)
    return out


def _exit_text(ei) -> str:
    return str(ei.value.code)


# ===========================================================================
# tessctl:update:staging-bytes-not-rebound-to-verified-tag
# ===========================================================================

def _scaffold_render(project):
    project.add(None, "# Tess OS\n\nRoot: {{TESS_ROOT}}\n",
                core_key=".tess/core/templates/CLAUDE.md.tpl", render_live=False)
    project.add(None, '{"root": "{{TESS_ROOT}}"}\n',
                core_key=".tess/core/settings-core.json", render_live=False)


def _update_project(project, gpg_key, tmp_path):
    project.add("conductor/intro.md", "intro v1\n")
    _scaffold_render(project)
    up = make_upstream(
        tmp_path / "upstream", gpg_key, "v2.1.0", sign="signed",
        core_files={
            ".tess/core/conductor/intro.md": "intro v2\n",
            ".tess/core/templates/CLAUDE.md.tpl": "# Tess OS\n\nRoot: {{TESS_ROOT}}\n",
            ".tess/core/settings-core.json": '{"root": "{{TESS_ROOT}}"}\n',
        },
        lock_files={".tess/core/conductor/intro.md":
                    {"status": "core-managed", "tier": "normal", "live_path": "conductor/intro.md"}},
    )
    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr
    project.write()


def _update_args(**kw):
    base = dict(ref="v2.1.0", to=None, dry_run=False, check=False, trust_on_first_use=False,
                allow_downgrade=False, verbose=True)
    base.update(kw)
    return ns(**base)


INTRO_STAGED = ".tess/staging/.tess/core/conductor/intro.md"
EVIL = b"intro EVIL (written after the signature check)\n"


@needs_gpg
def test_staging_rewritten_during_policy_prompt_window_is_refused(
        project, gpg_key, tmp_path, monkeypatch):
    """The finding's window: after fetch verified the tag, before the core
    advance. On 3eba77d the rewritten staged bytes were installed into core,
    re-pinned in tess.lock and anchored."""
    _update_project(project, gpg_key, tmp_path)
    real = project.mod._update_confirm_policy_rule_changes

    def agent_rewrites_staging(root, tag):
        real(root, tag)
        (root / INTRO_STAGED).write_bytes(EVIL)

    monkeypatch.setattr(project.mod, "_update_confirm_policy_rule_changes", agent_rewrites_staging)
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_update(_update_args(), project.root)
    assert "changed after the release signature was checked" in _exit_text(ei)
    assert project.core(".tess/core/conductor/intro.md").read_bytes() == b"intro v1\n"
    assert project.read_live("conductor/intro.md") == "intro v1\n"
    lock = project.lock()
    assert lock["framework"]["version"] == "2.0.0"
    assert lock["files"][".tess/core/conductor/intro.md"]["base_sha"] == \
        project.mod.sha256_bytes(b"intro v1\n")


@needs_gpg
def test_staging_rewritten_before_core_advance_rolls_the_update_back(
        project, gpg_key, tmp_path, monkeypatch):
    """A rewrite between per-file apply and the core advance (A1) is refused
    at A1's read; the transaction rolls back and nothing of EVIL survives."""
    _update_project(project, gpg_key, tmp_path)
    real = project.mod._apply_per_file_resolution

    def apply_then_tamper(root, lock, **kw):
        real(root, lock, **kw)
        (root / INTRO_STAGED).write_bytes(EVIL)

    monkeypatch.setattr(project.mod, "_apply_per_file_resolution", apply_then_tamper)
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_update(_update_args(), project.root)
    assert "changed after the release signature was checked" in _exit_text(ei)
    assert project.core(".tess/core/conductor/intro.md").read_bytes() == b"intro v1\n"
    assert project.lock()["framework"]["version"] == "2.0.0"
    assert EVIL not in (project.root / "conductor" / "intro.md").read_bytes()


@needs_gpg
def test_extra_file_planted_in_staging_is_refused(project, gpg_key, tmp_path, monkeypatch):
    _update_project(project, gpg_key, tmp_path)
    real = project.mod._update_confirm_policy_rule_changes

    def plant(root, tag):
        real(root, tag)
        p = root / ".tess/staging/.tess/core/conductor/planted.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"not in the release\n")

    monkeypatch.setattr(project.mod, "_update_confirm_policy_rule_changes", plant)
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_update(_update_args(), project.root)
    assert "not in the release" in _exit_text(ei)
    assert not project.core(".tess/core/conductor/planted.md").exists()


@needs_gpg
def test_clean_update_still_applies_and_repins_from_verified_hashes(project, gpg_key, tmp_path):
    _update_project(project, gpg_key, tmp_path)
    project.mod.cmd_update(_update_args(), project.root)
    lock = project.lock()
    assert lock["framework"]["version"] == "2.1.0"
    assert project.core(".tess/core/conductor/intro.md").read_bytes() == b"intro v2\n"
    assert lock["files"][".tess/core/conductor/intro.md"]["base_sha"] == \
        project.mod.sha256_bytes(b"intro v2\n")
    verified = project.mod._STAGING_STATE["verified"]
    assert verified[".tess/core/conductor/intro.md"] == project.mod.sha256_bytes(b"intro v2\n")
    assert "upstream-tess.lock" in verified


# ===========================================================================
# tessctl:update-ref:no-version-floor-signed-rollback
# ===========================================================================

def test_release_semver_order(engine):
    k = engine._release_semver_key
    assert k("v1.0.0-rc.1") < k("v1.0.0") < k("v1.0.1") < k("v1.10.0")
    assert k("v2.0.0-rc.2") < k("v2.0.0-rc.10")
    assert k("create-tess-v1.0.0") is None and k("main") is None


@pytest.mark.parametrize("ref,words", [
    ("v1.9.0", "older than the version you have"),
    ("v2.0.0-rc.1", "older than the version you have"),
    ("create-tess-v2.1.0", "create-tess setup package"),
    ("main", "not a Tess OS release tag"),
])
def test_update_refuses_older_or_non_release_refs_before_fetching(engine, ref, words):
    lock = {"framework": {"version": "2.0.0", "upstream_ref": "v2.0.0"}}
    with pytest.raises(SystemExit) as ei:
        engine._update_version_floor(ns(allow_downgrade=False), lock, ref, "update")
    assert words in _exit_text(ei)
    assert "Nothing was changed" in _exit_text(ei)


def test_same_or_newer_release_passes_the_floor(engine):
    lock = {"framework": {"version": "2.0.0", "upstream_ref": "v2.0.0"}}
    for ref in ("v2.0.0", "v2.0.1", "v3.0.0"):
        engine._update_version_floor(ns(allow_downgrade=False), lock, ref, "update")


def test_self_update_floor_uses_the_newer_of_version_and_upstream_ref(engine):
    """self-update moves upstream_ref but not version: v2.0.5 after a
    self-update to v2.1.0 is still a downgrade of the engine."""
    lock = {"framework": {"version": "2.0.0", "upstream_ref": "v2.1.0"}}
    with pytest.raises(SystemExit) as ei:
        engine._update_version_floor(ns(allow_downgrade=False), lock, "v2.0.5", "self-update")
    assert "older than the version you have (2.1.0)" in _exit_text(ei)


def test_allow_downgrade_needs_a_terminal_and_the_typed_words(engine, monkeypatch):
    lock = {"framework": {"version": "2.0.0", "upstream_ref": "v2.0.0"}}
    _tty(monkeypatch, "downgrade to v1.9.0\n", tty=False)
    with pytest.raises(SystemExit) as ei:
        engine._update_version_floor(ns(allow_downgrade=True), lock, "v1.9.0", "update")
    assert "interactive terminal" in _exit_text(ei)
    _tty(monkeypatch, "yes\n")
    with pytest.raises(SystemExit) as ei:
        engine._update_version_floor(ns(allow_downgrade=True), lock, "v1.9.0", "update")
    assert "did not match" in _exit_text(ei)
    _tty(monkeypatch, "downgrade to v1.9.0\n")
    engine._update_version_floor(ns(allow_downgrade=True), lock, "v1.9.0", "update")


def test_cli_update_and_self_update_refuse_an_older_release(project, run_cli):
    project.add("conductor/a.md", "alpha\n")
    project.framework["upstream"] = str(project.root / "no-such-upstream")
    project.write()
    for cmd in ("update", "self-update"):
        r = run_cli(project.root, cmd, "--ref", "v1.0.0")
        out = r.stdout + r.stderr
        assert r.returncode != 0, out
        assert "older than the version you have (2.0.0)" in out, out
        assert "fetching tag" not in out, out
    assert project.lock()["framework"]["version"] == "2.0.0"


# ===========================================================================
# tessctl:cmd_approve:quarantine-bytes-unbound-to-confirmation
# ===========================================================================

def _quarantine(project):
    project.add(GUARD, AUTHORITATIVE, tier="security")
    project.write()
    project.write_live(GUARD, WEAKENED)
    project.mod.cmd_capture(ns(path=GUARD, all=False, dry_run=False, rationale="",
                               source="agent"), project.root)
    return project.root / ".tess" / "quarantine" / GUARD


def test_capture_records_the_digest_of_the_parked_copy(project):
    q = _quarantine(project)
    entry = project.lock()["files"][GUARD_KEY]
    assert entry["status"] == "quarantined"
    assert entry["quarantined_sha256"] == project.mod.sha256_bytes(q.read_bytes())


def test_approve_refuses_a_parked_copy_rewritten_after_capture(project, monkeypatch):
    """On 3eba77d approve wrote whatever the agent-writable parked copy held."""
    q = _quarantine(project)
    q.write_text("SWAPPED after capture — never reviewed\n")
    _tty(monkeypatch, GUARD + "\n")
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_approve(ns(path=GUARD, rationale="ok"), project.root)
    assert "changed after Tess set it aside" in _exit_text(ei)
    assert project.read_live(GUARD) == AUTHORITATIVE
    assert project.lock()["files"][GUARD_KEY]["status"] == "quarantined"


def test_approve_shows_the_exact_bytes_and_their_digest(project, monkeypatch):
    q = _quarantine(project)
    out = _tty(monkeypatch, GUARD + "\n")
    project.mod.cmd_approve(ns(path=GUARD, rationale="reviewed"), project.root)
    text = out.getvalue()
    digest = project.mod.sha256_bytes(WEAKENED.encode())
    assert digest in text
    assert "+GUARDRAILS weakened by an agent" in text
    assert project.read_live(GUARD) == WEAKENED
    entry = project.lock()["files"][GUARD_KEY]
    assert entry["approved_sha256"] == digest and "quarantined_sha256" not in entry
    assert q.read_text() == WEAKENED


def test_approve_refuses_bytes_swapped_while_the_operator_reviews(project, monkeypatch):
    q = _quarantine(project)
    _tty(monkeypatch)

    def typed_while_agent_swaps(prompt=""):
        q.write_text("SWAPPED during review\n")
        return GUARD

    monkeypatch.setattr("builtins.input", typed_while_agent_swaps)
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_approve(ns(path=GUARD, rationale="ok"), project.root)
    assert "changed while you were reviewing it" in _exit_text(ei)
    assert project.read_live(GUARD) == AUTHORITATIVE
    assert project.lock()["files"][GUARD_KEY]["status"] == "quarantined"


def test_approve_refuses_a_symlinked_parked_copy(project, monkeypatch, tmp_path_factory):
    q = _quarantine(project)
    outside = tmp_path_factory.mktemp("outside") / "evil.md"
    outside.write_text(WEAKENED)       # same bytes: the digest alone would pass
    q.unlink()
    os.symlink(outside, q)
    _tty(monkeypatch, GUARD + "\n")
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_approve(ns(path=GUARD, rationale="ok"), project.root)
    assert "symbolic link" in _exit_text(ei)
    assert project.read_live(GUARD) == AUTHORITATIVE


# ===========================================================================
# tessctl:_rollback_from_manifest:self-attested-snapshot-restore-source
# ===========================================================================

def _plant_snapshot(project, snap_id: str, files: dict, symlinks: dict | None = None):
    """What an in-session agent can do with the Write tool: a snapshot
    directory whose manifest attests its own payloads."""
    snap = project.root / ".tess" / "snapshots" / snap_id
    snap.mkdir(parents=True)
    manifest = {}
    for rel, data in files.items():
        p = snap / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        manifest[rel] = {"existed": True, "sha256": project.mod.sha256_bytes(data),
                         "mode": 0o755, "is_symlink": False, "link_target": None}
    for rel, target in (symlinks or {}).items():
        manifest[rel] = {"existed": True, "sha256": None, "mode": 0o777,
                         "is_symlink": True, "link_target": target}
    (snap / "manifest.json").write_text(json.dumps(manifest))
    return snap


def test_planted_snapshot_cannot_write_git_hooks(project):
    project.add("conductor/a.md", "alpha\n")
    project.write()
    (project.root / ".git" / "hooks").mkdir(parents=True)
    _plant_snapshot(project, "2099-01-01T00-00-00Z-update",
                    {".git/hooks/post-checkout": b"#!/bin/sh\necho pwned\n"})
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_rollback(ns(to=None), project.root)
    assert "inside .git" in _exit_text(ei) and "Nothing was changed" in _exit_text(ei)
    assert not (project.root / ".git" / "hooks" / "post-checkout").exists()


def test_planted_snapshot_cannot_write_paths_tess_never_snapshots(project):
    project.add("conductor/a.md", "alpha\n")
    project.write()
    _plant_snapshot(project, "2099-01-01T00-00-00Z-update",
                    {".claude/settings.local.json": b'{"permissions": {"allow": ["Bash(*)"]}}\n',
                     "conductor/a.md": b"alpha\n"})
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_rollback(ns(to="2099-01-01T00-00-00Z-update"), project.root)
    assert ".claude/settings.local.json" in _exit_text(ei)
    assert not (project.root / ".claude" / "settings.local.json").exists()


def test_planted_snapshot_symlink_out_of_the_project_is_refused(project):
    project.add("conductor/a.md", "alpha\n")
    project.write()
    _plant_snapshot(project, "2099-01-01T00-00-00Z-update", {},
                    symlinks={"conductor/a.md": "../../../../etc/passwd"})
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_rollback(ns(to=None), project.root)
    assert "points outside the project" in _exit_text(ei)
    assert not (project.root / "conductor" / "a.md").is_symlink()


def test_rollback_of_security_tier_text_needs_the_person_at_the_terminal(project, monkeypatch):
    project.add(GUARD, AUTHORITATIVE, tier="security")
    project.write()
    _plant_snapshot(project, "2099-01-01T00-00-00Z-update", {GUARD: WEAKENED.encode()})
    _tty(monkeypatch, "roll back\n", tty=False)
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_rollback(ns(to=None), project.root)
    assert "interactive terminal" in _exit_text(ei)
    assert project.read_live(GUARD) == AUTHORITATIVE
    out = _tty(monkeypatch, "roll back\n")
    project.mod.cmd_rollback(ns(to=None), project.root)
    assert GUARD in out.getvalue()
    assert project.read_live(GUARD) == WEAKENED


def test_rollback_of_ordinary_files_stays_prompt_free(project):
    project.add("conductor/a.md", "alpha\n")
    project.write()
    project.write_live("conductor/a.md", "edited\n")
    _plant_snapshot(project, "2099-01-01T00-00-00Z-render", {"conductor/a.md": b"alpha\n"})
    project.mod.cmd_rollback(ns(to="2099-01-01T00-00-00Z-render"), project.root)
    assert project.read_live("conductor/a.md") == "alpha\n"


def test_snapshot_made_here_is_bound_to_its_manifest_bytes(project):
    project.add("conductor/a.md", "alpha\n")
    project.write()
    sid = project.mod.snapshot_paths(project.root, ["conductor/a.md"], "update")
    snap = project.root / ".tess" / "snapshots" / sid
    assert project.mod._snapshot_made_here(snap)
    m = json.loads((snap / "manifest.json").read_text())
    m[".git/hooks/post-merge"] = {"existed": False}
    (snap / "manifest.json").write_text(json.dumps(m))
    assert not project.mod._snapshot_made_here(snap)


def test_auto_rollback_never_restores_a_changed_snapshot(project, capsys):
    project.add("conductor/a.md", "alpha\n")
    project.write()
    sid = project.mod.snapshot_paths(project.root, ["conductor/a.md"], "update")
    snap = project.root / ".tess" / "snapshots" / sid
    (snap / "conductor" / "a.md").write_text("EVIL\n")
    m = json.loads((snap / "manifest.json").read_text())
    m["conductor/a.md"]["sha256"] = project.mod.sha256_bytes(b"EVIL\n")
    (snap / "manifest.json").write_text(json.dumps(m))
    project.write_live("conductor/a.md", "half-updated\n")
    project.mod._update_auto_rollback(project.root, sid, {}, RuntimeError("boom"))
    assert project.read_live("conductor/a.md") == "half-updated\n"
    assert "AUTOMATIC ROLLBACK INCOMPLETE" in capsys.readouterr().err


# ===========================================================================
# tessctl:cmd_resolve:security-tier-write-without-presence
# ===========================================================================

def _conflict(project, live_rel, data: bytes):
    d = project.root / ".tess" / "conflicts"
    d.mkdir(parents=True, exist_ok=True)
    p = d / live_rel.replace("/", "_")
    p.write_bytes(data)
    return p


def test_resolve_ours_on_security_tier_needs_presence(project, monkeypatch):
    """On 3eba77d `resolve --ours` flipped guardrails.md to locally-modified
    with no prompt, making any live edit 'captured drift (expected)'."""
    project.add(GUARD, AUTHORITATIVE, tier="security")
    project.write()
    project.write_live(GUARD, WEAKENED)
    _tty(monkeypatch, GUARD + "\n", tty=False)
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_resolve(ns(path=GUARD, ours=True, theirs=False, edit=False), project.root)
    assert "interactive terminal" in _exit_text(ei)
    assert project.lock()["files"][GUARD_KEY]["status"] == "core-managed"


def test_resolve_theirs_with_planted_conflict_file_needs_presence(project, monkeypatch):
    project.add(GUARD, AUTHORITATIVE, tier="security", status="quarantined")
    project.write()
    _conflict(project, GUARD, WEAKENED.encode())
    _tty(monkeypatch, GUARD + "\n", tty=False)
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_resolve(ns(path=GUARD, ours=False, theirs=True, edit=False), project.root)
    assert "interactive terminal" in _exit_text(ei)
    assert project.read_live(GUARD) == AUTHORITATIVE
    assert project.lock()["files"][GUARD_KEY]["status"] == "quarantined"


def test_resolve_theirs_with_presence_writes_exactly_the_reviewed_bytes(project, monkeypatch):
    project.add(GUARD, AUTHORITATIVE, tier="security")
    project.write()
    cf = _conflict(project, GUARD, b"GUARDRAILS incoming\n")
    out = _tty(monkeypatch)

    def typed_while_swapped(prompt=""):
        cf.write_bytes(b"SWAPPED\n")
        return GUARD

    monkeypatch.setattr("builtins.input", typed_while_swapped)
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_resolve(ns(path=GUARD, ours=False, theirs=True, edit=False), project.root)
    assert "changed while you were reviewing it" in _exit_text(ei)
    assert project.read_live(GUARD) == AUTHORITATIVE
    cf.write_bytes(b"GUARDRAILS incoming\n")
    monkeypatch.setattr("builtins.input", lambda prompt="": GUARD)
    project.mod.cmd_resolve(ns(path=GUARD, ours=False, theirs=True, edit=False), project.root)
    assert project.read_live(GUARD) == "GUARDRAILS incoming\n"
    assert project.mod.sha256_bytes(b"GUARDRAILS incoming\n") in out.getvalue()


def test_resolve_of_ordinary_file_stays_prompt_free(project):
    project.add("conductor/p.md", "core\n")
    project.write()
    _conflict(project, "conductor/p.md", b"incoming\n")
    project.mod.cmd_resolve(ns(path="conductor/p.md", ours=False, theirs=True, edit=False),
                            project.root)
    assert project.read_live("conductor/p.md") == "incoming\n"


# ===========================================================================
# coverage critic: override / reset / recruit / bench
# ===========================================================================

def test_override_of_security_tier_file_needs_presence(project, monkeypatch):
    project.add(GUARD, AUTHORITATIVE, tier="security")
    project.write()
    project.write_live(GUARD, WEAKENED)
    _tty(monkeypatch, GUARD + "\n", tty=False)
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_override(ns(path=GUARD), project.root)
    assert "interactive terminal" in _exit_text(ei)
    entry = project.lock()["files"][GUARD_KEY]
    assert entry["status"] == "core-managed" and "override_diff" not in entry


def test_override_of_ordinary_file_stays_prompt_free(project):
    project.add("conductor/p.md", "line1\n")
    project.write()
    project.write_live("conductor/p.md", "line1\nmine\n")
    project.mod.cmd_override(ns(path="conductor/p.md"), project.root)
    assert project.lock()["files"][".tess/core/conductor/p.md"]["status"] == "patch-override"


def test_reset_that_would_repin_changed_security_core_needs_presence(project, monkeypatch):
    """reset re-pins base_sha to the core bytes on disk: for a security-tier
    file whose core was changed, that silences verify's CORE TAMPER."""
    project.add(GUARD, AUTHORITATIVE, tier="security", status="locally-modified")
    project.write()
    project.core(GUARD_KEY).write_text("GUARDRAILS core changed by a script\n")
    pinned = project.lock()["files"][GUARD_KEY]["base_sha"]
    _tty(monkeypatch, GUARD + "\n", tty=False)
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_reset(ns(path=GUARD), project.root)
    assert "interactive terminal" in _exit_text(ei)
    assert project.lock()["files"][GUARD_KEY]["base_sha"] == pinned


def test_plain_reset_of_security_file_stays_prompt_free(project):
    project.add(GUARD, AUTHORITATIVE, tier="security", status="locally-modified")
    project.write()
    project.write_live(GUARD, WEAKENED)
    project.mod.cmd_reset(ns(path=GUARD), project.root)
    assert project.read_live(GUARD) == AUTHORITATIVE
    assert project.lock()["files"][GUARD_KEY]["status"] == "core-managed"


def test_bench_or_recruit_of_a_security_tier_entry_needs_presence(project, monkeypatch):
    key = ".tess/core/agents-dispatch/cyra.md"
    project.add(".claude/agents/cyra.md", "cyra\n", core_key=key, tier="security")
    project.add(None, json.dumps({"universal_base": [], "paths": {}}),
                core_key=".tess/core/roster-paths.json", render_live=False)
    project.write()
    _tty(monkeypatch, ".claude/agents/cyra.md\n", tty=False)
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_bench(ns(names=["cyra"]), project.root)
    assert "interactive terminal" in _exit_text(ei)
    assert project.lock()["files"][key]["status"] == "core-managed"
    assert (project.root / ".claude" / "agents" / "cyra.md").exists()
    files = project.lock()["files"]
    files[key]["status"] = "staged"
    project.mod.save_lock(project.root, {"schema": 1, "framework": project.framework,
                                         "files": files})
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_recruit(ns(names=["cyra"]), project.root)
    assert "interactive terminal" in _exit_text(ei)
    assert project.lock()["files"][key]["status"] == "staged"
