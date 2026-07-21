"""
Render-target abstraction (Phase 1 — Decision #1: "doctrine compiles, never
copied"; docs/ULTIMATE_FRAMEWORK_PLAN.md Part B + adapters/README.md).

Coverage:
  * RENDER_TARGETS registry contains exactly "claude-code" (Phase 1 scope).
  * ClaudeCodeRenderTarget.live_globs() is a genuine subset of the REAL
    tess.manifest.json owned_globs — a target can never claim a live path
    the write gate would refuse (checked against the shipped manifest, not
    a synthetic stand-in, so drift between the target and the manifest is
    caught).
  * `tessctl render` (no flags) and `tessctl render --target claude-code`
    produce byte-identical live output — the flag is additive, not a
    behavior change (Phase 1 backward-compatibility guarantee).
  * `tessctl render --list-targets` and the unknown-target error path.
  * DETERMINISM: two independent projects with byte-identical core content
    render byte-identical live output (same core -> same output, regardless
    of process/root).
  * IDEMPOTENCY: calling render() twice in a row on one project with no core
    change produces identical live bytes both times, and doctor/verify stay
    green after both calls (no drift accumulates).
  * The target's writes are still gated by the manifest write gate (a
    RenderTarget cannot bypass check_manifest_write_gate).
"""

from __future__ import annotations

import json

import pytest

from conftest import MANIFEST_SRC


# ---------------------------------------------------------------------------
# A minimal, self-contained render fixture (deliberately NOT using
# {{TESS_ROOT}} in the template body, so cross-root byte comparisons in the
# determinism test are meaningful without needing to strip the root token).
# ---------------------------------------------------------------------------

_TPL = (
    "# Tess OS — Render Target Fixture\n"
    "\n"
    "## Rule Zero\n"
    "{{CORE_RULE_ZERO}}\n"
    "\n"
    "## System Laws\n"
    "{{CORE_SYSTEM_LAWS}}\n"
    "\n"
    "## Orchestrators\n"
    "{{CORE_ORCHESTRATORS}}\n"
    "\n"
    "## Commands\n"
    "{{CORE_COMMANDS}}\n"
    "\n"
    "## Directory\n"
    "{{CORE_DIRECTORY}}\n"
)

_FRAGMENTS = {
    ".tess/core/templates/claude-md/rule-zero.md": "RULE ZERO FIXTURE\n",
    ".tess/core/templates/claude-md/system-laws.md": "SYSTEM LAWS FIXTURE\n",
    ".tess/core/templates/claude-md/orchestrators.md": "ORCHESTRATORS FIXTURE\n",
    ".tess/core/templates/claude-md/commands.md": "COMMANDS FIXTURE\n",
    ".tess/core/templates/claude-md/directory.md": "DIRECTORY FIXTURE\n",
}
_TPL_KEY = ".tess/core/templates/CLAUDE.md.tpl"
_SETTINGS = '{"feature_flag": "fixture"}\n'  # no {{TESS_ROOT}} — root-independent
_SETTINGS_KEY = ".tess/core/settings-core.json"


def _seed(project):
    """Register the render inputs as core-managed lock entries (mirrors the
    real lock's shape: template + fragments -> CLAUDE.md; settings-core ->
    .claude/settings.json), without materializing the live files yet."""
    project.add("CLAUDE.md", _TPL, core_key=_TPL_KEY, render_live=False)
    for core_key, content in _FRAGMENTS.items():
        project.add("CLAUDE.md", content, core_key=core_key, render_live=False)
    project.add(".claude/settings.json", _SETTINGS, core_key=_SETTINGS_KEY,
                render_live=False)


# ---------------------------------------------------------------------------
# Registry + interface shape
# ---------------------------------------------------------------------------

def test_registry_contains_claude_code_and_phase_2_targets(engine):
    """Phase 2 adds "codex" and "generic" to the registry alongside Phase 1's
    "claude-code" — see tests/test_render_targets_codex_generic.py for their
    own dedicated coverage (this file stays claude-code-focused)."""
    assert set(engine.RENDER_TARGETS) == {"claude-code", "codex", "generic"}
    target = engine.RENDER_TARGETS["claude-code"]
    assert isinstance(target, engine.RenderTarget)
    assert target.name == "claude-code"


def test_render_target_base_class_is_not_implemented(engine, project):
    project.write()
    base = engine.RenderTarget()
    with pytest.raises(NotImplementedError):
        base.live_globs()
    with pytest.raises(NotImplementedError):
        base.render(project.root)


def test_claude_code_live_globs_are_subset_of_real_manifest_owned_globs(engine):
    """The target can never claim a live path the write gate would refuse —
    checked against the REAL, shipped tess.manifest.json (not a stand-in),
    so drift between the target's declared scope and the manifest is caught."""
    manifest = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))
    owned = manifest["owned_globs"]
    target = engine.RENDER_TARGETS["claude-code"]
    for live_glob in target.live_globs():
        assert engine.path_matches_globs(live_glob, owned), (
            f"{live_glob!r} (declared by ClaudeCodeRenderTarget.live_globs()) "
            f"does not match any pattern in the real manifest's owned_globs — "
            f"the target claims a path the write gate would refuse."
        )


# ---------------------------------------------------------------------------
# HIGH-1 (Fable Phase-1 review): the two new interface methods
# ---------------------------------------------------------------------------

def test_render_target_base_class_new_methods_default_to_nothing(engine, project):
    """Base RenderTarget's expected_live_bytes/render_generated_paths do NOT
    raise NotImplementedError (unlike live_globs/render) — a target with no
    bespoke-compiled artifacts need not override them."""
    project.write()
    base = engine.RenderTarget()
    assert base.expected_live_bytes(project.root, "CLAUDE.md") is None
    assert base.render_generated_paths(project.root) == set()


def test_claude_code_expected_live_bytes_matches_bespoke_compile_functions(engine, project):
    """expected_live_bytes() for the two templated artifacts must equal
    calling render_claude_md()/render_settings_json() directly — proving
    render_core_to_live() (which calls expected_live_bytes()) will compute
    the SAME bytes doctor/verify compare against, not a naive core-byte
    copy."""
    _seed(project)
    project.write()
    target = engine.RENDER_TARGETS["claude-code"]

    claude_expected = target.expected_live_bytes(project.root, "CLAUDE.md")
    assert claude_expected == engine.render_claude_md(project.root).encode("utf-8")

    settings_expected = target.expected_live_bytes(project.root, ".claude/settings.json")
    assert settings_expected == engine.render_settings_json(project.root).encode("utf-8")


def test_claude_code_expected_live_bytes_none_for_paths_it_does_not_compile(engine, project):
    """A path outside this target's two bespoke-compiled artifacts (e.g. the
    copy-only surface, or simply an unrelated path) returns None — the
    generic render_core_to_live() fallback handles it, unchanged."""
    project.write()
    target = engine.RENDER_TARGETS["claude-code"]
    assert target.expected_live_bytes(project.root, ".claude/agents/athena.md") is None
    assert target.expected_live_bytes(project.root, "conductor/identity.md") is None
    assert target.expected_live_bytes(project.root, "nonexistent/path.md") is None


def test_claude_code_render_generated_paths_matches_live_globs(engine, project):
    """This target has no copy-only path within its own scope (see the class
    docstring) — render_generated_paths() is exactly live_globs() as a set,
    so doctor/verify route drift on all 5 to `tessctl render`, not
    `tessctl capture`."""
    project.write()
    target = engine.RENDER_TARGETS["claude-code"]
    assert target.render_generated_paths(project.root) == set(target.live_globs())


def test_render_return_contract_is_pinned(engine, project):
    """LOW-3: render() returns {"target": name, "status": "rendered"} —
    pinned so a Phase 2+ target's return value is inspectable in a
    consistent shape across every target."""
    _seed(project)
    project.write()
    target = engine.RENDER_TARGETS["claude-code"]
    result = target.render(project.root, verbose=False)
    assert result == {"target": "claude-code", "status": "rendered"}


def test_render_generated_live_paths_derives_from_enabled_targets(engine, project):
    """render_generated_live_paths(root) (HIGH-1) must equal the real
    manifest's default-enabled claude-code target's render_generated_paths —
    proving it's genuinely derived from the registry + enablement, not a
    resurrected copy of the old frozenset constant."""
    project.write()
    target = engine.RENDER_TARGETS["claude-code"]
    assert engine.render_generated_live_paths(project.root) == frozenset(
        target.render_generated_paths(project.root)
    )


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------

def test_cli_list_targets(project, run_cli):
    _seed(project)
    project.write()
    r = run_cli(project.root, "render", "--list-targets")
    assert r.returncode == 0, r.stderr
    assert "claude-code" in r.stdout
    assert "CLAUDE.md" in r.stdout
    # --list-targets must not render anything
    assert not (project.root / "CLAUDE.md").exists()


def test_cli_unknown_target_rejected_by_argparse(project, run_cli):
    """"codex" is now a REGISTERED target (Phase 2) — use a name that is
    genuinely unknown to prove the choices= validation still rejects an
    unrecognized --target."""
    _seed(project)
    project.write()
    r = run_cli(project.root, "render", "--target", "nonexistent-target")
    assert r.returncode != 0
    assert "invalid choice" in r.stderr


def test_cli_default_render_equals_explicit_claude_code_target(project, run_cli):
    """`tessctl render` (no flags) and `tessctl render --target claude-code`
    must be byte-identical — the --target flag is additive, not a behavior
    change, for the one target Phase 1 ships."""
    _seed(project)
    project.write()

    r1 = run_cli(project.root, "render")
    assert r1.returncode == 0, r1.stderr
    claude_default = project.read_live("CLAUDE.md")
    settings_default = project.read_live(".claude/settings.json")

    r2 = run_cli(project.root, "render", "--target", "claude-code")
    assert r2.returncode == 0, r2.stderr
    claude_explicit = project.read_live("CLAUDE.md")
    settings_explicit = project.read_live(".claude/settings.json")

    assert claude_default == claude_explicit
    assert settings_default == settings_explicit
    assert "RULE ZERO FIXTURE" in claude_default


# ---------------------------------------------------------------------------
# Determinism — same core -> same output, independent of process/root
# ---------------------------------------------------------------------------

def test_determinism_across_independent_projects(tmp_path, engine):
    from conftest import Project

    proj_a = Project(tmp_path / "a", engine)
    proj_b = Project(tmp_path / "b", engine)
    _seed(proj_a)
    _seed(proj_b)
    proj_a.write()
    proj_b.write()

    target = engine.RENDER_TARGETS["claude-code"]
    target.render(proj_a.root, verbose=False)
    target.render(proj_b.root, verbose=False)

    claude_a = proj_a.read_live("CLAUDE.md")
    claude_b = proj_b.read_live("CLAUDE.md")
    settings_a = proj_a.read_live(".claude/settings.json")
    settings_b = proj_b.read_live(".claude/settings.json")

    assert claude_a == claude_b, "identical core produced different CLAUDE.md across independent roots"
    assert settings_a == settings_b, "identical core produced different settings.json across independent roots"
    assert engine.sha256_str(claude_a) == engine.sha256_str(claude_b)


# ---------------------------------------------------------------------------
# Idempotency — repeat render, no drift
# ---------------------------------------------------------------------------

def test_idempotent_repeat_render_no_drift(project, run_cli):
    _seed(project)
    project.write()

    target = project.mod.RENDER_TARGETS["claude-code"]
    target.render(project.root, verbose=False)
    claude_1 = project.read_live("CLAUDE.md")
    settings_1 = project.read_live(".claude/settings.json")

    target.render(project.root, verbose=False)
    claude_2 = project.read_live("CLAUDE.md")
    settings_2 = project.read_live(".claude/settings.json")

    assert claude_1 == claude_2, "second render() call produced different bytes than the first (not idempotent)"
    assert settings_1 == settings_2

    # doctor/verify must stay green after two consecutive renders — no drift
    # accumulates from re-rendering an unchanged core.
    d = run_cli(project.root, "doctor")
    assert d.returncode == 0, f"doctor not clean after idempotent re-render:\n{d.stdout}\n{d.stderr}"
    v = run_cli(project.root, "verify")
    assert v.returncode == 0, f"verify not clean after idempotent re-render:\n{v.stdout}\n{v.stderr}"


def test_render_ordering_is_target_agnostic_repeat_call(project):
    """Calling render() a third time (simulating a second `tessctl render`
    invocation in a later session) still reproduces the same bytes — the
    determinism guarantee holds across an arbitrary number of calls, not
    just twice."""
    _seed(project)
    project.write()
    target = project.mod.RENDER_TARGETS["claude-code"]

    hashes = set()
    for _ in range(3):
        target.render(project.root, verbose=False)
        hashes.add(project.mod.sha256_str(project.read_live("CLAUDE.md")))
    assert len(hashes) == 1, "render() produced different CLAUDE.md bytes across repeat calls"


# ---------------------------------------------------------------------------
# The target cannot bypass the manifest write gate
# ---------------------------------------------------------------------------

def test_render_target_honors_manifest_write_gate(project, engine):
    """A RenderTarget's render() is not a privileged bypass of the write
    gate: if a (corrupted) manifest no longer owns CLAUDE.md, the render
    must refuse to write it, exactly like any other guarded_write caller."""
    _seed(project)
    project.write()

    # Poison the manifest: remove CLAUDE.md from owned_globs.
    manifest_path = project.root / "tess.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["owned_globs"] = [g for g in manifest["owned_globs"] if g != "CLAUDE.md"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    target = engine.RENDER_TARGETS["claude-code"]
    with pytest.raises(engine.GateError):
        target.render(project.root, verbose=False)
