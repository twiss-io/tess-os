"""
M2 — curated-squad mechanism: staged status + roster/recruit/bench verbs.

Covers the Phase-0 onboarding engine changes:

  * `roster apply <path>` installs exactly squad + universal-base (+ path
    orchestrators) and benches everything else (status → staged + live removed).
  * staged agents are ABSENT from the live tree and doctor + verify treat that
    as the correct state (not a missing-file error / drift).
  * `recruit` promotes a staged agent back to live (staged → core-managed),
    by exact name, orchestrator shorthand, and path-group expansion.
  * `bench` demotes an installed agent (core-managed → staged + live removed),
    idempotent on an already-staged agent.
  * `roster list` reports installed vs staged counts.
  * staged files survive `restore` and the `update` per-file resolution without
    being materialised to live.
  * error paths: unknown path, missing roster-paths.json, no subcommand,
    unknown recruit name.

These build on the synthetic `project` fixture in conftest.py. Agents live on
the dispatchable layer: core_key `.tess/core/agents-dispatch/<name>.md`,
live_path `.claude/agents/<name>.md` (covered by manifest owned_globs).
"""

from __future__ import annotations

import json

import pytest

from conftest import ns

# ---------------------------------------------------------------------------
# Self-contained squad config (mirrors .tess/core/roster-paths.json shape).
# Kept independent of the production file so these tests stay stable if the
# real roster membership changes.
# ---------------------------------------------------------------------------

UNIVERSAL_BASE = ["leah", "eva"]

BUILDERS_SQUAD = ["elena", "ada", "iris", "quinn", "reid"]
BUILDERS_ORCH = ["product-delivery-orchestrator"]

FOUNDERS_SQUAD = ["athena", "apolline", "zelie"]
FOUNDERS_ORCH = ["founders-office-orchestrator", "revenue-orchestrator"]

OPERATORS_SQUAD = ["adrienne", "evangeline", "clio"]
OPERATORS_ORCH = ["operational-reliability-orchestrator", "client-experience-orchestrator"]

# Agents in no path at all — must end up benched on any apply.
NOISE = ["vega", "cyra", "freya"]

ALL_AGENTS = (
    UNIVERSAL_BASE
    + BUILDERS_SQUAD + BUILDERS_ORCH
    + FOUNDERS_SQUAD + FOUNDERS_ORCH
    + OPERATORS_SQUAD + OPERATORS_ORCH
    + NOISE
)

BUILDERS_INSTALL_SET = set(UNIVERSAL_BASE + BUILDERS_SQUAD + BUILDERS_ORCH)   # 8
FOUNDERS_INSTALL_SET = set(UNIVERSAL_BASE + FOUNDERS_SQUAD + FOUNDERS_ORCH)   # 7

ROSTER = {
    "_doc": "test squad config",
    "universal_base": UNIVERSAL_BASE,
    "paths": {
        "founders": {"squad": FOUNDERS_SQUAD, "orchestrators": FOUNDERS_ORCH},
        "builders": {"squad": BUILDERS_SQUAD, "orchestrators": BUILDERS_ORCH},
        "operators": {"squad": OPERATORS_SQUAD, "orchestrators": OPERATORS_ORCH},
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _core_key(name: str) -> str:
    return f".tess/core/agents-dispatch/{name}.md"


def _live(name: str) -> str:
    return f".claude/agents/{name}.md"


def _write_roster_config(project, roster=ROSTER) -> None:
    rp = project.root / ".tess" / "core" / "roster-paths.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(roster, indent=2), encoding="utf-8")


def _build_squad_project(project, *, with_config=True):
    """All agents start fully installed (core-managed + rendered live); the
    roster config is planted in .tess/core/.  Returns the project."""
    for name in ALL_AGENTS:
        project.add(
            _live(name),
            f"# {name}\n\nDispatch brief for {name}.\n",
            core_key=_core_key(name),
            status="core-managed",
        )
    if with_config:
        _write_roster_config(project)
    project.write()
    return project


def _statuses(project) -> dict:
    lock = project.lock()
    return {
        name: lock["files"][_core_key(name)]["status"]
        for name in ALL_AGENTS
    }


# ---------------------------------------------------------------------------
# (1) roster apply — install set live, everything else staged + absent
# ---------------------------------------------------------------------------

def test_roster_apply_builders_installs_only_squad_and_base(project):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)

    st = _statuses(p)
    for name in BUILDERS_INSTALL_SET:
        assert st[name] == "core-managed", f"{name} should be installed"
        assert p.live(_live(name)).exists(), f"{name} live file should exist"
    for name in set(ALL_AGENTS) - BUILDERS_INSTALL_SET:
        assert st[name] == "staged", f"{name} should be staged"
        assert not p.live(_live(name)).exists(), f"{name} should be absent from live"


def test_roster_apply_builders_doctor_and_verify_green(project, capsys):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
    capsys.readouterr()

    # doctor: staged-absent is the correct state — no missing/drift error.
    p.mod.cmd_doctor(ns(json_out=False, fix=False, path=None), p.root)
    out = capsys.readouterr().out
    assert "doctor: OK" in out
    assert "staged (benched): 13" in out
    assert "uncaptured drift: 0" in out

    # verify: staged excluded from live-drift Check D; core untouched.
    p.mod.cmd_verify(ns(), p.root)
    out = capsys.readouterr().out
    assert "verify: OK" in out


def test_roster_apply_is_idempotent(project, capsys):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
    first = _statuses(p)
    capsys.readouterr()

    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
    second = _statuses(p)
    assert first == second

    capsys.readouterr()
    p.mod.cmd_doctor(ns(json_out=False, fix=False, path=None), p.root)
    assert "doctor: OK" in capsys.readouterr().out


def test_roster_apply_switches_paths(project):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="founders"), p.root)

    st = _statuses(p)
    for name in FOUNDERS_INSTALL_SET:
        assert st[name] == "core-managed", name
        assert p.live(_live(name)).exists(), name
    # Builders-only members (not shared with founders) are now benched.
    for name in set(BUILDERS_SQUAD + BUILDERS_ORCH) - FOUNDERS_INSTALL_SET:
        assert st[name] == "staged", name
        assert not p.live(_live(name)).exists(), name


# ---------------------------------------------------------------------------
# (2) recruit a staged agent → live + core-managed + doctor green
# ---------------------------------------------------------------------------

def test_recruit_staged_agent_installs_it(project, capsys):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
    assert _statuses(p)["athena"] == "staged"
    assert not p.live(_live("athena")).exists()

    capsys.readouterr()
    p.mod.cmd_recruit(ns(names=["athena"]), p.root)

    assert _statuses(p)["athena"] == "core-managed"
    assert p.live(_live("athena")).exists()

    capsys.readouterr()
    p.mod.cmd_doctor(ns(json_out=False, fix=False, path=None), p.root)
    assert "doctor: OK" in capsys.readouterr().out


def test_recruit_already_installed_is_noop(project, capsys):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
    capsys.readouterr()
    # ada is part of the builders squad → already installed.
    p.mod.cmd_recruit(ns(names=["ada"]), p.root)
    out = capsys.readouterr().out
    assert "already installed" in out
    assert _statuses(p)["ada"] == "core-managed"


# ---------------------------------------------------------------------------
# (3) recruit a path group / orchestrator shorthand → all members appear
# ---------------------------------------------------------------------------

def test_recruit_path_group_installs_all_members(project):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
    p.mod.cmd_recruit(ns(names=["founders"]), p.root)

    st = _statuses(p)
    for name in FOUNDERS_SQUAD + FOUNDERS_ORCH:
        assert st[name] == "core-managed", name
        assert p.live(_live(name)).exists(), name
    # Group expansion must not over-install unrelated (noise) agents.
    for name in NOISE:
        assert st[name] == "staged", name
        assert not p.live(_live(name)).exists(), name


def test_recruit_orchestrator_shorthand(project):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
    assert _statuses(p)["revenue-orchestrator"] == "staged"

    # "revenue" → "revenue-orchestrator"
    p.mod.cmd_recruit(ns(names=["revenue"]), p.root)
    assert _statuses(p)["revenue-orchestrator"] == "core-managed"
    assert p.live(_live("revenue-orchestrator")).exists()


def test_recruit_unknown_name_exits(project):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
    with pytest.raises(SystemExit):
        p.mod.cmd_recruit(ns(names=["nonexistent-agent"]), p.root)


# ---------------------------------------------------------------------------
# (4) bench an installed agent → removed from live + staged + doctor green
# ---------------------------------------------------------------------------

def test_bench_installed_agent_removes_it(project, capsys):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
    assert _statuses(p)["ada"] == "core-managed"
    assert p.live(_live("ada")).exists()

    capsys.readouterr()
    p.mod.cmd_bench(ns(names=["ada"]), p.root)

    assert _statuses(p)["ada"] == "staged"
    assert not p.live(_live("ada")).exists()

    capsys.readouterr()
    p.mod.cmd_doctor(ns(json_out=False, fix=False, path=None), p.root)
    assert "doctor: OK" in capsys.readouterr().out
    p.mod.cmd_verify(ns(), p.root)
    assert "verify: OK" in capsys.readouterr().out


def test_bench_already_staged_is_noop(project, capsys):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
    # athena is benched by the builders apply.
    capsys.readouterr()
    p.mod.cmd_bench(ns(names=["athena"]), p.root)
    out = capsys.readouterr().out
    assert "already staged" in out
    assert _statuses(p)["athena"] == "staged"


def test_bench_orchestrator_shorthand(project):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
    assert _statuses(p)["product-delivery-orchestrator"] == "core-managed"

    # "product-delivery" → "product-delivery-orchestrator"
    p.mod.cmd_bench(ns(names=["product-delivery"]), p.root)
    assert _statuses(p)["product-delivery-orchestrator"] == "staged"
    assert not p.live(_live("product-delivery-orchestrator")).exists()


# ---------------------------------------------------------------------------
# (5) roster list — counts correct
# ---------------------------------------------------------------------------

def test_roster_list_counts(project, capsys):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
    capsys.readouterr()

    p.mod.cmd_roster(ns(roster_sub="list"), p.root)
    out = capsys.readouterr().out
    assert "installed (8)" in out
    assert "staged / benched (13)" in out


# ---------------------------------------------------------------------------
# (6) staged survives restore + update resolution (not materialised)
# ---------------------------------------------------------------------------

def test_staged_survives_restore(project):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)

    counts = p.mod._do_restore(p.root, verbose=False)
    # All 13 benched agents are skipped by status, not restored.
    assert counts["skipped_status"] == 13

    st = _statuses(p)
    for name in set(ALL_AGENTS) - BUILDERS_INSTALL_SET:
        assert st[name] == "staged", name
        assert not p.live(_live(name)).exists(), f"{name} materialised by restore"
    for name in BUILDERS_INSTALL_SET:
        assert p.live(_live(name)).exists(), name


def test_staged_not_materialised_by_update_resolution(project, capsys):
    p = _build_squad_project(project)
    p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
    lock = p.lock()
    capsys.readouterr()

    # No staging content → upstream "unchanged". Staged entries → skip.
    p.mod._apply_per_file_resolution(p.root, lock, dry_run=False)
    out = capsys.readouterr().out
    assert "staged → benched; not in live tree" in out

    for name in set(ALL_AGENTS) - BUILDERS_INSTALL_SET:
        assert not p.live(_live(name)).exists(), f"{name} materialised by update apply"
    for name in BUILDERS_INSTALL_SET:
        assert p.live(_live(name)).exists(), name


# ---------------------------------------------------------------------------
# Error / edge paths
# ---------------------------------------------------------------------------

def test_roster_apply_unknown_path_exits(project):
    p = _build_squad_project(project)
    with pytest.raises(SystemExit):
        p.mod.cmd_roster(ns(roster_sub="apply", path_name="bogus"), p.root)


def test_roster_no_subcommand_exits(project):
    p = _build_squad_project(project)
    with pytest.raises(SystemExit):
        p.mod.cmd_roster(ns(roster_sub=None), p.root)


def test_roster_apply_missing_config_exits(project):
    p = _build_squad_project(project, with_config=False)
    with pytest.raises(SystemExit):
        p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)


# ---------------------------------------------------------------------------
# End-to-end CLI (argparse + dispatch + exit codes)
# ---------------------------------------------------------------------------

def test_cli_roster_apply_then_doctor_verify_exit_codes(project, run_cli):
    _build_squad_project(project)

    r = run_cli(project.root, "roster", "apply", "builders")
    assert r.returncode == 0, r.stderr
    assert "installed: 8" in r.stdout
    assert "staged: 13" in r.stdout

    d = run_cli(project.root, "doctor")
    assert d.returncode == 0, (d.stdout, d.stderr)
    assert "doctor: OK" in d.stdout
    assert "staged (benched): 13" in d.stdout

    v = run_cli(project.root, "verify")
    assert v.returncode == 0, (v.stdout, v.stderr)
    assert "verify: OK" in v.stdout
