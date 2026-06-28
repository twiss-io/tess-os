"""
M2 polish tests — bench/recruit shared resolver + roster-apply status-after-write +
staged-missing WARN in doctor/verify + real-config integrity guard.

(a) Guard test — loads the REAL .tess/core/roster-paths.json + the REAL .tess/tess.lock
    and asserts every referenced name (universal_base + each path's squad + orchestrators)
    resolves to an agents-dispatch/ lock entry.

(b) bench <path-group> — benches squad + orchestrators but NOT the universal base
    (leah/eva must never be benched by a group expansion).

Additional coverage wired to the three fixes in this pass:
  - Fix 1: bench path-group expansion (b) + bench raises on unknown name
  - Fix 2: _roster_apply sets status ONLY after guarded_write succeeds; missing core
           file does not leave a false core-managed status or inflate installed count
  - Fix 3: staged entry with missing core → STAGED-WARN in doctor (non-failing);
           staged entry with missing core → STAGED-WARN in verify (non-failing);
           staged entry with no live_path in lock → STAGED-WARN in doctor/verify
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from conftest import REPO_ROOT, ns, _load_engine

# ---------------------------------------------------------------------------
# Squad constants (mirrors test_curated_squad.py — kept local so these tests
# are self-contained and robust to membership changes in the production config).
# ---------------------------------------------------------------------------

UNIVERSAL_BASE = ["leah", "eva"]

FOUNDERS_SQUAD = ["athena", "apolline", "zelie"]
FOUNDERS_ORCH = ["founders-office-orchestrator", "revenue-orchestrator"]
FOUNDERS_INSTALL_SET = set(UNIVERSAL_BASE + FOUNDERS_SQUAD + FOUNDERS_ORCH)

BUILDERS_SQUAD = ["elena", "ada", "iris", "quinn", "reid"]
BUILDERS_ORCH = ["product-delivery-orchestrator"]

OPERATORS_SQUAD = ["adrienne", "evangeline", "clio"]
OPERATORS_ORCH = ["operational-reliability-orchestrator", "client-experience-orchestrator"]

NOISE = ["vega", "cyra", "freya"]

ALL_AGENTS = (
    UNIVERSAL_BASE
    + BUILDERS_SQUAD + BUILDERS_ORCH
    + FOUNDERS_SQUAD + FOUNDERS_ORCH
    + OPERATORS_SQUAD + OPERATORS_ORCH
    + NOISE
)

ROSTER = {
    "_doc": "test squad config",
    "universal_base": UNIVERSAL_BASE,
    "paths": {
        "founders": {"squad": FOUNDERS_SQUAD, "orchestrators": FOUNDERS_ORCH},
        "builders": {"squad": BUILDERS_SQUAD, "orchestrators": BUILDERS_ORCH},
        "operators": {"squad": OPERATORS_SQUAD, "orchestrators": OPERATORS_ORCH},
    },
}


def _core_key(name: str) -> str:
    return f".tess/core/agents-dispatch/{name}.md"


def _live(name: str) -> str:
    return f".claude/agents/{name}.md"


def _write_roster_config(project, roster=ROSTER) -> None:
    rp = project.root / ".tess" / "core" / "roster-paths.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(roster, indent=2), encoding="utf-8")


def _build_squad_project(project):
    for name in ALL_AGENTS:
        project.add(
            _live(name),
            f"# {name}\n\nDispatch brief for {name}.\n",
            core_key=_core_key(name),
            status="core-managed",
        )
    _write_roster_config(project)
    project.write()
    return project


def _statuses(project) -> dict:
    lock = project.lock()
    return {
        name: lock["files"][_core_key(name)]["status"]
        for name in ALL_AGENTS
    }


# ===========================================================================
# (a) REAL-CONFIG GUARD — every name in roster-paths.json resolves to a lock entry
# ===========================================================================

class TestRosterConfigGuard:
    """
    Integrity check: load the REAL roster-paths.json and the REAL tess.lock from
    the repo root and assert every agent name referenced in the config has a
    corresponding agents-dispatch/ entry in the lock.

    This acts as a typo guard: if a name is added to roster-paths.json but the
    matching .tess/core/agents-dispatch/<name>.md file (and lock entry) is not
    created, this test catches it immediately.
    """

    @pytest.fixture(scope="class")
    def real_data(self):
        mod = _load_engine()
        roster_path = REPO_ROOT / ".tess" / "core" / "roster-paths.json"
        assert roster_path.exists(), f"roster-paths.json not found at {roster_path}"
        roster_data = json.loads(roster_path.read_text(encoding="utf-8"))
        lock = mod.load_lock(REPO_ROOT)
        by_name = mod._agent_keys_by_name(lock)
        return {"roster": roster_data, "by_name": by_name, "lock": lock}

    def test_universal_base_in_lock(self, real_data):
        """Every universal_base agent must have an agents-dispatch/ lock entry."""
        roster = real_data["roster"]
        by_name = real_data["by_name"]
        for name in roster.get("universal_base", []):
            assert name in by_name, (
                f"universal_base agent {name!r} not found in agents-dispatch/ lock entries. "
                f"Add .tess/core/agents-dispatch/{name}.md and a matching lock entry."
            )

    def test_all_path_squad_members_in_lock(self, real_data):
        """Every squad member in every path must have an agents-dispatch/ lock entry."""
        roster = real_data["roster"]
        by_name = real_data["by_name"]
        for path_name, path_cfg in roster.get("paths", {}).items():
            for name in path_cfg.get("squad", []):
                assert name in by_name, (
                    f"path={path_name!r} squad member {name!r} not found in "
                    f"agents-dispatch/ lock entries."
                )

    def test_all_path_orchestrators_in_lock(self, real_data):
        """Every orchestrator in every path must have an agents-dispatch/ lock entry."""
        roster = real_data["roster"]
        by_name = real_data["by_name"]
        for path_name, path_cfg in roster.get("paths", {}).items():
            for name in path_cfg.get("orchestrators", []):
                assert name in by_name, (
                    f"path={path_name!r} orchestrator {name!r} not found in "
                    f"agents-dispatch/ lock entries."
                )

    def test_no_duplicate_names_across_paths(self, real_data):
        """Names should be unique within universal_base and each path (catches copy-paste typos)."""
        roster = real_data["roster"]
        # universal_base has no duplicates
        ub = roster.get("universal_base", [])
        assert len(ub) == len(set(ub)), f"universal_base has duplicates: {ub}"
        for path_name, path_cfg in roster.get("paths", {}).items():
            squad = path_cfg.get("squad", [])
            orch = path_cfg.get("orchestrators", [])
            assert len(squad) == len(set(squad)), f"path={path_name} squad has duplicates"
            assert len(orch) == len(set(orch)), f"path={path_name} orchestrators has duplicates"


# ===========================================================================
# (b) bench <path-group> benches squad+orchestrators, NOT universal base
# ===========================================================================

class TestBenchPathGroup:

    def test_bench_founders_group_benches_squad_and_orch_not_base(self, project, capsys):
        """
        `bench founders` must bench FOUNDERS_SQUAD + FOUNDERS_ORCH but leave
        leah and eva (universal_base) installed — they can never be benched via
        a group expansion.
        """
        p = _build_squad_project(project)
        # Install the founders path so squad+orch are core-managed
        p.mod.cmd_roster(ns(roster_sub="apply", path_name="founders"), p.root)
        st = _statuses(p)
        for name in FOUNDERS_SQUAD + FOUNDERS_ORCH + UNIVERSAL_BASE:
            assert st[name] == "core-managed", f"{name} should be installed before bench"

        capsys.readouterr()
        # bench the entire founders group via path-group expansion
        p.mod.cmd_bench(ns(names=["founders"]), p.root)

        st = _statuses(p)

        # Squad + orchestrators: must be staged + absent from live
        for name in FOUNDERS_SQUAD + FOUNDERS_ORCH:
            assert st[name] == "staged", f"{name} should be staged after bench founders"
            assert not p.live(_live(name)).exists(), (
                f"{name} live file should be removed after bench"
            )

        # Universal base: must remain installed — group expansion explicitly excludes them
        for name in UNIVERSAL_BASE:
            assert st[name] == "core-managed", (
                f"{name} (universal base) must NOT be benched by a path-group bench"
            )
            assert p.live(_live(name)).exists(), (
                f"{name} (universal base) live file must remain present"
            )

    def test_bench_path_group_doctor_still_green(self, project, capsys):
        """After bench path-group, doctor + verify remain clean."""
        p = _build_squad_project(project)
        p.mod.cmd_roster(ns(roster_sub="apply", path_name="founders"), p.root)
        p.mod.cmd_bench(ns(names=["founders"]), p.root)
        capsys.readouterr()

        p.mod.cmd_doctor(ns(json_out=False, fix=False, path=None), p.root)
        out = capsys.readouterr().out
        assert "doctor: OK" in out
        assert "uncaptured drift: 0" in out

        p.mod.cmd_verify(ns(), p.root)
        out = capsys.readouterr().out
        assert "verify: OK" in out

    def test_bench_path_group_unknown_exit(self, project):
        """bench with an unknown name that is not a path group raises SystemExit."""
        p = _build_squad_project(project)
        with pytest.raises(SystemExit):
            p.mod.cmd_bench(ns(names=["totally-made-up-name"]), p.root)

    def test_bench_path_group_orchestrator_shorthand_still_works(self, project):
        """bench product-delivery → product-delivery-orchestrator (shorthand still intact)."""
        p = _build_squad_project(project)
        p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
        assert _statuses(p)["product-delivery-orchestrator"] == "core-managed"

        p.mod.cmd_bench(ns(names=["product-delivery"]), p.root)
        assert _statuses(p)["product-delivery-orchestrator"] == "staged"
        assert not p.live(_live("product-delivery-orchestrator")).exists()


# ===========================================================================
# Fix 2 — _roster_apply: status set ONLY after guarded_write succeeds;
#          missing core file does NOT inflate installed count or set status
# ===========================================================================

class TestRosterApplyStatusAfterWrite:

    def test_missing_core_does_not_set_core_managed_status(self, project, capsys):
        """
        If an agent is in the install set but its core file is MISSING, roster apply
        must WARN and NOT flip the agent's status to core-managed.

        Setup: apply founders first so ada ends up staged (builders are not in founders).
        Then remove ada's core file and apply builders — ada should NOT become
        core-managed because the core file is gone.
        """
        p = _build_squad_project(project)
        # Stage ada by applying founders (ada is in builders, not founders)
        p.mod.cmd_roster(ns(roster_sub="apply", path_name="founders"), p.root)
        assert p.lock()["files"][_core_key("ada")]["status"] == "staged"

        # Remove ada's core file before the builders apply
        (p.root / _core_key("ada")).unlink()
        capsys.readouterr()

        p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
        out = capsys.readouterr().out
        assert "WARN" in out and "core missing" in out.lower()

        # Status must remain staged — NOT promoted to core-managed
        lock = p.lock()
        status = lock["files"][_core_key("ada")]["status"]
        assert status == "staged", (
            f"ada should remain 'staged' after missing-core roster apply; got {status!r}"
        )

    def test_missing_core_does_not_inflate_installed_count(self, project, capsys):
        """
        Missing-core agent must NOT appear in the installed count.

        Setup: apply founders first so ada ends up staged; remove ada's core;
        then apply builders — installed count must be 7 (not 8) since ada's core is gone.
        """
        p = _build_squad_project(project)
        # Stage ada first via founders apply
        p.mod.cmd_roster(ns(roster_sub="apply", path_name="founders"), p.root)
        assert p.lock()["files"][_core_key("ada")]["status"] == "staged"
        # Remove ada's core file
        (p.root / _core_key("ada")).unlink()
        capsys.readouterr()

        p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
        out = capsys.readouterr().out
        # builders install set = leah + eva + 5 squad + 1 orch = 8
        # With ada's core missing, installed count should be 7, not 8
        assert "installed: 7" in out, (
            f"Expected 'installed: 7' (ada excluded due to missing core). Got:\n{out}"
        )

    def test_gate_error_does_not_set_core_managed_status(self, project, capsys):
        """
        If guarded_write raises GateError (gate skipped), the agent's status must
        not be flipped to core-managed — the lock must reflect the pre-apply state.
        """
        import shutil, os
        p = _build_squad_project(project)
        # Make the live_path for ada a symlink into a never_touch zone to trigger
        # a GateError.  We achieve this by temporarily making ada's live_path a
        # symlink that points outside the owned tree — just verify the contract:
        # if status is NOT staged before apply (it's core-managed), we trust the
        # gate logic; instead, we test the reverse: start staged and confirm that
        # a gate failure leaves status as staged.
        lock = p.lock()
        lock["files"][_core_key("ada")]["status"] = "staged"
        p.mod.save_lock(p.root, lock)
        # Ensure the live file is absent (staged)
        live_path = p.root / _live("ada")
        if live_path.exists():
            live_path.unlink()

        # Now patch the lock live_path to a never_touch path
        lock = p.lock()
        lock["files"][_core_key("ada")]["live_path"] = ".env"
        p.mod.save_lock(p.root, lock)
        capsys.readouterr()

        # roster apply tries to install ada but guarded_write will refuse .env (never_touch)
        p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
        out = capsys.readouterr().out

        lock = p.lock()
        status = lock["files"][_core_key("ada")]["status"]
        # Status should remain staged (gate refused) — NOT core-managed
        assert status == "staged", (
            f"Status should remain 'staged' after gate failure; got {status!r}"
        )


# ===========================================================================
# Fix 3 — staged-missing WARN in doctor/verify (non-failing)
# ===========================================================================

class TestStagedMissingWarn:

    def _make_staged_missing_core(self, project):
        """
        Build a project where one staged agent has its core file deleted after
        the lock entry was created. This represents an un-recruitable staged agent.
        """
        p = _build_squad_project(project)
        p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
        # athena is now staged (benched by builders apply)
        # Remove athena's core file to make it un-recruitable
        core_path = p.root / _core_key("athena")
        core_path.unlink()
        return p

    def test_doctor_staged_missing_core_warns_not_fails(self, project, capsys):
        """
        Doctor must surface a STAGED-WARN for a staged entry whose core file is
        missing (un-recruitable) but must NOT exit with code 1.
        """
        p = self._make_staged_missing_core(project)
        capsys.readouterr()

        # Must NOT raise SystemExit
        p.mod.cmd_doctor(ns(json_out=False, fix=False, path=None), p.root)
        out = capsys.readouterr().out

        assert "doctor: OK" in out, "Doctor should still be OK despite staged missing core"
        assert "STAGED-WARN" in out, (
            "Doctor should surface STAGED-WARN for a staged agent with missing core"
        )

    def test_verify_staged_missing_core_warns_not_fails(self, project, capsys):
        """
        Verify must surface a STAGED-WARN for a staged entry whose core file is
        missing but must NOT exit with code 1.
        """
        p = self._make_staged_missing_core(project)
        capsys.readouterr()

        # Must NOT raise SystemExit
        p.mod.cmd_verify(ns(), p.root)
        out = capsys.readouterr().out

        assert "verify: OK" in out, "Verify should still be OK despite staged missing core"
        assert "STAGED-WARN" in out, (
            "Verify should surface STAGED-WARN for a staged agent with missing core"
        )

    def test_doctor_staged_no_live_path_warns_not_fails(self, project, capsys):
        """
        Doctor must surface a STAGED-WARN for a staged lock entry whose live_path
        attribute is absent in the lock (cannot even determine where to install).
        """
        p = _build_squad_project(project)
        p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
        # Corrupt athena's lock entry: remove its live_path
        lock = p.lock()
        lock["files"][_core_key("athena")]["live_path"] = None
        p.mod.save_lock(p.root, lock)
        capsys.readouterr()

        p.mod.cmd_doctor(ns(json_out=False, fix=False, path=None), p.root)
        out = capsys.readouterr().out

        assert "doctor: OK" in out
        assert "STAGED-WARN" in out

    def test_verify_staged_no_live_path_warns_not_fails(self, project, capsys):
        """
        Verify must surface a STAGED-WARN for a staged lock entry with no live_path
        but must NOT exit with code 1.
        """
        p = _build_squad_project(project)
        p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
        lock = p.lock()
        lock["files"][_core_key("athena")]["live_path"] = None
        p.mod.save_lock(p.root, lock)
        capsys.readouterr()

        p.mod.cmd_verify(ns(), p.root)
        out = capsys.readouterr().out

        assert "verify: OK" in out
        assert "STAGED-WARN" in out

    def test_doctor_check_file_staged_missing_core_returns_staged_warn(self, project):
        """
        doctor_check_file returns staged_warn (not issues) for staged + missing core.
        pristine must be True so it does not feed into the error/drift counts.
        """
        name = "athena"
        p = _build_squad_project(project)
        p.mod.cmd_roster(ns(roster_sub="apply", path_name="builders"), p.root)
        lock = p.lock()
        attrs = lock["files"][_core_key(name)]
        # Remove the core file
        (p.root / _core_key(name)).unlink()

        r = p.mod.doctor_check_file(_core_key(name), attrs, p.root)

        assert r["staged_warn"], "staged_warn should be non-empty"
        assert r["issues"] == [], "issues must be empty for staged missing core (non-failing)"
        assert r["pristine"] is True, "pristine must be True — staged missing core is not drift"
        assert "core file missing" in r["staged_warn"][0]

    def test_missing_core_of_non_staged_not_treated_as_staged_warn(self, project, capsys):
        """
        Regression guard: a core-managed entry with a missing core file must show
        ISSUE (not STAGED-WARN). staged_warn treatment must never leak to non-staged
        entries.
        """
        p = _build_squad_project(project)
        p.mod.cmd_roster(ns(roster_sub="apply", path_name="founders"), p.root)
        # athena is installed (core-managed) after founders apply
        assert p.lock()["files"][_core_key("athena")]["status"] == "core-managed"
        # Remove core file
        (p.root / _core_key("athena")).unlink()
        capsys.readouterr()

        p.mod.cmd_doctor(ns(json_out=False, fix=False, path=None), p.root)
        out = capsys.readouterr().out

        # Must show ISSUE (standard path), not the staged-specific STAGED-WARN
        assert "STAGED-WARN" not in out, (
            "STAGED-WARN must NOT appear for a core-managed entry with missing core"
        )
        assert "core file missing" in out.lower() or "ISSUE" in out, (
            "Expected 'ISSUE' or 'core file missing' in doctor output for core-managed + missing core"
        )
