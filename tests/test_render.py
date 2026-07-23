"""
Render + token substitution.

  * apply_token_sub: {{TESS_ROOT}} → absolute root
  * render_core_to_live: token sub + .local.md append-first shadow
  * parse_operator_stub: inject:false → empty, inject:true → body
  * render_settings_json: {{TESS_ROOT}} sub + JSON-validity guard
  * render_claude_md: template token map + operator stub injection
"""

from __future__ import annotations

import json

import pytest

from conftest import REPO_ROOT


def test_apply_token_sub(engine, project):
    out = engine.apply_token_sub("root is {{TESS_ROOT}} ok", project.root)
    assert out == f"root is {project.root} ok"


def test_render_core_to_live_substitutes_token(engine, project):
    core_key = project.add("conductor/tok.md", "path={{TESS_ROOT}}\n",
                           render_live=False)
    project.write()
    rendered = engine.render_core_to_live(
        project.core(core_key), project.live("conductor/tok.md"), project.root)
    assert rendered.decode() == f"path={project.root}\n"


def test_render_appends_local_md_shadow(engine, project):
    core_key = project.add("conductor/shadow.md", "CORE BODY\n", render_live=False)
    project.write()
    # The append-first customization layer.
    (project.root / "conductor").mkdir(parents=True, exist_ok=True)
    (project.root / "conductor" / "shadow.local.md").write_text("LOCAL ADDENDUM\n")
    rendered = engine.render_core_to_live(
        project.core(core_key), project.live("conductor/shadow.md"), project.root
    ).decode()
    assert "CORE BODY" in rendered
    assert "LOCAL ADDENDUM" in rendered
    assert rendered.index("CORE BODY") < rendered.index("LOCAL ADDENDUM")


def test_parse_operator_stub_inject_false_returns_empty(engine, project):
    content = (
        "<!-- stub -->\n---\nzone: OPERATOR_PROFILE\ninject: false\n---\n\n"
        "# Hidden Profile\nshould not appear\n"
    )
    p = project.root / "operator" / "user-profile.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    assert engine.parse_operator_stub(content, p) == ""


def test_parse_operator_stub_inject_true_returns_body(engine, project):
    content = "---\nzone: OPERATOR_IDENTITY\ninject: true\n---\n\n# Visible\nbody here\n"
    p = project.root / "operator" / "identity-stub.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    body = engine.parse_operator_stub(content, p)
    assert "# Visible" in body and "body here" in body
    assert "inject" not in body  # frontmatter stripped


def test_render_settings_json_substitutes_and_validates(engine, project):
    src = project.root / ".tess" / "core" / "settings-core.json"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(json.dumps({"root": "{{TESS_ROOT}}", "n": 1}))
    out = engine.render_settings_json(project.root)
    parsed = json.loads(out)
    assert parsed["root"] == str(project.root)
    assert parsed["n"] == 1


def test_render_settings_json_real_core_file_carries_assistant_name_token(engine, project):
    """Issue #21 follow-up: the REAL shipped `.tess/core/settings-core.json`
    once hardcoded the literal default name inside the `PostToolUse` hook's
    embedded systemMessage JSON string ("If you are Tess: send a Telegram
    update..."), instead of the `{{ASSISTANT_NAME}}` token every other
    render surface uses — so a renamed conductor's own settings.json still
    told it to act as "Tess". `render_settings_json` -> `apply_token_sub`
    substitutes on raw text regardless of file type; this proves the ACTUAL
    shipped file (not a synthetic stand-in) round-trips the token rather
    than shipping a literal name that can never be renamed."""
    real = (REPO_ROOT / ".tess" / "core" / "settings-core.json").read_text(encoding="utf-8")
    assert "{{ASSISTANT_NAME}}" in real, (
        "settings-core.json's PostToolUse hook no longer carries the "
        "{{ASSISTANT_NAME}} token — issue #21 has regressed"
    )
    assert "If you are Tess" not in real

    src = project.root / ".tess" / "core" / "settings-core.json"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(real, encoding="utf-8")

    out = engine.render_settings_json(project.root)
    json.loads(out)  # still valid JSON after substitution
    assert "If you are Atlas" not in out  # sanity: default profile, not yet renamed
    assert "If you are Tess" in out  # default profile renders the default name


def test_render_settings_json_rejects_invalid_json(engine, project):
    src = project.root / ".tess" / "core" / "settings-core.json"
    src.parent.mkdir(parents=True, exist_ok=True)
    # {{TESS_ROOT}} unquoted → invalid JSON after substitution
    src.write_text('{"root": {{TESS_ROOT}}}')
    with pytest.raises(SystemExit):
        engine.render_settings_json(project.root)


def test_render_claude_md_resolves_tokens_and_injection(engine, project):
    tpl_dir = project.root / ".tess" / "core" / "templates"
    frag_dir = tpl_dir / "claude-md"
    frag_dir.mkdir(parents=True, exist_ok=True)
    # Template references one core fragment + two operator stubs.
    (tpl_dir / "CLAUDE.md.tpl").write_text(
        "# Tess\n{{CORE_RULE_ZERO}}\n\nID:\n{{OPERATOR_IDENTITY}}\n\n"
        "PROFILE:\n{{OPERATOR_PROFILE}}\n"
    )
    (frag_dir / "rule-zero.md").write_text("RULE ZERO BLOCK")
    op = project.root / "operator"
    op.mkdir(parents=True, exist_ok=True)
    (op / "identity-stub.md").write_text(
        "---\nzone: OPERATOR_IDENTITY\ninject: true\n---\n\nIDENTITY VISIBLE")
    (op / "user-profile.md").write_text(
        "---\nzone: OPERATOR_PROFILE\ninject: false\n---\n\nPROFILE HIDDEN")

    out = engine.render_claude_md(project.root)
    assert "RULE ZERO BLOCK" in out      # core fragment resolved
    assert "IDENTITY VISIBLE" in out     # inject:true stub surfaced
    assert "PROFILE HIDDEN" not in out   # inject:false stub suppressed
    assert "{{CORE_RULE_ZERO}}" not in out  # all tokens consumed
