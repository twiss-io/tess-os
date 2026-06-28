"""
M4 + M6 remediation — hardening coverage for the persona/identity render layer.

This suite differs from test_identity_persona_layer.py in one decisive way: it
runs against a *full copy of the real Tess OS root* (real CLAUDE.md.tpl, real
core fragments, real operator stubs, real 985-entry tess.lock) instead of a
minimal hermetic stub. That is the only way to prove the remediation holds on
the actually-shipped surface, where the render path threads through six lock
entries that all map to CLAUDE.md, real persona splicing, and real base_sha pins.

Covered (per the M4+M6 remediation brief):
  (1) REAL-TEMPLATE render — after `rename X` + `set-operator Y`, the live
      CLAUDE.md addresses the operator by name, carries the new conductor name,
      has ZERO stale bare-'Tess' (product token 'Tess OS' allowed), and both
      doctor and verify EXIT 0.
  (2) PERSONA TAMPER — appending bytes to any .tess/core/personas/*.md makes
      doctor AND verify FAIL with a core-tamper; restoring returns to green.
  (3) PROFILE SANITIZE — a malformed operator/profile.json (non-string name,
      brace-injection, bogus pathway, non-dict, invalid JSON) never crashes
      render/doctor; offending fields coerce to defaults.
  (4) RENDER-GENERATED DRIFT — editing an injected operator stub makes doctor /
      verify recommend `tessctl render` (NOT `tessctl capture`) for CLAUDE.md,
      and `doctor --fix` re-renders so a subsequent doctor is clean.
  (5) PERSONA ASSETS — all five persona files stay byte-distinct and each ships
      both a confirmation sample and an error/blocker sample.
"""

from __future__ import annotations

import itertools
import json
import re
import shutil

import pytest

from conftest import REPO_ROOT

PERSONA_KEYS = ("chief-of-staff", "co-founder", "strategist", "guide", "operator")

# Live paths the render layer generates (mirror of RENDER_GENERATED_LIVE_PATHS).
_REAL_PERSONAS = REPO_ROOT / ".tess" / "core" / "personas"

_COPY_IGNORE = shutil.ignore_patterns(
    ".git", "tests", ".pytest_cache", "__pycache__", ".github"
)


@pytest.fixture
def real_root(tmp_path):
    """A fresh, isolated copy of the real Tess OS root.

    Carries the genuine CLAUDE.md.tpl, core fragments, operator stubs, persona
    blocks, engine, and the full tess.lock (985 entries) so doctor/verify run
    against the shipped surface. Heavy/dev-only dirs are excluded — none are
    referenced by the lock (asserted in the build session), so doctor stays
    pristine on a fresh copy.
    """
    dst = tmp_path / "os"
    shutil.copytree(REPO_ROOT, dst, ignore=_COPY_IGNORE)
    return dst


def _bare_tess_hits(text: str) -> list[str]:
    """Occurrences of 'Tess' that are NOT the product token 'Tess OS'."""
    return [m for m in re.findall(r"Tess(?: OS)?", text) if m != "Tess OS"]


# ---------------------------------------------------------------------------
# (1) REAL-TEMPLATE render
# ---------------------------------------------------------------------------

def test_real_template_rename_and_set_operator_clean(real_root, run_cli):
    root = real_root

    # Fresh copy is pristine before any personalization.
    assert run_cli(root, "doctor").returncode == 0

    assert run_cli(root, "rename", "Atlas").returncode == 0
    assert run_cli(root, "set-operator", "Alex").returncode == 0
    # The verbs auto-render; run render explicitly to exercise the full path.
    assert run_cli(root, "render").returncode == 0

    claude = (root / "CLAUDE.md").read_text(encoding="utf-8")

    # Operator addressed by name (the {{OPERATOR_NAME}} token site).
    assert "Alex" in claude, "operator name not rendered into CLAUDE.md"
    assert "**Operator this instance serves:** Alex" in claude

    # Conductor name propagated (the {{ASSISTANT_NAME}} token sites). The real
    # template hardcodes the product token 'Tess OS' (not '{{ASSISTANT_NAME}} OS'),
    # so the rename surfaces as bare conductor references flipping to 'Atlas'.
    assert "Atlas" in claude
    assert "Who Atlas is" in claude  # conductor/identity Further-Reading row token site

    # ZERO stale bare-'Tess' — every conductor reference is the new name.
    stale = _bare_tess_hits(claude)
    assert stale == [], f"{len(stale)} stale bare-'Tess' occurrence(s) survived rename"
    # …but the product token IS preserved (Tess OS reform note + changelog line).
    assert "Tess OS" in claude

    # No unresolved template tokens leaked into the live entry point.
    assert "{{" not in claude and "}}" not in claude

    # The two render-generated conductor files also flip cleanly.
    identity = (root / "conductor" / "identity.md").read_text(encoding="utf-8")
    personality = (root / "conductor" / "personality.md").read_text(encoding="utf-8")
    assert "Atlas" in identity and _bare_tess_hits(identity) == []
    assert "Atlas" in personality and "Alex" in personality
    assert _bare_tess_hits(personality) == []

    # The load-bearing invariant: a personalized real instance is NOT drift.
    d = run_cli(root, "doctor")
    assert d.returncode == 0, f"doctor flagged personalized instance:\n{d.stdout}"
    assert "doctor: OK" in d.stdout
    v = run_cli(root, "verify")
    assert v.returncode == 0, f"verify flagged personalized instance:\n{v.stdout}"
    assert "verify: OK" in v.stdout


def test_real_template_profile_reflects_both_names(real_root, run_cli):
    root = real_root
    assert run_cli(root, "rename", "Atlas").returncode == 0
    assert run_cli(root, "set-operator", "Alex").returncode == 0
    profile = json.loads((root / "operator" / "profile.json").read_text())
    assert profile["assistant_name"] == "Atlas"
    assert profile["operator_name"] == "Alex"


# ---------------------------------------------------------------------------
# (2) PERSONA TAMPER — core-integrity tracking on .tess/core/personas/*.md
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("persona_key", PERSONA_KEYS)
def test_persona_tamper_fails_doctor_and_verify(real_root, run_cli, persona_key):
    root = real_root
    # Baseline: a fresh real copy is clean.
    assert run_cli(root, "doctor").returncode == 0

    persona = root / ".tess" / "core" / "personas" / f"{persona_key}.md"
    original = persona.read_bytes()
    persona.write_bytes(original + b"\n## INJECTED MARKER -- tamper probe\n")

    d = run_cli(root, "doctor")
    assert d.returncode == 1, f"doctor did not fail on tampered {persona_key}.md"
    assert "CORE-TAMPER" in d.stdout
    assert f"{persona_key}.md" in d.stdout
    assert "core tamper(s) detected" in d.stdout

    v = run_cli(root, "verify")
    assert v.returncode == 1, f"verify did not fail on tampered {persona_key}.md"
    assert "CORE TAMPER" in v.stdout
    assert f"{persona_key}.md" in v.stdout

    # Restoring the pristine bytes returns the instance to green.
    persona.write_bytes(original)
    assert run_cli(root, "doctor").returncode == 0
    assert run_cli(root, "verify").returncode == 0


# ---------------------------------------------------------------------------
# (3) PROFILE SANITIZE — malformed profile.json never crashes render/doctor
# ---------------------------------------------------------------------------

def test_malformed_profile_coerces_and_does_not_crash(real_root, engine, run_cli):
    root = real_root
    (root / "operator" / "profile.json").write_text(
        json.dumps({
            "assistant_name": ["inject", "list"],          # non-string → '[' → default
            "operator_name": "Pwn{{ASSISTANT_NAME}}{}",    # brace-injection → default
            "pathway": "totally-bogus",                    # invalid → default
        }),
        encoding="utf-8",
    )

    # Loader must not raise and must coerce every offending field to its default.
    prof = engine._load_operator_profile(root)
    assert isinstance(prof["assistant_name"], str)
    assert isinstance(prof["operator_name"], str)
    assert prof["assistant_name"] == "Tess"
    assert prof["operator_name"] == "Operator"
    assert prof["pathway"] == "chief-of-staff"
    assert "{" not in prof["operator_name"] and "}" not in prof["operator_name"]

    # render_claude_md must not raise and must neutralize the injection.
    claude = engine.render_claude_md(root)
    assert "{{ASSISTANT_NAME}}" not in claude
    assert "{{OPERATOR_NAME}}" not in claude
    assert "Pwn" not in claude, "brace-injection payload survived into render"

    # CLI doctor must not crash; after a re-render from the coerced state it is clean.
    assert run_cli(root, "render").returncode == 0
    d = run_cli(root, "doctor")
    assert d.returncode == 0, f"doctor crashed/failed on coerced profile:\n{d.stdout}\n{d.stderr}"


def test_numeric_profile_name_coerced_to_string_not_crash(real_root, engine):
    """A bare JSON number for a name is a TypeError landmine for naive .strip();
    the loader must str()-coerce it (no crash) rather than default it."""
    root = real_root
    (root / "operator" / "profile.json").write_text(
        json.dumps({"assistant_name": 12345}), encoding="utf-8"
    )
    prof = engine._load_operator_profile(root)
    assert prof["assistant_name"] == "12345"     # coerced via str(), still valid charset
    # Render does not raise.
    assert "{{ASSISTANT_NAME}}" not in engine.render_claude_md(root)


@pytest.mark.parametrize("raw", [
    "[1, 2, 3]", "42", '"just a string"', "{not valid json", "",
    # HIGH-2: list/dict pathway values raise TypeError on unhashable `not in frozenset`.
    # The fix (isinstance guard) must coerce them to the default without crashing.
    '{"pathway": []}',
    '{"pathway": {}}',
])
def test_profile_non_dict_or_invalid_json_falls_back_to_defaults(real_root, engine, raw):
    root = real_root
    (root / "operator" / "profile.json").write_text(raw, encoding="utf-8")
    prof = engine._load_operator_profile(root)
    assert prof == {
        "assistant_name": "Tess",
        "operator_name": "Operator",
        "pathway": "chief-of-staff",
    }
    # And render still succeeds against defaults.
    assert "{{" not in engine.render_claude_md(root)


# ---------------------------------------------------------------------------
# (4) RENDER-GENERATED DRIFT — remedy is `render`, never `capture`
# ---------------------------------------------------------------------------

def test_render_generated_drift_recommends_render_not_capture(real_root, run_cli):
    root = real_root
    assert run_cli(root, "doctor").returncode == 0

    # identity-stub.md is the one operator stub that injects (no inject:false),
    # so editing it makes the rendered CLAUDE.md stale.
    stub = root / "operator" / "identity-stub.md"
    stub.write_text(
        stub.read_text(encoding="utf-8") + "\nOperator note added by test.\n",
        encoding="utf-8",
    )

    d = run_cli(root, "doctor")
    assert d.returncode == 1, "doctor did not detect stale render-generated CLAUDE.md"

    # The CLAUDE.md drift line points to render, and capture is NEVER suggested.
    claude_drift_lines = [
        ln for ln in d.stdout.splitlines() if "CLAUDE.md" in ln and "DRIFT" in ln
    ]
    assert claude_drift_lines, f"no CLAUDE.md DRIFT line:\n{d.stdout}"
    assert all("tessctl render" in ln for ln in claude_drift_lines)
    assert "capture CLAUDE.md" not in d.stdout
    assert "Render-generated file(s) are stale" in d.stdout

    # verify reaches the same verdict with the render remedy.
    v = run_cli(root, "verify")
    assert v.returncode == 1
    assert "render-generated file is stale" in v.stdout
    assert "capture CLAUDE.md" not in v.stdout

    # doctor --fix re-renders render-generated files (not capture)…
    fx = run_cli(root, "doctor", "--fix")
    assert "re-rendering render-generated files" in fx.stdout
    assert "rendered  CLAUDE.md" in fx.stdout

    # …and a subsequent doctor is clean.
    assert run_cli(root, "doctor").returncode == 0


# ---------------------------------------------------------------------------
# (5) PERSONA ASSETS — byte-distinct + confirmation & error samples each
# ---------------------------------------------------------------------------

def test_personas_byte_distinct_with_confirmation_and_error_samples():
    bodies: dict[str, str] = {}
    for key in PERSONA_KEYS:
        path = _REAL_PERSONAS / f"{key}.md"
        assert path.exists(), f"persona file missing: {key}.md"
        body = path.read_text(encoding="utf-8")
        bodies[key] = body
        # Each persona ships a worked confirmation sample AND an error/blocker sample.
        assert "### Confirmation Sample" in body, f"{key}: missing confirmation sample"
        assert "### Error / Blocker Sample" in body, f"{key}: missing error/blocker sample"

    # All five remain byte-distinct from one another.
    for a, b in itertools.combinations(PERSONA_KEYS, 2):
        assert bodies[a] != bodies[b], f"{a} and {b} are byte-identical"


# ---------------------------------------------------------------------------
# (6) HIGH-1: update gate ignores render-generated drift — does NOT block,
#     does NOT say `capture` for CLAUDE.md
# ---------------------------------------------------------------------------

def test_update_gate_ignores_render_generated_drift(real_root, run_cli):
    """HIGH-1: render-generated drift on CLAUDE.md (stale stub) is NOT a
    gate blocker.  Step 1 must pass and must never emit 'capture CLAUDE.md'.
    """
    root = real_root
    assert run_cli(root, "doctor").returncode == 0, "baseline must be clean"

    # Edit the injecting operator stub — makes CLAUDE.md render-stale.
    stub = root / "operator" / "identity-stub.md"
    stub.write_text(
        stub.read_text(encoding="utf-8") + "\nOperator note — gate test.\n",
        encoding="utf-8",
    )

    # Confirm doctor detects the stale CLAUDE.md.
    d = run_cli(root, "doctor")
    assert d.returncode == 1, "doctor should detect stale CLAUDE.md"
    assert "CLAUDE.md" in d.stdout

    # update --dry-run must pass the gate (Step 1) — render-stale is NOT a blocker.
    upd = run_cli(root, "update", "--dry-run")

    assert "doctor gate: PASS" in upd.stdout, (
        f"update gate unexpectedly blocked on render-generated drift:\n{upd.stdout}\n{upd.stderr}"
    )
    # The wrong remedy must never appear.
    assert "capture CLAUDE.md" not in upd.stdout, (
        f"update gate emitted the wrong remedy 'capture' for CLAUDE.md:\n{upd.stdout}"
    )
    assert "BLOCKED" not in upd.stdout, (
        f"update gate reported BLOCKED for render-stale CLAUDE.md:\n{upd.stdout}"
    )


# ---------------------------------------------------------------------------
# (7) QUINN: client template is rename-aware — {{ASSISTANT_NAME}} tokenized
# ---------------------------------------------------------------------------

def test_client_template_rename_aware(real_root, run_cli):
    """QUINN: after rename + restore, clients/_template/CLAUDE.md carries
    the new conductor name with zero stale bare-'Tess' occurrences.
    """
    root = real_root
    assert run_cli(root, "doctor").returncode == 0, "baseline must be clean"

    # Rename the conductor and re-render.
    assert run_cli(root, "rename", "Atlas").returncode == 0

    # restore re-applies ALL core files to the live tree, including the client
    # template.  The token substitution ({{ASSISTANT_NAME}} → "Atlas") must flow
    # through render_core_to_live for clients/_template/CLAUDE.md.
    r = run_cli(root, "restore")
    assert r.returncode == 0, f"restore failed:\n{r.stdout}\n{r.stderr}"

    tpl = (root / "clients" / "_template" / "CLAUDE.md").read_text(encoding="utf-8")

    # "Atlas" must be present (name token resolved).
    assert "Atlas" in tpl, "conductor name not rendered into client template"

    # Zero stale bare-'Tess' — every conductor reference must be the new name.
    stale = _bare_tess_hits(tpl)
    assert stale == [], (
        f"{len(stale)} stale bare-'Tess' occurrence(s) in client template "
        f"after rename to 'Atlas': {stale}"
    )

    # doctor must pass after restore propagated the rename.
    d = run_cli(root, "doctor")
    assert d.returncode == 0, f"doctor failed after rename+restore:\n{d.stdout}"
