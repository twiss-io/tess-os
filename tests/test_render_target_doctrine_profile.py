"""
RenderTarget.doctrine_profile — G3 (2026-07-08, the 2026-07-07 honest
reckoning: proving-ground/reports/2026-07-07*.md).

The benchmark's central finding: mounting the FULL orchestration doctrine
("always dispatch, never execute solo," the six outcome orchestrators, the
mission-ceremony command table) into a single-agent harness measured as
harmful, never helpful — in the fair run's verification probes, the mounted
CLAUDE.md caused a weak model to attempt an actual nested subagent spawn on
a task that only asked for `python3 --version`. `doctrine_profile` is the
seam that stops that payload from reaching a harness with no dispatchable
crew: it is DATA on the RenderTarget class (not a CLI flag someone forgets),
and every registered target must declare it.

Coverage:
  * Every REGISTERED target (regardless of per-install enablement)
    declares a doctrine_profile in DOCTRINE_PROFILES — a registry sweep, so
    a FUTURE target can never silently ship undeclared.
  * The known values: claude-code -> orchestrator; codex, generic -> worker.
  * doctrine_digest_paths(): the base class defaults to empty; claude-code
    -> {"CLAUDE.md"}; codex/generic -> {"AGENTS.md"}.
  * The orchestrator profile is UNCHANGED by G3 — CLAUDE.md.tpl and its
    claude-md/ fragments still carry the full doctrine (Rule Zero, the
    System Laws table, the Outcome Orchestrator layer) verbatim. G3 re-scoped
    ONLY the worker-profile AGENTS.md payload; the orchestrator's genuine
    case (Claude Code as Tess, which really does hold the Agent/Task tool)
    is untouched.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Registry sweep — every target declares a valid profile
# ---------------------------------------------------------------------------

def test_every_registered_target_declares_a_valid_doctrine_profile(engine):
    for name, target in engine.RENDER_TARGETS.items():
        assert target.doctrine_profile in engine.DOCTRINE_PROFILES, (
            f"RenderTarget {name!r} has doctrine_profile={target.doctrine_profile!r} — "
            f"must be one of {engine.DOCTRINE_PROFILES}. A target that skips declaring "
            f"this is invisible to the G3 worker-profile denylist drift check."
        )


def test_known_target_doctrine_profiles(engine):
    assert engine.RENDER_TARGETS["claude-code"].doctrine_profile == "orchestrator"
    assert engine.RENDER_TARGETS["codex"].doctrine_profile == "worker"
    assert engine.RENDER_TARGETS["generic"].doctrine_profile == "worker"


def test_base_render_target_has_no_default_profile(engine):
    """No default on purpose (see RenderTarget's own docstring) — a
    hypothetical bare RenderTarget() (never actually registered) must NOT
    silently count as either profile."""
    base = engine.RenderTarget()
    assert base.doctrine_profile == ""
    assert base.doctrine_profile not in engine.DOCTRINE_PROFILES


# ---------------------------------------------------------------------------
# doctrine_digest_paths() — the subset of render_generated_paths() scanned
# by the denylist check (see tests/test_worker_profile_denylist.py)
# ---------------------------------------------------------------------------

def test_doctrine_digest_paths_by_target(engine):
    from pathlib import Path
    dummy_root = Path("/nonexistent-for-this-test")
    assert engine.RENDER_TARGETS["claude-code"].doctrine_digest_paths(dummy_root) == {"CLAUDE.md"}
    assert engine.RENDER_TARGETS["codex"].doctrine_digest_paths(dummy_root) == {"AGENTS.md"}
    assert engine.RENDER_TARGETS["generic"].doctrine_digest_paths(dummy_root) == {"AGENTS.md"}


def test_base_render_target_doctrine_digest_paths_is_empty(engine):
    from pathlib import Path
    base = engine.RenderTarget()
    assert base.doctrine_digest_paths(Path("/nonexistent-for-this-test")) == set()


# ---------------------------------------------------------------------------
# The orchestrator profile is UNCHANGED — full doctrine intact
# ---------------------------------------------------------------------------

def test_orchestrator_profile_claude_md_still_has_full_doctrine(engine):
    """Positive control: G3 re-scoped ONLY the worker-profile AGENTS.md
    payload. The orchestrator's own CLAUDE.md.tpl + claude-md/ fragments
    (the genuine case — Claude Code as Tess holds the Agent/Task tool) must
    still carry Rule Zero, the System Laws table, and the Outcome
    Orchestrator layer verbatim, unchanged by this fix."""
    # Use the REAL repo root (this test intentionally reads the actual
    # shipped core, not a synthetic fixture — proving the real orchestrator
    # payload, not a stand-in).
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent
    rendered = engine.render_claude_md(repo_root)
    for marker in (
        "RULE ZERO",
        "ALWAYS DISPATCH",
        "NEVER EXECUTE SOLO",
        "Outcome Orchestrator Layer",
        "System Laws",
    ):
        assert marker in rendered, (
            f"{marker!r} missing from the real render_claude_md() output — "
            f"the orchestrator profile must stay full-doctrine; G3 must never "
            f"touch this render."
        )
