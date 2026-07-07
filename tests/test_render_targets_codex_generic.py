"""
Phase 2 (Codex + generic render targets) — docs/ULTIMATE_FRAMEWORK_PLAN.md
Part B §B.2; adapters/codex/README.md + adapters/generic/README.md.

Mirrors the structure of tests/test_render_targets.py (Phase 1's
claude-code coverage) for the two new targets:

  * Registry + interface shape (genuine RenderTarget subclasses; live_globs()
    is a subset of the REAL tess.manifest.json owned_globs).
  * AGENTS.md is SHARED — byte-identical whether produced by `codex` or
    `generic` (render_agents_md() takes no harness argument; see its
    docstring in .tess/bin/tessctl).
  * expected_live_bytes() for every compiled artifact (AGENTS.md,
    .codex/config.toml, .codex/prompts/*.md, prompts/*.md) matches the
    direct render function it wraps — proving render_core_to_live() (and
    therefore doctor/verify) will compare against the SAME bytes the target
    actually writes.
  * Determinism + idempotency, exactly like the claude-code suite.
  * The manifest write gate is honored (a target cannot bypass it).
  * The untracked-render-generated pass (_check_untracked_render_generated) —
    the mechanism doctor/verify/`lock --check` use to drift-check
    `.codex/prompts/*.md` / `prompts/*.md`, which have NO individual
    tess.lock entry of their own (the underlying `.tess/core/commands/*.md`
    core file is already lock-tracked under a DIFFERENT live_path,
    `.claude/commands/*.md` — see that function's docstring).
  * `tessctl update`'s Step 7 re-renders AGENTS.md from newly-fetched core —
    "a doctrine edit re-propagates into AGENTS.md" via a real signed
    fetch + update cycle (mirrors test_tracked_render_e2e.py).
"""

from __future__ import annotations

import json

import pytest

from conftest import MANIFEST_SRC, make_upstream, ns


# ---------------------------------------------------------------------------
# Synthetic fixture: AGENTS.md template + fragments + a couple of commands.
# Deliberately independent of the real .tess/core content (same convention
# test_render_targets.py / test_tracked_render_e2e.py already use).
# ---------------------------------------------------------------------------

_AGENTS_TPL = (
    "# AGENTS.md Fixture\n"
    "\n"
    "{{CORE_RULE_ZERO}}\n"
    "\n"
    "{{CORE_HARD_FLOOR}}\n"
    "\n"
    "{{CORE_SYSTEM_LAWS}}\n"
    "\n"
    "{{CORE_DIRECTORY}}\n"
    "\n"
    "{{HARNESS_NOTE}}\n"
    "\n"
    "{{COMMAND_TABLE}}\n"
)

_AGENTS_FRAGMENTS = {
    ".tess/core/templates/claude-md/rule-zero.md": "RULE ZERO FIXTURE\n",
    ".tess/core/templates/claude-md/hard-floor.md": "HARD FLOOR FIXTURE\n",
    ".tess/core/templates/claude-md/system-laws.md": "SYSTEM LAWS FIXTURE\n",
    ".tess/core/templates/claude-md/directory.md": "DIRECTORY FIXTURE\n",
    ".tess/core/templates/agents-md/harness-note.md": "HARNESS NOTE FIXTURE\n",
}
_AGENTS_TPL_KEY = ".tess/core/templates/agents-md/AGENTS.md.tpl"

_CODEX_CONFIG_TOML = 'approval_policy = "on-request"\nsandbox_mode = "workspace-write"\n'
_CODEX_CONFIG_KEY = ".tess/core/templates/agents-md/codex-config.toml.tpl"

_COMMANDS_V1 = {
    "wake": "---\ndescription: Session start checklist V1\n---\n\n# /wake\n\nDo the wake thing.\n",
    "close": "---\ndescription: Session end checklist V1\n---\n\n# /close\n\nDo the close thing.\n",
}


def _seed_agents(project, commands=None):
    """Register the AGENTS.md render inputs as core-managed lock entries,
    mirroring the real lock's shape (template + fragments -> AGENTS.md,
    core-internal via live_path=None — see .tess/tess.lock's real entries
    for agents-md/**), plus a couple of command bodies REGISTERED UNDER
    THEIR CLAUDE-CODE LIVE PATH (.claude/commands/<name>.md) — reproducing
    the real "already tracked elsewhere" situation .codex/prompts and
    prompts mirror into."""
    commands = _COMMANDS_V1 if commands is None else commands
    project.add(None, _AGENTS_TPL, core_key=_AGENTS_TPL_KEY, render_live=False)
    for core_key, content in _AGENTS_FRAGMENTS.items():
        project.add(None, content, core_key=core_key, render_live=False)
    project.add(None, _CODEX_CONFIG_TOML, core_key=_CODEX_CONFIG_KEY, render_live=False)
    for name, body in commands.items():
        # render_live=True: the .claude/commands/*.md live copy is written
        # immediately (mirrors reality — these are already restored/rendered
        # in a real repo) so an unrelated "live file missing" doctor issue on
        # THIS ordinary, already-tracked entry never contaminates a test
        # asserting doctor/verify is clean for codex/generic-specific reasons.
        project.add(
            f".claude/commands/{name}.md", body,
            core_key=f".tess/core/commands/{name}.md", render_live=True,
        )


def _set_enabled(project, names):
    mf_path = project.root / "tess.manifest.json"
    manifest = json.loads(mf_path.read_text(encoding="utf-8"))
    manifest.setdefault("render_targets", {})["enabled"] = list(names)
    mf_path.write_text(json.dumps(manifest), encoding="utf-8")


# ---------------------------------------------------------------------------
# Registry + interface shape
# ---------------------------------------------------------------------------

def test_registry_contains_codex_and_generic(engine):
    assert {"codex", "generic"} <= set(engine.RENDER_TARGETS)
    codex = engine.RENDER_TARGETS["codex"]
    generic = engine.RENDER_TARGETS["generic"]
    assert isinstance(codex, engine.RenderTarget) and codex.name == "codex"
    assert isinstance(generic, engine.RenderTarget) and generic.name == "generic"


def test_neither_codex_nor_generic_enabled_by_default(engine):
    """MED-3: registering a target in RENDER_TARGETS is not the same as
    enabling it for every existing install — the real tess.manifest.json's
    default enabled list must still be exactly ["claude-code"]."""
    manifest = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))
    assert manifest["render_targets"]["enabled"] == ["claude-code"]


@pytest.mark.parametrize("target_name", ["codex", "generic"])
def test_live_globs_are_subset_of_real_manifest_owned_globs(engine, target_name):
    manifest = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))
    owned = manifest["owned_globs"]
    target = engine.RENDER_TARGETS[target_name]
    for live_glob in target.live_globs():
        assert engine.path_matches_globs(live_glob, owned), (
            f"{live_glob!r} (declared by {target_name}'s live_globs()) does not "
            f"match any pattern in the real manifest's owned_globs — the target "
            f"claims a path the write gate would refuse."
        )


# ---------------------------------------------------------------------------
# AGENTS.md is SHARED — byte-identical regardless of which target renders it
# ---------------------------------------------------------------------------

def test_agents_md_is_byte_identical_between_codex_and_generic(engine, project):
    """render_agents_md() takes no harness argument by design (see its
    docstring) — both targets' expected_live_bytes("AGENTS.md") must agree,
    so enabling both at once (unusual, but not forbidden) never races two
    DIFFERENT contents for the same root-level file."""
    _seed_agents(project)
    project.write()
    codex = engine.RENDER_TARGETS["codex"]
    generic = engine.RENDER_TARGETS["generic"]
    assert (
        codex.expected_live_bytes(project.root, "AGENTS.md")
        == generic.expected_live_bytes(project.root, "AGENTS.md")
        == engine.render_agents_md(project.root).encode("utf-8")
    )


def test_render_agents_md_reuses_shared_fragments_verbatim(engine, project):
    """The claude-md/ fragments the fixture seeds (RULE ZERO FIXTURE, HARD
    FLOOR FIXTURE, SYSTEM LAWS FIXTURE, DIRECTORY FIXTURE) must appear
    verbatim in the rendered AGENTS.md — proving real reuse, not a
    re-authored copy."""
    _seed_agents(project)
    project.write()
    rendered = engine.render_agents_md(project.root)
    for marker in ("RULE ZERO FIXTURE", "HARD FLOOR FIXTURE", "SYSTEM LAWS FIXTURE",
                   "DIRECTORY FIXTURE", "HARNESS NOTE FIXTURE"):
        assert marker in rendered, f"{marker!r} missing from rendered AGENTS.md — fragment not reused"


def test_render_agents_md_command_table_is_generated_from_command_frontmatter(engine, project):
    _seed_agents(project)
    project.write()
    rendered = engine.render_agents_md(project.root)
    assert "`/wake`" in rendered and "Session start checklist V1" in rendered
    assert "`/close`" in rendered and "Session end checklist V1" in rendered


# ---------------------------------------------------------------------------
# expected_live_bytes() matches the direct render functions for every path
# ---------------------------------------------------------------------------

def test_codex_expected_live_bytes_matches_render_functions(engine, project):
    _seed_agents(project)
    project.write()
    codex = engine.RENDER_TARGETS["codex"]
    assert codex.expected_live_bytes(project.root, "AGENTS.md") == \
        engine.render_agents_md(project.root).encode("utf-8")
    assert codex.expected_live_bytes(project.root, ".codex/config.toml") == \
        engine.render_codex_config_toml(project.root).encode("utf-8")
    assert codex.expected_live_bytes(project.root, ".codex/prompts/wake.md") == \
        engine._render_command_prompt_bytes(project.root, "wake")
    assert b"Do the wake thing." in codex.expected_live_bytes(project.root, ".codex/prompts/wake.md")


def test_generic_expected_live_bytes_matches_render_functions(engine, project):
    _seed_agents(project)
    project.write()
    generic = engine.RENDER_TARGETS["generic"]
    assert generic.expected_live_bytes(project.root, "AGENTS.md") == \
        engine.render_agents_md(project.root).encode("utf-8")
    assert generic.expected_live_bytes(project.root, "prompts/close.md") == \
        engine._render_command_prompt_bytes(project.root, "close")
    assert b"Do the close thing." in generic.expected_live_bytes(project.root, "prompts/close.md")


def test_expected_live_bytes_none_for_paths_outside_scope(engine, project):
    _seed_agents(project)
    project.write()
    codex = engine.RENDER_TARGETS["codex"]
    generic = engine.RENDER_TARGETS["generic"]
    assert codex.expected_live_bytes(project.root, "conductor/identity.md") is None
    assert codex.expected_live_bytes(project.root, "prompts/wake.md") is None  # that's generic's path
    assert generic.expected_live_bytes(project.root, ".codex/config.toml") is None  # codex-only
    assert generic.expected_live_bytes(project.root, ".codex/prompts/wake.md") is None


def test_render_generated_paths_includes_every_command(engine, project):
    _seed_agents(project)
    project.write()
    codex = engine.RENDER_TARGETS["codex"]
    generic = engine.RENDER_TARGETS["generic"]
    codex_paths = codex.render_generated_paths(project.root)
    generic_paths = generic.render_generated_paths(project.root)
    assert codex_paths == {"AGENTS.md", ".codex/config.toml",
                           ".codex/prompts/wake.md", ".codex/prompts/close.md"}
    assert generic_paths == {"AGENTS.md", "prompts/wake.md", "prompts/close.md"}


def test_render_return_contract_is_pinned(engine, project):
    _seed_agents(project)
    project.write()
    _set_enabled(project, ["codex"])
    result = engine.RENDER_TARGETS["codex"].render(project.root, verbose=False)
    assert result == {"target": "codex", "status": "rendered"}


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------

def test_cli_list_targets_shows_three_targets(project, run_cli):
    _seed_agents(project)
    project.write()
    r = run_cli(project.root, "render", "--list-targets")
    assert r.returncode == 0, r.stderr
    for name in ("claude-code", "codex", "generic"):
        assert name in r.stdout
    assert "[disabled for this install]" in r.stdout  # codex/generic aren't in the default enabled list
    assert not (project.root / "AGENTS.md").exists()


def test_cli_render_target_codex_emits_agents_prompts_and_config(project, run_cli):
    _seed_agents(project)
    project.write()
    r = run_cli(project.root, "render", "--target", "codex")
    assert r.returncode == 0, r.stderr

    agents_md = project.read_live("AGENTS.md")
    assert "RULE ZERO FIXTURE" in agents_md
    assert "HARD FLOOR FIXTURE" in agents_md

    config_toml = project.read_live(".codex/config.toml")
    assert 'approval_policy = "on-request"' in config_toml

    wake_prompt = project.read_live(".codex/prompts/wake.md")
    assert "Do the wake thing." in wake_prompt
    close_prompt = project.read_live(".codex/prompts/close.md")
    assert "Do the close thing." in close_prompt


def test_cli_render_target_generic_emits_agents_and_plain_prompts(project, run_cli):
    _seed_agents(project)
    project.write()
    r = run_cli(project.root, "render", "--target", "generic")
    assert r.returncode == 0, r.stderr

    agents_md = project.read_live("AGENTS.md")
    assert "RULE ZERO FIXTURE" in agents_md

    assert not (project.root / ".codex").exists(), "generic must never write .codex/**"
    wake_prompt = project.read_live("prompts/wake.md")
    assert "Do the wake thing." in wake_prompt


# ---------------------------------------------------------------------------
# Determinism + idempotency (same shape as the claude-code suite)
# ---------------------------------------------------------------------------

def test_determinism_across_independent_projects(tmp_path, engine):
    from conftest import Project

    proj_a = Project(tmp_path / "a", engine)
    proj_b = Project(tmp_path / "b", engine)
    _seed_agents(proj_a)
    _seed_agents(proj_b)
    proj_a.write()
    proj_b.write()

    target = engine.RENDER_TARGETS["codex"]
    target.render(proj_a.root, verbose=False)
    target.render(proj_b.root, verbose=False)

    assert proj_a.read_live("AGENTS.md") == proj_b.read_live("AGENTS.md")
    assert proj_a.read_live(".codex/prompts/wake.md") == proj_b.read_live(".codex/prompts/wake.md")


def test_idempotent_repeat_render_no_drift(project, run_cli):
    _seed_agents(project)
    project.write()
    _set_enabled(project, ["codex"])

    target = project.mod.RENDER_TARGETS["codex"]
    target.render(project.root, verbose=False)
    agents_1 = project.read_live("AGENTS.md")
    target.render(project.root, verbose=False)
    agents_2 = project.read_live("AGENTS.md")
    assert agents_1 == agents_2

    d = run_cli(project.root, "doctor")
    assert d.returncode == 0, f"doctor not clean after idempotent re-render:\n{d.stdout}\n{d.stderr}"
    v = run_cli(project.root, "verify")
    assert v.returncode == 0, f"verify not clean after idempotent re-render:\n{v.stdout}\n{v.stderr}"


# ---------------------------------------------------------------------------
# The manifest write gate is honored — a target cannot bypass it
# ---------------------------------------------------------------------------

def test_codex_render_honors_manifest_write_gate(project, engine):
    _seed_agents(project)
    project.write()
    manifest_path = project.root / "tess.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["owned_globs"] = [g for g in manifest["owned_globs"] if g != "AGENTS.md"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    target = engine.RENDER_TARGETS["codex"]
    with pytest.raises(engine.GateError):
        target.render(project.root, verbose=False)


# ---------------------------------------------------------------------------
# Untracked-render-generated pass — doctor/verify/lock --check tracking for
# `.codex/prompts/*.md` / `prompts/*.md` (no individual tess.lock entry).
# ---------------------------------------------------------------------------

def test_untracked_check_clean_immediately_after_render(project, engine):
    _seed_agents(project)
    project.write()
    _set_enabled(project, ["codex"])
    engine.RENDER_TARGETS["codex"].render(project.root, verbose=False)

    covered = set()  # nothing lock-tracked under these live_paths
    results = engine._check_untracked_render_generated(project.root, covered)
    assert results, "expected at least AGENTS.md / .codex/config.toml / prompts to be checked"
    assert all(r["pristine"] is True for r in results), results


def test_doctor_flags_hand_edit_of_codex_prompt_as_uncaptured_drift(project, engine, run_cli, capsys):
    _seed_agents(project)
    project.write()
    _set_enabled(project, ["codex"])
    engine.RENDER_TARGETS["codex"].render(project.root, verbose=False)

    (project.root / ".codex" / "prompts" / "wake.md").write_text(
        "SOMEONE HAND-EDITED THIS\n", encoding="utf-8"
    )

    r = run_cli(project.root, "doctor")
    assert r.returncode == 1, r.stdout
    assert ".codex/prompts/wake.md" in r.stdout
    assert "tessctl render" in r.stdout
    assert "tessctl capture .codex/prompts/wake.md" not in r.stdout


def test_doctor_clean_when_codex_enabled_but_not_yet_rendered(project, run_cli):
    """A target's compiled artifacts having no individual tess.lock entry
    (see _check_untracked_render_generated's docstring) means "not yet
    rendered" is treated as a benign transient state, not an integrity
    failure — an enabled-but-not-yet-run target is not equivalent to a
    lock-tracked core-managed file going missing (that's the ordinary
    per-lock-entry loop's job, for the paths that DO carry that guarantee,
    e.g. CLAUDE.md)."""
    _seed_agents(project)
    project.write()
    _set_enabled(project, ["codex"])
    # Deliberately never call render() — codex is enabled but nothing exists yet.
    r = run_cli(project.root, "doctor")
    assert r.returncode == 0, f"doctor should tolerate an enabled-but-unrendered target:\n{r.stdout}\n{r.stderr}"


def test_doctor_clean_when_codex_disabled_and_never_rendered(project, run_cli):
    """MED-3, extended to the untracked-render-generated pass: a target's
    outputs are not expected to exist at all when it isn't enabled — no
    phantom "missing AGENTS.md" failure for an install that hasn't enabled
    codex/generic. (enabled=[] rather than ["claude-code"]: this fixture
    only seeds codex/generic's own core inputs, not claude-code's — see
    _seed_agents — so this isolates the claim to codex/generic specifically,
    without also requiring claude-code's unrelated CLAUDE.md.tpl etc. to be
    seeded just to keep IT out of the untracked-check's way.)"""
    _seed_agents(project)
    project.write()
    _set_enabled(project, [])  # nothing enabled, including codex/generic
    r = run_cli(project.root, "doctor")
    assert r.returncode == 0, f"doctor should be clean with codex disabled:\n{r.stdout}\n{r.stderr}"
    assert "missing" not in r.stdout.lower()


def test_verify_flags_stale_codex_prompt(project, run_cli):
    _seed_agents(project)
    project.write()
    _set_enabled(project, ["codex"])
    r0 = run_cli(project.root, "render", "--target", "codex")
    assert r0.returncode == 0, r0.stderr

    (project.root / ".codex" / "config.toml").write_text("HAND EDITED\n", encoding="utf-8")

    r = run_cli(project.root, "verify")
    assert r.returncode == 1, r.stdout
    assert ".codex/config.toml" in r.stdout
    assert "render-generated file is stale" in r.stdout


def test_lock_check_flags_stale_generic_prompt(project, run_cli):
    _seed_agents(project)
    project.write()
    _set_enabled(project, ["generic"])
    r0 = run_cli(project.root, "render", "--target", "generic")
    assert r0.returncode == 0, r0.stderr

    (project.root / "prompts" / "close.md").write_text("HAND EDITED\n", encoding="utf-8")

    r = run_cli(project.root, "lock", "--check")
    assert r.returncode == 1, r.stdout
    assert "prompts/close.md" in r.stdout


# ---------------------------------------------------------------------------
# `tessctl update`'s Step 7 re-renders AGENTS.md from newly-fetched core —
# "a doctrine edit re-propagates into AGENTS.md" (mirrors
# test_tracked_render_e2e.py's CLAUDE.md coverage).
# ---------------------------------------------------------------------------

def test_doctrine_edit_repropagates_into_agents_md_via_update(project, gpg_key, tmp_path, run_cli):
    _seed_agents(project)
    project.framework["upstream"] = str(tmp_path / "upstream")
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr
    project.write()
    _set_enabled(project, ["codex"])
    project.mod.RENDER_TARGETS["codex"].render(project.root, verbose=False)
    assert "RULE ZERO FIXTURE" in project.read_live("AGENTS.md")

    # Signed upstream v2.1.0 CHANGES the rule-zero fragment (a doctrine edit).
    up_core = {_AGENTS_TPL_KEY: _AGENTS_TPL}
    up_core.update(_AGENTS_FRAGMENTS)
    up_core[".tess/core/templates/claude-md/rule-zero.md"] = "RULE ZERO V2 — TRACKED VIA AGENTS.MD\n"
    up_core[_CODEX_CONFIG_KEY] = _CODEX_CONFIG_TOML
    for name, body in _COMMANDS_V1.items():
        up_core[f".tess/core/commands/{name}.md"] = body

    def _live_for(k):
        if k == _AGENTS_TPL_KEY or k in _AGENTS_FRAGMENTS or k == _CODEX_CONFIG_KEY:
            return None  # core-internal, matches the real lock's agents-md/** entries
        for name in _COMMANDS_V1:
            if k == f".tess/core/commands/{name}.md":
                return f".claude/commands/{name}.md"
        return None

    up_lock = {k: {"status": "core-managed", "tier": "normal", "live_path": _live_for(k)} for k in up_core}
    make_upstream(tmp_path / "upstream", gpg_key, "v2.1.0", sign="signed",
                  core_files=up_core, lock_files=up_lock)

    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    assert r.returncode == 0, f"update failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"

    live_agents = project.read_live("AGENTS.md")
    assert "RULE ZERO V2 — TRACKED VIA AGENTS.MD" in live_agents, (
        "AGENTS.md was NOT re-rendered from the new core fragment after `tessctl update` — "
        "the doctrine edit did not propagate"
    )
    assert "RULE ZERO FIXTURE" not in live_agents, "stale v1 fragment still present in live AGENTS.md"

    d = run_cli(project.root, "doctor")
    assert d.returncode == 0, f"doctor not clean after upgrade:\n{d.stdout}\n{d.stderr}"
    v = run_cli(project.root, "verify")
    assert v.returncode == 0, f"verify not clean after upgrade:\n{v.stdout}\n{v.stderr}"
