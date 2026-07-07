"""
Worker-profile denylist drift check — G3 (2026-07-08, the 2026-07-07 honest
reckoning). Fixes PR #43 (`goal-codex-render`): the branch's AGENTS.md.tpl
opened with `{{CORE_RULE_ZERO}}` and the rendered AGENTS.md carried, verbatim,
"RULE ZERO — ALWAYS DISPATCH. NEVER EXECUTE SOLO... If about to use Bash,
Grep, Glob, Edit, or Write for anything else: STOP and dispatch" — addressed
to Codex, Cursor, Copilot, Gemini CLI, Zed, Devin, none of which can dispatch
at all. This is the exact mechanism the 2026-07-07 proving-ground benchmark
measured as harmful to a single-agent harness (a weak model attempted a
nested subagent spawn on a bare `python3 --version` task under this exact
doctrine).

This suite proves two things:
  1. The REAL shipped worker-profile render (AGENTS.md, both `codex` and
     `generic`) is clean today — the fix actually landed.
  2. `_check_worker_profile_denylist()` genuinely detects a regression (not
     just a check that always passes) — a synthetic worker-profile fixture
     seeded with a denylisted phrase is caught, and `tessctl doctor`,
     `tessctl verify`, and `tessctl lock --check` all fail loud on it (not
     just one of the three).
"""

from __future__ import annotations

import json

from conftest import ns


# ---------------------------------------------------------------------------
# 1. The REAL shipped render is clean
# ---------------------------------------------------------------------------

def test_real_worker_profile_render_has_no_denylist_violations(engine):
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent
    violations = engine._check_worker_profile_denylist(repo_root)
    assert violations == [], (
        f"Worker-profile doctrine leak(s) detected in the REAL shipped render: "
        f"{violations} — orchestration doctrine must never reach a "
        f"single-agent harness's doctrine digest."
    )


def test_real_agents_md_tpl_does_not_reference_orchestrator_only_tokens(engine):
    """A structural companion to the content check above: the WORKER
    template must not even REQUEST the orchestrator-only fragments (Rule
    Zero, System Laws, the 26-command table) — catches a regression at the
    token level, before it would even reach rendered content."""
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent
    tpl = (repo_root / engine.AGENTS_MD_TPL).read_text(encoding="utf-8")
    for forbidden_token in (
        "{{CORE_RULE_ZERO}}", "{{CORE_SYSTEM_LAWS}}",
        "{{CORE_ORCHESTRATORS}}", "{{CORE_COMMANDS}}", "{{COMMAND_TABLE}}",
    ):
        assert forbidden_token not in tpl, (
            f"{forbidden_token!r} found in AGENTS.md.tpl — an orchestrator-only "
            f"fragment token has no business in the worker doctrine profile."
        )


def test_real_agents_md_line_count_stays_lean(engine):
    """G3's own budget: the worker profile digest is ~40-60 lines. A loose
    upper bound (not the denylist's job, but cheap to assert here) — if this
    ever creeps back toward the pre-G3 hundreds of lines, that is its own
    signal something orchestration-shaped snuck back in."""
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent
    rendered = engine.render_agents_md(repo_root)
    line_count = rendered.count("\n")
    assert line_count < 100, (
        f"rendered AGENTS.md is {line_count} lines — the worker doctrine "
        f"profile is supposed to stay ~40-60 lines; this far over budget "
        f"suggests non-lean content crept back in."
    )


# ---------------------------------------------------------------------------
# 2. The check genuinely detects a regression (synthetic fixture)
# ---------------------------------------------------------------------------

_LEAKY_AGENTS_TPL = (
    "# AGENTS.md Leaky Fixture\n"
    "\n"
    "{{WORKER_HARD_FLOOR}}\n"
)
_LEAKY_FRAGMENT = "ALWAYS DISPATCH. NEVER EXECUTE SOLO.\n"
_LEAKY_TPL_KEY = ".tess/core/templates/agents-md/AGENTS.md.tpl"
_LEAKY_FRAG_KEY = ".tess/core/templates/agents-md/worker-hard-floor.md"


def _seed_leaky_worker_profile(project):
    """A minimal synthetic project whose worker-profile AGENTS.md render
    contains a denylisted phrase — reproducing the exact #43 harm at unit
    scale, independent of the real repo's (now-clean) content."""
    project.add(None, _LEAKY_AGENTS_TPL, core_key=_LEAKY_TPL_KEY, render_live=False)
    project.add(None, _LEAKY_FRAGMENT, core_key=_LEAKY_FRAG_KEY, render_live=False)


def test_denylist_check_detects_synthetic_regression(engine, project):
    _seed_leaky_worker_profile(project)
    project.write()
    violations = engine._check_worker_profile_denylist(project.root)
    by_phrase = {v["phrase"] for v in violations}
    assert "always dispatch" in by_phrase
    assert "never execute solo" in by_phrase
    # Both worker-profile targets share the same AGENTS.md digest, so both
    # must be flagged, not just one.
    targets_hit = {v["target"] for v in violations}
    assert targets_hit == {"codex", "generic"}


def test_denylist_check_case_insensitive(engine, project):
    project.add(
        None, "always DISPATCH everything, Rule Zero applies.\n",
        core_key=_LEAKY_FRAG_KEY, render_live=False,
    )
    project.add(None, _LEAKY_AGENTS_TPL, core_key=_LEAKY_TPL_KEY, render_live=False)
    project.write()
    violations = engine._check_worker_profile_denylist(project.root)
    phrases = {v["phrase"] for v in violations}
    assert "always dispatch" in phrases
    assert "rule zero" in phrases


def test_denylist_check_clean_when_no_violation(engine, project):
    project.add(
        None, "Stay in scope. Finish the change and stop.\n",
        core_key=_LEAKY_FRAG_KEY, render_live=False,
    )
    project.add(None, _LEAKY_AGENTS_TPL, core_key=_LEAKY_TPL_KEY, render_live=False)
    project.write()
    assert engine._check_worker_profile_denylist(project.root) == []


def test_denylist_check_runs_regardless_of_enablement(engine, project):
    """G3: the check is a property of core render logic, not per-install
    enablement — it must fire even when codex/generic aren't in
    tess.manifest.json's render_targets.enabled list (the shipped default)."""
    _seed_leaky_worker_profile(project)
    project.write()
    manifest = json.loads((project.root / "tess.manifest.json").read_text())
    assert manifest.get("render_targets", {}).get("enabled", ["claude-code"]) == ["claude-code"]
    violations = engine._check_worker_profile_denylist(project.root)
    assert violations, "denylist check must fire even for a not-yet-enabled worker target"


# ---------------------------------------------------------------------------
# Wired into doctor / verify / lock --check
# ---------------------------------------------------------------------------

def test_doctor_fails_loud_on_denylist_leak(project):
    _seed_leaky_worker_profile(project)
    project.write()
    import pytest
    with pytest.raises(SystemExit) as exc:
        project.mod.cmd_doctor(ns(json_out=False, fix=False, path=None), project.root)
    assert exc.value.code == 1


def test_doctor_json_fails_loud_on_denylist_leak(project, capsys):
    _seed_leaky_worker_profile(project)
    project.write()
    import pytest
    with pytest.raises(SystemExit) as exc:
        project.mod.cmd_doctor(ns(json_out=True, fix=False, path=None), project.root)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "DOCTRINE LEAK" in out


def test_verify_fails_loud_on_denylist_leak(project):
    _seed_leaky_worker_profile(project)
    project.write()
    import pytest
    with pytest.raises(SystemExit) as exc:
        project.mod.cmd_verify(ns(), project.root)
    assert exc.value.code == 1


def test_lock_check_fails_loud_on_denylist_leak(project):
    _seed_leaky_worker_profile(project)
    project.write()
    import pytest
    with pytest.raises(SystemExit) as exc:
        project.mod.cmd_lock(ns(check=True, regen=False), project.root)
    assert exc.value.code == 1


def test_doctor_clean_when_worker_profile_is_lean(project):
    """Non-regression: seeding a CLEAN worker-profile fixture must not trip
    the new check (it must not false-positive on ordinary content)."""
    project.add(
        None, "Stay in scope. Finish the change and stop.\n",
        core_key=_LEAKY_FRAG_KEY, render_live=False,
    )
    project.add(None, _LEAKY_AGENTS_TPL, core_key=_LEAKY_TPL_KEY, render_live=False)
    project.write()
    # doctor may still exit 0 or non-zero for unrelated reasons in a minimal
    # fixture with no other lock entries; isolate the denylist signal
    # specifically rather than asserting a bare exit code here.
    violations = project.mod._check_worker_profile_denylist(project.root)
    assert violations == []
