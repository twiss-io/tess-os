"""
v0.2 integrity gates (engine bugs e, 10, 12, 13, 14, a).

  * e   init/restore never overwrite uncaptured drift silently: they skip it,
        print `WOULD CLOBBER UNCAPTURED DRIFT <path>` and exit non-zero; with
        --force they overwrite (recorded in modified.json, doctor WARNs with
        the snapshot id) — except a security-tier copy file, refused always.
  * 10  every file under .tess/core has a tess.lock entry (hard-floor.md and
        roster-paths.json had none, so tampering with them passed doctor,
        verify and `lock --check`); an untracked core file FAILs all three.
  * 12  one consolidated snapshot per restore, whatever the wall clock does.
  * 13  `init --from` exits non-zero.
  * 14  an unknown name in render_targets.enabled FAILs doctor, verify and
        `lock --check`, and the message lists the known targets.
  * a   the 5c2d698 scratch repro end to end on a copy of the real tree.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT, ns


def _snaps(root):
    return Path(root) / ".tess" / "snapshots"


def _snapshot_dirs(root):
    d = _snaps(root)
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []


def _set_enabled(root, names):
    mf_path = Path(root) / "tess.manifest.json"
    manifest = json.loads(mf_path.read_text(encoding="utf-8"))
    manifest.setdefault("render_targets", {})["enabled"] = list(names)
    mf_path.write_text(json.dumps(manifest), encoding="utf-8")


# ---------------------------------------------------------------------------
# bug 13
# ---------------------------------------------------------------------------

def test_init_from_upstream_exits_nonzero(project, run_cli):
    project.add("conductor/a.md", "x\n")
    project.write()
    r = run_cli(project.root, "init", "--from", "x")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "not implemented" in (r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# bug 14
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [("doctor",), ("verify",), ("lock", "--check")])
def test_unknown_render_target_fails_integrity_commands(project, run_cli, argv):
    project.add("conductor/a.md", "x\n")
    project.write()
    _set_enabled(project.root, ["claude-code", "gemni"])
    r = run_cli(project.root, *argv)
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "unknown render target" in out
    assert "'gemni'" in out
    for known in sorted(project.mod.RENDER_TARGETS):
        assert known in out


def test_known_render_targets_pass(project):
    project.add("conductor/a.md", "x\n")
    project.write()
    assert project.mod._unknown_render_target_findings(project.root) == []
    _set_enabled(project.root, "claude-code")  # a string, not a list
    assert project.mod._unknown_render_target_findings(project.root)


# ---------------------------------------------------------------------------
# bug 10
# ---------------------------------------------------------------------------

def test_every_real_core_file_has_a_lock_entry():
    lock = yaml.safe_load((REPO_ROOT / ".tess" / "tess.lock").read_text(encoding="utf-8"))
    keys = set(lock["files"])
    core = REPO_ROOT / ".tess" / "core"
    untracked = sorted(
        p.relative_to(REPO_ROOT).as_posix()
        for p in core.rglob("*")
        if p.is_file() and p.name not in (".DS_Store", ".gitkeep")
        and "__pycache__" not in p.parts
        and p.relative_to(REPO_ROOT).as_posix() not in keys
    )
    assert untracked == []
    hf = lock["files"][".tess/core/templates/claude-md/hard-floor.md"]
    assert hf["tier"] == "security" and hf["live_path"] == "CLAUDE.md"
    assert lock["files"][".tess/core/roster-paths.json"]["live_path"] is None


@pytest.mark.parametrize("argv", [("doctor",), ("verify",), ("lock", "--check")])
def test_untracked_core_file_fails_integrity_commands(project, run_cli, argv):
    project.add("conductor/a.md", "x\n")
    project.write()
    stray = project.root / ".tess" / "core" / "templates" / "stray.md"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text("feeds nothing yet, protected by nothing\n")
    r = run_cli(project.root, *argv)
    assert r.returncode == 1, r.stdout + r.stderr
    assert ".tess/core/templates/stray.md" in r.stdout + r.stderr


# ---------------------------------------------------------------------------
# A copy of the real tree (the 5c2d698 repros ran on one)
# ---------------------------------------------------------------------------

_REAL_TREE_PARTS = (
    ".tess", ".claude", ".codex", "conductor", "agents", "core", "clients",
    "prompts", "operator", "CLAUDE.md", "AGENTS.md", "tess.manifest.json",
)


@pytest.fixture
def real_tree(tmp_path):
    root = tmp_path / "real"
    root.mkdir()
    for part in _REAL_TREE_PARTS:
        src = REPO_ROOT / part
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(
                src, root / part, symlinks=True,
                ignore=shutil.ignore_patterns("__pycache__", ".tessctl_tmp_*"),
            )
        else:
            shutil.copy2(src, root / part)
    snaps = root / ".tess" / "snapshots"
    if snaps.exists():
        shutil.rmtree(snaps)
    snaps.mkdir(parents=True)
    (snaps / ".gitkeep").write_text("")
    for stale in (".tess/modified.json", ".tess/update.lock"):
        if (root / stale).exists():
            (root / stale).unlink()
    return root


def _cli(root, *args):
    env = {**os.environ, "TESS_ROOT": str(root)}
    return subprocess.run(
        [sys.executable, str(Path(root) / ".tess" / "bin" / "tessctl"), *args],
        cwd=str(root), env=env, capture_output=True, text=True,
    )


def test_hard_floor_tamper_after_render_fails_verify(real_tree):
    """Bug 10 acceptance: 5c2d698 reported verify OK here."""
    r0 = _cli(real_tree, "verify")
    assert r0.returncode == 0, r0.stdout[-2000:] + r0.stderr
    hf = real_tree / ".tess" / "core" / "templates" / "claude-md" / "hard-floor.md"
    hf.write_text(hf.read_text(encoding="utf-8") + "\nWEAKENED BY TAMPER\n", encoding="utf-8")
    r1 = _cli(real_tree, "render")
    assert r1.returncode == 0, r1.stdout[-2000:] + r1.stderr
    assert "WEAKENED BY TAMPER" in (real_tree / "CLAUDE.md").read_text(encoding="utf-8")
    for argv in (("verify",), ("doctor",), ("lock", "--check")):
        r = _cli(real_tree, *argv)
        assert r.returncode != 0, (argv, r.stdout[-2000:])
        assert "TAMPER" in r.stdout, (argv, r.stdout[-2000:])


_MARKERS = {
    "CLAUDE.md": "\nMARKER-CLAUDE\n",
    "conductor/guardrails.md": "\nMARKER-GUARDRAILS\n",
    "conductor/doctrine.md": "\nMARKER-DOCTRINE\n",
    "AGENTS.md": "\nMARKER-AGENTS\n",
    ".codex/prompts/wake.md": "\nMARKER-WAKE-PROMPT\n",
    ".codex/config.toml": "\n[mcp_servers.demo]\ncommand = \"demo-mcp\"\n",
}


def _plant_markers(root):
    for rel, marker in _MARKERS.items():
        p = root / rel
        assert p.is_file(), rel
        p.write_text(p.read_text(encoding="utf-8") + marker, encoding="utf-8")


def _marker_present(root, rel):
    return _MARKERS[rel].strip() in (root / rel).read_text(encoding="utf-8")


def test_init_refuses_to_clobber_uncaptured_drift_then_force_and_rollback(real_tree):
    """Bugs e + a acceptance, the 5c2d698 scratch repro: 6 markers, `init`
    overwrote all 6 and doctor/verify then said OK; the -pre snapshot held 3."""
    _plant_markers(real_tree)
    pre_images = {rel: (real_tree / rel).read_bytes() for rel in _MARKERS}

    r = _cli(real_tree, "init")
    assert r.returncode != 0, r.stdout[-3000:]
    for rel in _MARKERS:
        assert _marker_present(real_tree, rel), rel
    assert "WOULD CLOBBER UNCAPTURED DRIFT" in r.stdout
    assert "conductor/guardrails.md" in r.stdout

    before = set(_snapshot_dirs(real_tree))
    r = _cli(real_tree, "init", "--force")
    assert r.returncode != 0, r.stdout[-3000:]  # guardrails.md is still refused
    assert "REFUSED" in r.stdout and "conductor/guardrails.md" in r.stdout
    assert _marker_present(real_tree, "conductor/guardrails.md")
    for rel in _MARKERS:
        if rel != "conductor/guardrails.md":
            assert not _marker_present(real_tree, rel), rel

    # ONE consolidated snapshot for the whole `init --force` (per-file `-pre`
    # directories written by the render write path are extra copies).
    new = sorted(d for d in set(_snapshot_dirs(real_tree)) - before if not d.endswith("-pre"))
    assert len(new) == 1, new
    snap = _snaps(real_tree) / new[0]
    for rel, data in pre_images.items():
        assert (snap / rel).read_bytes() == data, rel

    events = json.loads((real_tree / ".tess" / "modified.json").read_text(encoding="utf-8"))
    forced = {e["path"] for e in events if e.get("kind") == "forced-overwrite"}
    assert forced == set(_MARKERS) - {"conductor/guardrails.md"}
    assert all(e.get("pre_image") == new[0] for e in events if e.get("kind") == "forced-overwrite")

    doc = _cli(real_tree, "doctor")
    assert f"pre-image in snapshot {new[0]}" in doc.stdout

    r = _cli(real_tree, "rollback", "--to", new[0])
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    for rel, data in pre_images.items():
        assert (real_tree / rel).read_bytes() == data, rel


# ---------------------------------------------------------------------------
# bug e on the synthetic fixture
# ---------------------------------------------------------------------------

def test_restore_skips_uncaptured_drift_and_exits_nonzero(project, capsys):
    project.add("conductor/x.md", "core x\n")
    project.add("conductor/y.md", "core y\n")
    project.write()
    _set_enabled(project.root, [])  # no CLAUDE.md.tpl in this fixture: render nothing
    project.write_live("conductor/x.md", "hand edit\n")
    project.write_live("conductor/y.md", "")
    os.unlink(project.root / "conductor" / "y.md")  # missing: restored, not drift

    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_restore(ns(dry_run=False, force=False), project.root)
    assert ei.value.code not in (None, 0)
    out = capsys.readouterr().out
    assert "WOULD CLOBBER UNCAPTURED DRIFT conductor/x.md" in out
    assert project.read_live("conductor/x.md") == "hand edit\n"
    assert project.read_live("conductor/y.md") == "core y\n"


def test_init_force_overwrites_and_doctor_warns_until_acked(project, capsys):
    project.add("conductor/x.md", "core x\n")
    project.write()
    _set_enabled(project.root, [])  # no CLAUDE.md.tpl in this fixture: render nothing
    project.write_live("conductor/x.md", "hand edit\n")

    project.mod.cmd_init(ns(from_upstream=None, force=True), project.root)
    assert project.read_live("conductor/x.md") == "core x\n"
    events = project.mod.load_modified(project.root)
    evt = [e for e in events if e.get("kind") == "forced-overwrite"]
    assert [e["path"] for e in evt] == ["conductor/x.md"]
    snap_id = evt[0]["pre_image"]
    assert (_snaps(project.root) / snap_id / "conductor" / "x.md").read_text() == "hand edit\n"
    capsys.readouterr()

    project.mod.cmd_doctor(ns(json_out=False, fix=False, path=None), project.root)
    out = capsys.readouterr().out
    assert "WARN" in out and "conductor/x.md" in out and snap_id in out
    assert "doctor: OK" in out  # a WARN, not a failure

    project.mod.cmd_doctor(ns(json_out=False, fix=False, path=None, ack_overwrites=True), project.root)
    capsys.readouterr()
    project.mod.cmd_doctor(ns(json_out=False, fix=False, path=None), project.root)
    assert snap_id not in capsys.readouterr().out


def test_security_tier_drift_refused_with_and_without_force(project, capsys):
    project.add("conductor/guardrails.md", "GUARDRAILS\n", tier="security")
    project.write()
    _set_enabled(project.root, [])  # no CLAUDE.md.tpl in this fixture: render nothing
    project.write_live("conductor/guardrails.md", "GUARDRAILS weakened\n")
    for force in (False, True):
        with pytest.raises(SystemExit) as ei:
            project.mod.cmd_init(ns(from_upstream=None, force=force), project.root)
        assert ei.value.code not in (None, 0)
        assert project.read_live("conductor/guardrails.md") == "GUARDRAILS weakened\n"
    out = capsys.readouterr().out
    assert "REFUSED" in out


def test_restore_dry_run_reports_drift_without_writing(project, capsys):
    project.add("conductor/x.md", "core x\n")
    project.write()
    _set_enabled(project.root, [])  # no CLAUDE.md.tpl in this fixture: render nothing
    project.write_live("conductor/x.md", "hand edit\n")
    project.mod.cmd_restore(ns(dry_run=True, force=False), project.root)
    out = capsys.readouterr().out
    assert "WOULD CLOBBER UNCAPTURED DRIFT conductor/x.md" in out
    assert project.read_live("conductor/x.md") == "hand edit\n"
    assert _snapshot_dirs(project.root) == []


def test_clean_restore_leaves_no_snapshot(project):
    project.add("conductor/x.md", "core x\n")
    project.write()
    _set_enabled(project.root, [])  # no CLAUDE.md.tpl in this fixture: render nothing
    project.mod.cmd_restore(ns(dry_run=False, force=False), project.root)
    assert _snapshot_dirs(project.root) == []


# ---------------------------------------------------------------------------
# bug 12
# ---------------------------------------------------------------------------

class _TickingDatetime(_dt.datetime):
    """datetime whose now() advances one second per call."""
    _tick = 0

    @classmethod
    def now(cls, tz=None):
        cls._tick += 1
        return _dt.datetime(2026, 9, 24, 3, 0, 0, tzinfo=tz) + _dt.timedelta(seconds=cls._tick)


def test_long_restore_keeps_every_pre_image_in_one_snapshot(project, monkeypatch):
    """Bug 12: 25 drifted files, a new wall-clock second per call. 5c2d698
    wrote 25 `<ts>-pre` directories and pruned them to 20, so the earliest
    pre-images were gone and no single snapshot could undo the restore."""
    n = 25
    for i in range(n):
        project.add(f"conductor/f{i:02d}.md", f"core {i}\n")
    project.write()
    _set_enabled(project.root, [])  # no CLAUDE.md.tpl in this fixture: render nothing
    for i in range(n):
        project.write_live(f"conductor/f{i:02d}.md", f"edit {i}\n")

    fake = type("FakeDatetimeModule", (), {
        "datetime": _TickingDatetime, "timezone": _dt.timezone, "timedelta": _dt.timedelta,
    })
    monkeypatch.setattr(project.mod, "datetime", fake)
    project.mod.cmd_restore(ns(dry_run=False, force=True), project.root)
    monkeypatch.undo()

    holders = []
    for name in _snapshot_dirs(project.root):
        d = _snaps(project.root) / name
        if all((d / f"conductor/f{i:02d}.md").is_file() for i in range(n)):
            holders.append(name)
    assert len(holders) == 1, _snapshot_dirs(project.root)
    for i in range(n):
        assert project.read_live(f"conductor/f{i:02d}.md") == f"core {i}\n"

    project.mod.cmd_rollback(ns(to=holders[0]), project.root)
    for i in range(n):
        assert project.read_live(f"conductor/f{i:02d}.md") == f"edit {i}\n"


# ---------------------------------------------------------------------------
# bug 11: staged in the lock but present on disk
# ---------------------------------------------------------------------------

def _staged_but_present(project):
    project.add(".claude/agents/vega.md", "---\nname: vega\n---\nvega\n",
                core_key=".tess/core/agents-dispatch/vega.md", status="staged")
    project.add(".claude/agents/ada.md", "---\nname: ada\n---\nada\n",
                core_key=".tess/core/agents-dispatch/ada.md", status="staged",
                render_live=False)
    project.add(".claude/agents/lyra.md", "---\nname: lyra\n---\nlyra\n",
                core_key=".tess/core/agents-dispatch/lyra.md")
    project.write()
    _set_enabled(project.root, [])
    assert (project.root / ".claude" / "agents" / "vega.md").is_file()
    assert not (project.root / ".claude" / "agents" / "ada.md").exists()


def test_roster_list_reports_present_but_unmanaged(project, capsys):
    """5c2d698 counted vega as benched although its file exists."""
    _staged_but_present(project)
    project.mod.cmd_roster(ns(roster_sub="list"), project.root)
    out = capsys.readouterr().out
    assert "present-but-unmanaged (1)" in out
    unmanaged_block = out.split("present-but-unmanaged", 1)[1]
    assert "vega" in unmanaged_block
    assert "staged / benched (1)" in out  # ada only


def test_doctor_warns_on_present_but_unmanaged(project, capsys):
    _staged_but_present(project)
    project.mod.cmd_doctor(ns(json_out=False, fix=False, path=None), project.root)
    out = capsys.readouterr().out
    assert "doctor: OK" in out  # a WARN, never a failure
    warn = [l for l in out.splitlines() if "present-but-unmanaged" in l]
    assert warn and ".claude/agents/vega.md" in warn[0]
    assert not any(".claude/agents/ada.md" in l for l in warn)


# ---------------------------------------------------------------------------
# Cyra fix round 1: the drift gate knows stale renders and captured overrides
# ---------------------------------------------------------------------------

def test_restore_applies_a_new_local_md_append_without_force(project, capsys):
    """Adding `<file>.local.md` (the operator's append-first customization
    tier) leaves the live file equal to pristine core: a stale render, not a
    hand edit. restore applies the append and exits 0 (e5ba76a refused it as
    WOULD CLOBBER UNCAPTURED DRIFT and exited 1; 5c2d698 applied it)."""
    project.add("conductor/doctrine.md", "CORE DOCTRINE\n")
    project.write()
    _set_enabled(project.root, [])
    (project.root / "conductor" / "doctrine.local.md").write_text("OPERATOR APPEND\n")

    code = 0
    try:
        project.mod.cmd_restore(ns(dry_run=False, force=False), project.root)
    except SystemExit as e:  # the behaviour under test is the exit status
        code = e.code
    out = capsys.readouterr().out
    assert code in (None, 0), f"restore exited {code!r}\n{out}"
    assert "WOULD CLOBBER" not in out
    assert project.read_live("conductor/doctrine.md") == "CORE DOCTRINE\n\nOPERATOR APPEND\n"


def test_restore_still_blocks_a_real_hand_edit_next_to_a_local_md(project, capsys):
    """The stale-render rule is exact: a hand edit is still uncaptured drift,
    and the remedy names the per-path discard (`tessctl reset <path>`)."""
    project.add("conductor/doctrine.md", "CORE DOCTRINE\n")
    project.write()
    _set_enabled(project.root, [])
    (project.root / "conductor" / "doctrine.local.md").write_text("OPERATOR APPEND\n")
    project.write_live("conductor/doctrine.md", "CORE DOCTRINE\nHAND EDIT\n")

    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_restore(ns(dry_run=False, force=False), project.root)
    assert ei.value.code not in (None, 0)
    assert "tessctl reset <path>" in str(ei.value.code)
    assert "WOULD CLOBBER UNCAPTURED DRIFT conductor/doctrine.md" in capsys.readouterr().out
    assert project.read_live("conductor/doctrine.md") == "CORE DOCTRINE\nHAND EDIT\n"


def test_restore_keeps_a_patch_override_without_calling_it_drift(project, run_cli):
    """A recorded patch-override is a captured customization: restore keeps it,
    exits 0, and never labels it uncaptured drift or suggests --force
    (5c2d698 silently reverted it to core; e5ba76a exited 1 with
    'WOULD CLOBBER UNCAPTURED DRIFT' and --force as the only remedy)."""
    project.add("conductor/p.md", "line1\nline2\n")
    project.write()
    _set_enabled(project.root, [])
    project.write_live("conductor/p.md", "line1\nline2 OVERRIDDEN\n")
    r = run_cli(project.root, "override", "conductor/p.md")
    assert r.returncode == 0, r.stdout + r.stderr
    assert project.lock()["files"][".tess/core/conductor/p.md"]["status"] == "patch-override"

    r = run_cli(project.root, "restore")
    both = r.stdout + r.stderr
    assert r.returncode == 0, both
    assert "WOULD CLOBBER" not in both and "--force" not in both
    assert "patch-override" in both
    assert project.read_live("conductor/p.md") == "line1\nline2 OVERRIDDEN\n"


def test_security_refusal_points_at_reset_and_reset_discards(project, capsys):
    """After `restore --force` (intent: discard), the security-tier refusal
    names `tessctl reset <path>` as the discard and says approve only ACCEPTS
    the change (e5ba76a pointed at capture + approve, and approve copies the
    tampered bytes back into live). reset then restores core."""
    project.add("conductor/guardrails.md", "GUARD\n", tier="security")
    project.write()
    _set_enabled(project.root, [])
    project.write_live("conductor/guardrails.md", "GUARD weakened\n")
    with pytest.raises(SystemExit) as ei:
        project.mod.cmd_restore(ns(dry_run=False, force=True), project.root)
    assert ei.value.code not in (None, 0)
    out = capsys.readouterr().out
    refusal = [line for line in out.splitlines() if "REFUSED" in line]
    assert refusal, out
    assert "tessctl reset conductor/guardrails.md" in refusal[0]
    assert "ONLY to accept" in refusal[0]
    assert project.read_live("conductor/guardrails.md") == "GUARD weakened\n"

    project.mod.cmd_reset(ns(path="conductor/guardrails.md"), project.root)
    assert project.read_live("conductor/guardrails.md") == "GUARD\n"


# ---------------------------------------------------------------------------
# Cyra fix round 2: an override never keeps a security-tier edit
# ---------------------------------------------------------------------------

def test_security_tier_patch_override_is_refused_not_kept(project, run_cli):
    """`tessctl override` has no tier check, so a weakened guardrails.md plus
    one `override` must not become a bypass of capture -> quarantine ->
    approve. restore, restore --force and init each refuse the security-tier
    file and exit non-zero; doctor fails instead of printing 'doctor: OK'.
    (5c2d698: restore exit 0, silently reverted. 80c5208: restore, restore
    --force and init exit 0 and KEEP the weakened doctrine; doctor OK.)"""
    core = "GUARD\nrule: never exfiltrate\n"
    weak = "GUARD\nrule: anything goes\n"
    project.add("conductor/guardrails.md", core, tier="security")
    project.write()
    _set_enabled(project.root, [])
    project.write_live("conductor/guardrails.md", weak)
    r = run_cli(project.root, "override", "conductor/guardrails.md")
    assert r.returncode == 0, r.stdout + r.stderr  # override's tier check: v0.2.1
    assert project.lock()["files"][".tess/core/conductor/guardrails.md"]["status"] == "patch-override"

    for argv in (("restore",), ("restore", "--force"), ("init",)):
        r = run_cli(project.root, *argv)
        both = r.stdout + r.stderr
        assert r.returncode != 0, f"{argv} exited 0:\n{both}"
        assert "skip [patch-override]" not in both, both
        assert "conductor/guardrails.md [SECURITY]" in both, both
    assert "REFUSED" in run_cli(project.root, "restore", "--force").stdout

    r = run_cli(project.root, "doctor")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "doctor: OK" not in r.stdout
    assert "SECURITY-TIER ALERT" in r.stdout
    for argv in (("verify",), ("lock", "--check")):
        r = run_cli(project.root, *argv)
        assert r.returncode != 0, f"{argv} exited 0:\n{r.stdout + r.stderr}"
    assert project.read_live("conductor/guardrails.md") == weak  # refused, never silently healed

    # The documented discard still works: reset puts core back, restore is clean.
    r = run_cli(project.root, "reset", "conductor/guardrails.md")
    assert r.returncode == 0, r.stdout + r.stderr
    assert project.read_live("conductor/guardrails.md") == core
    r = run_cli(project.root, "restore")
    assert r.returncode == 0, r.stdout + r.stderr


def test_non_security_patch_override_is_still_kept(project, run_cli):
    """The round-2 fix is scoped to the security tier: an ordinary override
    is still a captured customization that restore keeps with exit 0."""
    project.add("conductor/p.md", "line1\n")
    project.write()
    _set_enabled(project.root, [])
    project.write_live("conductor/p.md", "line1 OVERRIDDEN\n")
    assert run_cli(project.root, "override", "conductor/p.md").returncode == 0
    for argv in (("restore",), ("restore", "--force"), ("init",)):
        r = run_cli(project.root, *argv)
        assert r.returncode == 0, f"{argv}:\n{r.stdout + r.stderr}"
    assert project.read_live("conductor/p.md") == "line1 OVERRIDDEN\n"
