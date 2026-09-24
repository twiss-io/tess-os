"""
v0.2.0 (ws-rt): the `codex` render target emits Agent Skills, not
`.codex/prompts/`.

Codex never loads a project-scoped `.codex/prompts/` (openai/codex#9848,
closed NOT_PLANNED). It scans `.agents/skills/<name>/SKILL.md` from the
working directory up to the repo root
(https://learn.chatgpt.com/docs/build-skills.md). These tests pin the
behaviour that replaced the dead prompt mirrors:

  * one `.agents/skills/tess-<cmd>/SKILL.md` per core command, with Agent
    Skills frontmatter (`name` == directory name, `description`), plus an
    `agents/openai.yaml` that makes the skill explicit-only in Codex;
  * no `.codex/prompts/` file is written any more, and an existing one is
    reported as retired and left byte-for-byte untouched;
  * relative links in the command bodies still resolve from the skill dir;
  * the owned glob `.agents/skills/tess-*/**` beats the `.agents/**`
    never_touch for Tess's own skills only;
  * the committed render output in THIS repo matches the renderer;
  * a pre-0.2 manifest (no skills glob) skips the skills as not-owned and
    names the glob to add, instead of failing the render;
  * render never writes through a symlinked skill file;
  * a second render changes nothing (`git status --porcelain` empty).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import HAS_GIT, MANIFEST_SRC, REPO_ROOT

_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # agentskills.io name rule
_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")

_AGENTS_TPL_KEY = ".tess/core/templates/agents-md/AGENTS.md.tpl"
_CODEX_CONFIG_KEY = ".tess/core/templates/agents-md/codex-config.toml.tpl"
_COMMANDS = {
    "wake": (
        "---\ndescription: \"Session start: orient — then report\"\n---\n\n"
        "# /wake\n\nRead [the guardrails](../../conductor/guardrails.md#rule-18) "
        "and see [`/close`](close.md). Keep [external](https://example.com/x) links.\n"
    ),
    "close": (
        "---\ndescription: Session end checklist.\nargument-hint: [summary]\n---\n\n"
        "# /close\n\nClose with: **$ARGUMENTS**\n"
    ),
}


def _seed(project, manifest_overrides=None):
    project.add(None, "# AGENTS.md Fixture\n\n{{HARNESS_NOTE}}\n",
                core_key=_AGENTS_TPL_KEY, render_live=False)
    project.add(None, "HARNESS NOTE\n",
                core_key=".tess/core/templates/agents-md/harness-note.md", render_live=False)
    project.add(None, 'approval_policy = "on-request"\n',
                core_key=_CODEX_CONFIG_KEY, render_live=False)
    for name, body in _COMMANDS.items():
        project.add(f".claude/commands/{name}.md", body,
                    core_key=f".tess/core/commands/{name}.md", render_live=True)
    project.write()
    mf_path = project.root / "tess.manifest.json"
    manifest = json.loads(mf_path.read_text(encoding="utf-8"))
    manifest["render_targets"]["enabled"] = ["codex"]
    if manifest_overrides:
        manifest.update(manifest_overrides)
    mf_path.write_text(json.dumps(manifest), encoding="utf-8")


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), text[:40]
    end = text.index("\n---\n", 4)
    return yaml.safe_load(text[4:end])


def _real_commands() -> list:
    return sorted(p.stem for p in (REPO_ROOT / ".tess" / "core" / "commands").glob("*.md"))


# ---------------------------------------------------------------------------
# Synthetic project: behaviour of the CLI render
# ---------------------------------------------------------------------------

def test_render_codex_writes_one_agent_skill_per_command(project, run_cli):
    _seed(project)
    r = run_cli(project.root, "render", "--target", "codex")
    assert r.returncode == 0, r.stdout + r.stderr

    skills = sorted(p.parent.name for p in (project.root / ".agents" / "skills").glob("*/SKILL.md"))
    assert skills == ["tess-close", "tess-wake"], skills

    wake = project.read_live(".agents/skills/tess-wake/SKILL.md")
    meta = _frontmatter(wake)
    assert meta == {"name": "tess-wake", "description": "Session start: orient — then report"}
    assert "# /wake" in wake
    assert "$tess-wake" in wake

    close = project.read_live(".agents/skills/tess-close/SKILL.md")
    assert _frontmatter(close) == {"name": "tess-close", "description": "Session end checklist."}
    assert "**$ARGUMENTS**" in close
    assert "(expected: `[summary]`)" in close

    policy = yaml.safe_load(project.read_live(".agents/skills/tess-wake/agents/openai.yaml"))
    assert policy == {"policy": {"allow_implicit_invocation": False}}

    assert not (project.root / ".codex" / "prompts").exists(), (
        ".codex/prompts is retired in v0.2.0 — Codex never loads it for a project"
    )
    assert "rendered  .agents/skills/tess-*/ (2 skills)" in r.stdout


def test_skill_links_are_rebased_onto_the_skill_directory(project, run_cli):
    _seed(project)
    r = run_cli(project.root, "render", "--target", "codex")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (project.root / ".agents" / "skills" / "tess-wake" / "SKILL.md").is_file()
    wake = project.read_live(".agents/skills/tess-wake/SKILL.md")
    assert "](../../../conductor/guardrails.md#rule-18)" in wake
    assert "](../tess-close/SKILL.md)" in wake  # sibling command -> sibling skill
    assert "](https://example.com/x)" in wake
    assert "](../../conductor/" not in wake


def test_existing_codex_prompts_are_reported_as_retired_and_never_touched(project, run_cli):
    _seed(project)
    prompts = project.root / ".codex" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "wake.md").write_text("OPERATOR KEPT THIS\n", encoding="utf-8")
    (prompts / "close.md").write_text("OPERATOR KEPT THAT\n", encoding="utf-8")

    r = run_cli(project.root, "render", "--target", "codex")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (prompts / "wake.md").read_text(encoding="utf-8") == "OPERATOR KEPT THIS\n"
    assert (prompts / "close.md").read_text(encoding="utf-8") == "OPERATOR KEPT THAT\n"
    assert "retired   .codex/prompts/" in r.stdout, r.stdout
    assert "2 file(s) left in place" in r.stdout

    retired = getattr(project.mod.RENDER_TARGETS["codex"], "retired_paths", lambda _root: set())
    assert retired(project.root) == {".codex/prompts/wake.md", ".codex/prompts/close.md"}


def test_pre_v02_manifest_skips_skills_as_not_owned_and_names_the_glob(project, run_cli):
    """A v0.1.x manifest: `.agents/**` never_touch, `.codex/prompts/**`
    owned, no skills glob. The render must not fail and must not write any
    skill; it reports the skip once and names the exact glob to add. After
    the operator adds the glob, the skills render."""
    _seed(project)
    mf_path = project.root / "tess.manifest.json"
    manifest = json.loads(mf_path.read_text(encoding="utf-8"))
    manifest["owned_globs"] = [
        g for g in manifest["owned_globs"] if not g.startswith(".agents/")
    ] + [".codex/prompts/**"]
    if ".agents/**" not in manifest["never_touch"]:
        manifest["never_touch"].append(".agents/**")
    mf_path.write_text(json.dumps(manifest), encoding="utf-8")
    before = mf_path.read_bytes()

    r = run_cli(project.root, "render", "--target", "codex")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (project.root / ".agents").exists()
    assert not (project.root / ".codex" / "prompts").exists()
    assert (project.root / "AGENTS.md").exists()
    assert mf_path.read_bytes() == before
    skip_lines = [ln for ln in r.stdout.splitlines() if "not-owned" in ln]
    assert len(skip_lines) == 1, r.stdout
    assert '".agents/skills/tess-*/**"' in skip_lines[0]

    manifest["owned_globs"].append(".agents/skills/tess-*/**")
    mf_path.write_text(json.dumps(manifest), encoding="utf-8")
    r2 = run_cli(project.root, "render", "--target", "codex")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert (project.root / ".agents" / "skills" / "tess-wake" / "SKILL.md").is_file()


def test_render_never_writes_through_a_symlinked_skill_file(project, run_cli, tmp_path):
    _seed(project)
    outside = tmp_path / "outside.md"
    outside.write_text("OUTSIDE\n", encoding="utf-8")
    skill = project.root / ".agents" / "skills" / "tess-wake" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.symlink_to(outside)

    run_cli(project.root, "render", "--target", "codex")
    assert outside.read_text(encoding="utf-8") == "OUTSIDE\n"
    assert skill.is_symlink()


@pytest.mark.skipif(not HAS_GIT, reason="git not available")
def test_second_render_leaves_git_status_clean(project, run_cli):
    _seed(project)
    r = run_cli(project.root, "render", "--target", "codex")
    assert r.returncode == 0, r.stdout + r.stderr
    g = ["git", "-C", str(project.root), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(g + ["init", "-q"], check=True)
    subprocess.run(g + ["add", "-A"], check=True)
    subprocess.run(g + ["commit", "-q", "-m", "first render"], check=True)
    r2 = run_cli(project.root, "render", "--target", "codex")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    status = subprocess.run(g + ["status", "--porcelain"], capture_output=True, text=True, check=True)
    assert status.stdout == "", status.stdout
    assert (project.root / ".agents" / "skills" / "tess-wake" / "SKILL.md").is_file()


# ---------------------------------------------------------------------------
# The owned glob vs the `.agents/**` never_touch (real manifest)
# ---------------------------------------------------------------------------

def test_owned_skills_glob_beats_never_touch_for_tess_prefix_only(engine, tmp_path):
    manifest = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))
    assert ".agents/**" in manifest["never_touch"]
    shutil.copy2(MANIFEST_SRC, tmp_path / "tess.manifest.json")

    try:
        engine.check_manifest_write_gate(tmp_path, manifest, ".agents/skills/tess-wake/SKILL.md", op="render")
        tess_skill_allowed = True
    except engine.GateError:
        tess_skill_allowed = False
    assert tess_skill_allowed, "the real manifest must own .agents/skills/tess-*/**"

    for user_path in (".agents/skills/my-skill/SKILL.md", ".agents/other.md", ".agents/skills/tess.md"):
        with pytest.raises(engine.GateError):
            engine.check_manifest_write_gate(tmp_path, manifest, user_path, op="render")
    assert ".codex/prompts/**" not in manifest["owned_globs"], (
        ".codex/prompts is retired: nothing renders there, so the gate must not own it"
    )


# ---------------------------------------------------------------------------
# The real core + the committed render output in THIS repo
# ---------------------------------------------------------------------------

def test_committed_skills_match_the_real_core_one_to_one():
    commands = _real_commands()
    assert len(commands) == 26, commands
    committed = sorted(p.parent.name for p in (REPO_ROOT / ".agents" / "skills").glob("tess-*/SKILL.md"))
    assert committed == [f"tess-{c}" for c in commands]
    assert not list((REPO_ROOT / ".codex").glob("prompts/*.md")), (
        "this repo must not ship retired .codex/prompts files"
    )


@pytest.mark.parametrize("command", _real_commands())
def test_each_committed_skill_is_valid_and_matches_the_renderer(engine, command):
    rel = f".agents/skills/tess-{command}/SKILL.md"
    path = REPO_ROOT / rel
    assert path.is_file(), f"{rel} is not committed"
    text = path.read_text(encoding="utf-8")

    meta = _frontmatter(text)
    assert set(meta) == {"name", "description"}, meta
    assert meta["name"] == f"tess-{command}" == path.parent.name
    assert _SKILL_NAME_RE.match(meta["name"]) and len(meta["name"]) <= 64
    assert 0 < len(meta["description"]) <= 1024

    expected = engine.RENDER_TARGETS["codex"].expected_live_bytes(REPO_ROOT, rel)
    assert expected == path.read_bytes(), f"{rel} is stale — run `tessctl render --target codex`"

    for target in _LINK_RE.findall(text):
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith("#"):
            continue
        resolved = (path.parent / target.split("#", 1)[0]).resolve()
        assert resolved.exists(), f"{rel}: link {target!r} does not resolve"

    policy = yaml.safe_load((path.parent / "agents" / "openai.yaml").read_text(encoding="utf-8"))
    assert policy["policy"]["allow_implicit_invocation"] is False
