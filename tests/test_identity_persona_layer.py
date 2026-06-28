"""
M4 + M6 — name tokens + persona pathway render layer.

Covers the operator-personalization surface (M4 + M6):

  * {{ASSISTANT_NAME}} / {{OPERATOR_NAME}} token substitution (M6)
  * {{PATHWAY}} persona-block injection from .tess/core/personas/<key>.md (M4)
  * the `rename` / `set-operator` / `identity` / `pathway` verbs
  * the C5 name charset guard (_validate_name)

The single load-bearing property: a *personalized* instance (renamed conductor,
named operator, switched pathway) is NOT flagged as drift. After every name /
pathway mutation, `tessctl doctor` and `tessctl verify` must still EXIT 0 —
because the same render function that wrote the live files is the one doctor /
verify re-render and compare against. If that invariant ever breaks, a user who
renames their conductor would be told their install is corrupt.

Strategy:
  * The persona blocks and conductor templates are copied verbatim from the REAL
    repo core (REPO_ROOT/.tess/core) so the distinctive-voice assertions exercise
    the actually-shipped content, while the lock stays minimal/hermetic.
  * CLI verbs are driven through the real subprocess (run_cli) so argparse, the
    re-render, and exit codes are all exercised end-to-end.
"""

from __future__ import annotations

import difflib
import itertools
import json
import shutil

import pytest

from conftest import REPO_ROOT, ns

# ---------------------------------------------------------------------------
# Real shipped assets the render layer consumes
# ---------------------------------------------------------------------------

PERSONA_KEYS = ("chief-of-staff", "co-founder", "strategist", "guide", "operator")

# Header line present in exactly one persona file — the cleanest "this persona
# and not the others" discriminator.
PERSONA_HEADER = {
    "chief-of-staff": "## Active Pathway — Chief of Staff",
    "co-founder":     "## Active Pathway — Co-founder",
    "strategist":     "## Active Pathway — Strategist",
    "guide":          "## Active Pathway — Guide",
    "operator":       "## Active Pathway — Operator",
}

_REAL_PERSONAS = REPO_ROOT / ".tess" / "core" / "personas"
_REAL_CONDUCTOR = REPO_ROOT / ".tess" / "core" / "conductor"
_REAL_IDENTITY_STUB = REPO_ROOT / "operator" / "identity-stub.md"

# Minimal CLAUDE.md template: pulls in the operator identity stub (which carries
# {{ASSISTANT_NAME}}) plus a direct name token and one core fragment, so a rename
# propagates into the rendered CLAUDE.md exactly as it does in production.
_TPL = (
    "# {{ASSISTANT_NAME}} OS\n\n"
    "Root: {{TESS_ROOT}}\n\n"
    "{{OPERATOR_IDENTITY}}\n\n"
    "## Rule Zero\n"
    "{{CORE_RULE_ZERO}}\n"
)
_FRAGMENTS = {".tess/core/templates/claude-md/rule-zero.md": "Always dispatch. Never execute solo.\n"}
_TPL_KEY = ".tess/core/templates/CLAUDE.md.tpl"
_SETTINGS_KEY = ".tess/core/settings-core.json"
_SETTINGS = '{"root": "{{TESS_ROOT}}"}\n'

_CONDUCTOR_LIVE = ("conductor/identity.md", "conductor/personality.md")


# ---------------------------------------------------------------------------
# Builder — a self-contained instance carrying the full M4/M6 render surface
# ---------------------------------------------------------------------------

def _render_all_live(project):
    """(Re)write every tracked live file from the current profile.json state,
    mirroring what `tessctl render` / a CLI mutation does."""
    mod, root = project.mod, project.root
    project.write_live("CLAUDE.md", mod.render_claude_md(root))
    project.write_live(".claude/settings.json", mod.render_settings_json(root))
    for live_rel in _CONDUCTOR_LIVE:
        core_path = root / ".tess" / "core" / live_rel
        project.write_live(live_rel, mod.render_core_to_live(core_path, root / live_rel, root))


def _seed_identity_instance(project):
    """Stand up a hermetic Tess OS root with the real persona blocks + conductor
    templates + a minimal CLAUDE.md/settings render surface, all lock-tracked
    core-managed. No operator/profile.json → defaults (Tess / Operator /
    chief-of-staff) are in force until a verb writes one."""
    root = project.root

    # 1. Real persona blocks — inputs to the {{PATHWAY}} render.
    dst = root / ".tess" / "core" / "personas"
    dst.mkdir(parents=True, exist_ok=True)
    for key in PERSONA_KEYS:
        shutil.copy2(_REAL_PERSONAS / f"{key}.md", dst / f"{key}.md")

    # 2. Real operator identity stub (carries {{ASSISTANT_NAME}}).
    (root / "operator").mkdir(parents=True, exist_ok=True)
    shutil.copy2(_REAL_IDENTITY_STUB, root / "operator" / "identity-stub.md")

    # 3. CLAUDE.md template + fragment → CLAUDE.md (rendered last).
    project.add("CLAUDE.md", _TPL, core_key=_TPL_KEY, render_live=False)
    for core_key, content in _FRAGMENTS.items():
        project.add("CLAUDE.md", content, core_key=core_key, render_live=False)

    # 4. settings-core.json → .claude/settings.json (so _do_render has a target).
    project.add(".claude/settings.json", _SETTINGS, core_key=_SETTINGS_KEY, render_live=False)

    # 5. Real conductor identity.md + personality.md core (the token-bearing files
    #    _do_render re-renders by name). core_key defaults to .tess/core/<live_rel>.
    project.add("conductor/identity.md",
                (_REAL_CONDUCTOR / "identity.md").read_text(encoding="utf-8"),
                render_live=False)
    project.add("conductor/personality.md",
                (_REAL_CONDUCTOR / "personality.md").read_text(encoding="utf-8"),
                render_live=False)

    # 6. Flush manifest + lock, then render the pristine live tree.
    project.write()
    _render_all_live(project)
    return project


def _assert_clean(run_cli, root, when: str):
    """doctor AND verify must both EXIT 0 — the personalized-instance invariant."""
    d = run_cli(root, "doctor")
    assert d.returncode == 0, f"doctor flagged drift {when}:\n{d.stdout}\n{d.stderr}"
    assert "doctor: OK" in d.stdout
    v = run_cli(root, "verify")
    assert v.returncode == 0, f"verify flagged drift {when}:\n{v.stdout}\n{v.stderr}"
    assert "verify: OK" in v.stdout


# ---------------------------------------------------------------------------
# (1) set-operator — operator name flows into the rendered persona block
# ---------------------------------------------------------------------------

def test_set_operator_name_appears_in_render(project, run_cli):
    _seed_identity_instance(project)
    root = project.root

    # Default operator name is "Operator" and lives in the chief-of-staff
    # arrival beat: "Good morning, Operator."
    assert "Good morning, Operator." in project.read_live("conductor/personality.md")

    r = run_cli(root, "set-operator", "Alex Rivera")
    assert r.returncode == 0, f"set-operator failed:\n{r.stdout}\n{r.stderr}"

    profile = json.loads((root / "operator" / "profile.json").read_text())
    assert profile["operator_name"] == "Alex Rivera"

    pers = project.read_live("conductor/personality.md")
    assert "Good morning, Alex Rivera." in pers, "operator name not rendered into persona arrival beat"
    # The literal placeholder name in token sites is gone.
    assert "Good morning, Operator." not in pers

    _assert_clean(run_cli, root, "after set-operator")


# ---------------------------------------------------------------------------
# (2) rename — assistant name propagates to CLAUDE.md + conductor files
# ---------------------------------------------------------------------------

def test_rename_propagates_assistant_name(project, run_cli):
    _seed_identity_instance(project)
    root = project.root

    # Default conductor name is "Tess" (no profile.json written yet).
    assert project.mod._load_operator_profile(root)["assistant_name"] == "Tess"
    assert "# Identity — Tess" in project.read_live("conductor/identity.md")
    assert "Tess" in project.read_live("CLAUDE.md")

    r = run_cli(root, "rename", "Atlas")
    assert r.returncode == 0, f"rename failed:\n{r.stdout}\n{r.stderr}"

    assert json.loads((root / "operator" / "profile.json").read_text())["assistant_name"] == "Atlas"

    claude = project.read_live("CLAUDE.md")
    identity = project.read_live("conductor/identity.md")
    personality = project.read_live("conductor/personality.md")
    assert "Atlas" in claude and "Atlas OS" in claude
    assert "# Identity — Atlas" in identity
    assert "# Personality — Atlas" in personality
    # The name token sites no longer say Tess.
    assert "# Identity — Tess" not in identity
    assert "# Personality — Tess" not in personality

    _assert_clean(run_cli, root, "after rename")


def test_rename_noop_when_unchanged(project, run_cli):
    _seed_identity_instance(project)
    root = project.root
    run_cli(root, "rename", "Atlas")
    again = run_cli(root, "rename", "Atlas")
    assert again.returncode == 0
    assert "no change" in again.stdout
    _assert_clean(run_cli, root, "after no-op rename")


# ---------------------------------------------------------------------------
# (3) pathway — switching injects THAT persona's voice and no other
# ---------------------------------------------------------------------------

def test_pathway_switch_injects_distinct_persona(project, run_cli):
    _seed_identity_instance(project)
    root = project.root

    def assert_only(active_key, pers_text):
        assert PERSONA_HEADER[active_key] in pers_text, f"{active_key} block missing"
        for other in PERSONA_KEYS:
            if other != active_key:
                assert PERSONA_HEADER[other] not in pers_text, (
                    f"{other} block leaked while {active_key} active"
                )

    # Default pathway = chief-of-staff.
    assert project.mod._load_operator_profile(root)["pathway"] == "chief-of-staff"
    assert_only("chief-of-staff", project.read_live("conductor/personality.md"))

    for key in ("strategist", "co-founder", "operator", "guide"):
        r = run_cli(root, "pathway", key)
        assert r.returncode == 0, f"pathway {key} failed:\n{r.stdout}\n{r.stderr}"
        assert json.loads((root / "operator" / "profile.json").read_text())["pathway"] == key
        assert_only(key, project.read_live("conductor/personality.md"))
        _assert_clean(run_cli, root, f"after pathway {key}")


# ---------------------------------------------------------------------------
# (4) LOAD-BEARING — a fully personalized instance is never flagged as drift
# ---------------------------------------------------------------------------

def test_personalized_instance_not_flagged_as_drift(project, run_cli):
    """The whole point of the render layer: personalization is not corruption.
    doctor + verify stay green after EACH mutation and after the combined
    rename + set-operator + pathway personalization."""
    _seed_identity_instance(project)
    root = project.root

    _assert_clean(run_cli, root, "at pristine default state")

    assert run_cli(root, "rename", "Seraphina").returncode == 0
    _assert_clean(run_cli, root, "after rename")

    assert run_cli(root, "set-operator", "Jo").returncode == 0
    _assert_clean(run_cli, root, "after set-operator")

    assert run_cli(root, "pathway", "co-founder").returncode == 0
    _assert_clean(run_cli, root, "after pathway switch")

    # All three personalizations are simultaneously live and consistent.
    profile = json.loads((root / "operator" / "profile.json").read_text())
    assert profile == {"assistant_name": "Seraphina", "operator_name": "Jo", "pathway": "co-founder"} \
        or (profile["assistant_name"] == "Seraphina"
            and profile["operator_name"] == "Jo"
            and profile["pathway"] == "co-founder")
    pers = project.read_live("conductor/personality.md")
    assert "Seraphina" in pers and "Jo" in pers
    assert PERSONA_HEADER["co-founder"] in pers
    assert "Seraphina" in project.read_live("conductor/identity.md")


# ---------------------------------------------------------------------------
# (5) All five persona files exist and are non-trivially distinct
# ---------------------------------------------------------------------------

def test_all_persona_files_exist_and_are_distinct(engine):
    # Keys are exactly the engine's declared pathways.
    assert set(PERSONA_KEYS) == set(engine.VALID_PATHWAYS)

    texts = {}
    for key in PERSONA_KEYS:
        path = _REAL_PERSONAS / f"{key}.md"
        assert path.exists(), f"persona file missing: {key}.md"
        body = path.read_text(encoding="utf-8")
        assert len(body.strip()) > 200, f"persona {key} is suspiciously thin"
        texts[key] = body
        # Each file carries its own unique header, and that header alone.
        assert PERSONA_HEADER[key] in body

    # Headers are unique across the set; bodies are byte-distinct and have low
    # textual overlap (boilerplate blockquote aside).
    for a, b in itertools.combinations(PERSONA_KEYS, 2):
        assert texts[a] != texts[b], f"{a} and {b} are byte-identical"
        assert PERSONA_HEADER[a] not in texts[b], f"{a} header leaked into {b}"
        ratio = difflib.SequenceMatcher(None, texts[a], texts[b]).ratio()
        assert ratio < 0.6, f"{a} vs {b} too similar (ratio={ratio:.3f})"


# ---------------------------------------------------------------------------
# Token-layer units — resolution order, validation, profile coercion
# ---------------------------------------------------------------------------

def test_token_resolution_order_pathway_before_names(project, engine):
    """{{PATHWAY}} expands first so name tokens *inside* the injected persona
    block resolve in the same pass — the ordering claim in apply_token_sub."""
    _seed_identity_instance(project)
    root = project.root
    engine._save_operator_profile(
        root, {"assistant_name": "Atlas", "operator_name": "Alex", "pathway": "co-founder"}
    )
    out = engine.apply_token_sub("BEGIN {{PATHWAY}} END", root)
    assert PERSONA_HEADER["co-founder"] in out          # persona block injected
    assert "Atlas" in out and "Alex" in out             # its inner name tokens resolved
    assert "{{ASSISTANT_NAME}}" not in out
    assert "{{OPERATOR_NAME}}" not in out
    assert "{{PATHWAY}}" not in out


def test_missing_persona_falls_back_to_visible_marker(project, engine):
    """A partially-constructed install must not silently lose the injection
    zone — _render_pathway_block emits a visible comment when the file is gone."""
    block = engine._render_pathway_block(project.root, "nonexistent-key")
    assert "PATHWAY PERSONA MISSING" in block
    assert "nonexistent-key" in block


def test_load_profile_coerces_invalid_pathway(project, engine):
    root = project.root
    (root / "operator").mkdir(parents=True, exist_ok=True)
    (root / "operator" / "profile.json").write_text(
        json.dumps({"assistant_name": "X", "operator_name": "Y", "pathway": "bogus"}),
        encoding="utf-8",
    )
    prof = engine._load_operator_profile(root)
    assert prof["pathway"] == "chief-of-staff"   # coerced back to default
    assert prof["assistant_name"] == "X"          # valid fields preserved


def test_load_profile_defaults_when_absent(project, engine):
    prof = engine._load_operator_profile(project.root)
    assert prof == {
        "assistant_name": "Tess",
        "operator_name": "Operator",
        "pathway": "chief-of-staff",
    }


def test_validate_name_charset_guard(engine):
    # Accepted: letters, digits, spaces, hyphens, apostrophes, unicode letters.
    for good in ("Atlas", "Alex Rivera", "Jean-Luc", "O'Brien", "Tess2", "Renée"):
        assert engine._validate_name(good, "test") == good.strip()
    assert engine._validate_name("  Padded  ", "test") == "Padded"
    # Rejected: YAML/markdown breakers, control chars, empty, over-length.
    for bad in ("Bad:Name", "a{b}", "a[b]", "x#y", "a|b", "a`b", "", "   ",
                "a\nb", "x" * 31):
        with pytest.raises(SystemExit):
            engine._validate_name(bad, "test")


def test_rename_rejects_invalid_name_via_cli(project, run_cli):
    _seed_identity_instance(project)
    root = project.root
    r = run_cli(root, "rename", "Bad:Name")
    assert r.returncode != 0
    # Profile untouched, instance still clean.
    assert not (root / "operator" / "profile.json").exists()
    _assert_clean(run_cli, root, "after rejected rename")


def test_pathway_rejects_unknown_key_via_cli(project, run_cli):
    _seed_identity_instance(project)
    root = project.root
    r = run_cli(root, "pathway", "wizard")
    assert r.returncode != 0
    assert "unknown pathway" in (r.stdout + r.stderr)
    assert not (root / "operator" / "profile.json").exists()
    _assert_clean(run_cli, root, "after rejected pathway")


def test_identity_readonly_shows_state(project, run_cli):
    _seed_identity_instance(project)
    root = project.root
    run_cli(root, "rename", "Atlas")
    run_cli(root, "pathway", "operator")
    r = run_cli(root, "identity")           # no flags → read-only report
    assert r.returncode == 0
    assert "Atlas" in r.stdout
    assert "operator" in r.stdout
