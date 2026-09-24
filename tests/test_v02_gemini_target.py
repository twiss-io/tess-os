"""
v0.2.0 — Gemini CLI render target (`gemini`, conformance level Partial).

What this suite pins (adapters/gemini/README.md has the doc citations):

  * Registration: `gemini` is a real, worker-profile RenderTarget whose live
    globs are inside the real manifest's owned_globs, and new installs (this
    manifest) enable it.
  * `tessctl render --target gemini` writes AGENTS.md, GEMINI.md (a header
    plus the `@./AGENTS.md` import) and one `.gemini/commands/tess/<name>.toml`
    per core command. It never writes `.gemini/settings.json` or
    `.gemini/policies/**`.
  * Every TOML parses (tomllib, Python 3.11+) with a non-empty `description`
    and `prompt`; the prompt round-trips the command body, `$ARGUMENTS`
    becomes `{{args}}`, and hostile bodies (quote runs, backslashes, control
    characters, `!{...}` shell and `@{...}` file triggers) can neither break
    the TOML nor smuggle an injection trigger into Gemini.
  * The target is deterministic and idempotent; doctor/verify/lock --check
    drift-check its outputs; the manifest write gate still applies; it does
    not write through a symlink.
  * The REAL repo: 26 committed `.gemini/commands/tess/*.toml` + GEMINI.md
    match a fresh render byte for byte, and the rendered AGENTS.md carries no
    token that Gemini's memory-import processor would treat as an import.

The CLI tests fail on 5c2d698 (the engine before this target existed):
`render --target gemini` exits "unknown target(s): gemini" there.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

from conftest import MANIFEST_SRC, REPO_ROOT

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - exercised on the 3.9 CI leg
    tomllib = None

needs_tomllib = pytest.mark.skipif(tomllib is None, reason="tomllib needs Python 3.11+")


# ---------------------------------------------------------------------------
# Synthetic fixture (same shape as test_render_targets_codex_generic.py)
# ---------------------------------------------------------------------------

_AGENTS_TPL_KEY = ".tess/core/templates/agents-md/AGENTS.md.tpl"
_AGENTS_TPL = "# AGENTS.md Fixture\n\n{{WORKER_HARD_FLOOR}}\n"
_HARD_FLOOR_KEY = ".tess/core/templates/agents-md/worker-hard-floor.md"
_GEMINI_TPL_KEY = ".tess/core/templates/gemini/GEMINI.md.tpl"

_COMMANDS = {
    "wake": "---\ndescription: Session start checklist V1\n---\n\n# /wake\n\nDo the wake thing.\n",
    "add-mission": (
        "---\ndescription: Start a mission — intake first\nargument-hint: [brief]\n---\n\n"
        "# /add-mission\n\nStart a new mission with the brief: **$ARGUMENTS**\n\n"
        "See [conductor/doctrine.md](../../conductor/doctrine.md).\n"
    ),
}


def _real_gemini_tpl() -> str:
    return (REPO_ROOT / _GEMINI_TPL_KEY).read_text(encoding="utf-8")


def _seed(project, commands=None):
    commands = _COMMANDS if commands is None else commands
    project.add(None, _AGENTS_TPL, core_key=_AGENTS_TPL_KEY, render_live=False)
    project.add(None, "HARD FLOOR FIXTURE\n", core_key=_HARD_FLOOR_KEY, render_live=False)
    project.add(None, _real_gemini_tpl(), core_key=_GEMINI_TPL_KEY, render_live=False)
    for name, body in commands.items():
        project.add(
            f".claude/commands/{name}.md", body,
            core_key=f".tess/core/commands/{name}.md", render_live=True,
        )


def _set_enabled(project, names):
    mf_path = project.root / "tess.manifest.json"
    manifest = json.loads(mf_path.read_text(encoding="utf-8"))
    manifest.setdefault("render_targets", {})["enabled"] = list(names)
    mf_path.write_text(json.dumps(manifest), encoding="utf-8")


def _toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


# Port of Gemini CLI 0.61.0's memory-import scanner (memoryImportProcessor.ts
# findImports + findCodeRegions): an `@` at the start or after whitespace,
# followed by a path starting with `.`, `/` or an ASCII letter, outside a
# backtick code span, is imported as a file.
_CODE_SPAN = re.compile(r"(`+)([\s\S]*?)\1")


def _gemini_import_tokens(text: str) -> list:
    regions = [(m.start(), m.end()) for m in _CODE_SPAN.finditer(text)]
    found = []
    i = 0
    while True:
        i = text.find("@", i)
        if i == -1:
            return found
        if i > 0 and text[i - 1] not in " \t\n\r":
            i += 1
            continue
        j = i + 1
        while j < len(text) and text[j] not in " \t\n\r":
            j += 1
        path = text[i + 1:j]
        if path and (path[0] in "./" or ("A" <= path[0] <= "Z") or ("a" <= path[0] <= "z")):
            if not any(s <= i < e for s, e in regions):
                found.append(path)
        i = j + 1


# ---------------------------------------------------------------------------
# Registration and manifest
# ---------------------------------------------------------------------------

def test_gemini_is_a_registered_worker_target(engine):
    target = engine.RENDER_TARGETS["gemini"]
    assert isinstance(target, engine.RenderTarget)
    assert target.name == "gemini"
    assert target.doctrine_profile == "worker"
    assert target.doctrine_digest_paths(Path("/nonexistent")) == {"AGENTS.md", "GEMINI.md"}
    assert target.live_globs() == ["AGENTS.md", "GEMINI.md", ".gemini/commands/tess/**"]


def test_live_globs_are_inside_the_real_manifest_owned_globs(engine):
    manifest = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))
    owned = manifest["owned_globs"]
    for live_glob in engine.RENDER_TARGETS["gemini"].live_globs():
        assert engine.path_matches_globs(live_glob, owned), live_glob
    # The namespace keeps an operator's own commands and settings out of reach.
    for foreign in (".gemini/settings.json", ".gemini/commands/mine.toml",
                    ".gemini/policies/tess.toml", ".gemini/commands/git/commit.toml"):
        assert not engine.path_matches_globs(foreign, owned), foreign


def test_new_installs_enable_gemini(engine):
    manifest = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))
    assert "gemini" in manifest["render_targets"]["enabled"]


# ---------------------------------------------------------------------------
# CLI render (behavioural; fails on 5c2d698: unknown target)
# ---------------------------------------------------------------------------

def test_cli_render_target_gemini_writes_context_and_commands(project, run_cli):
    _seed(project)
    project.write()
    r = run_cli(project.root, "render", "--target", "gemini")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "unknown target" not in (r.stdout + r.stderr)

    gemini_md = project.read_live("GEMINI.md")
    assert gemini_md.rstrip().endswith("@./AGENTS.md")
    assert "HARD FLOOR FIXTURE" in project.read_live("AGENTS.md")

    cmd_dir = project.root / ".gemini" / "commands" / "tess"
    assert sorted(p.name for p in cmd_dir.iterdir()) == ["add-mission.toml", "wake.toml"]
    wake = (cmd_dir / "wake.toml").read_text(encoding="utf-8")
    assert 'description = "Session start checklist V1"' in wake
    assert "Do the wake thing." in wake

    assert not (project.root / ".gemini" / "settings.json").exists()
    assert not (project.root / ".gemini" / "policies").exists()
    assert not (project.root / ".codex").exists()


def test_cli_render_gemini_is_idempotent_and_doctor_clean(project, run_cli):
    _seed(project)
    project.write()
    _set_enabled(project, ["gemini"])
    r1 = run_cli(project.root, "render")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    snap = {p: p.read_bytes() for p in (project.root / ".gemini").rglob("*") if p.is_file()}
    snap[project.root / "GEMINI.md"] = (project.root / "GEMINI.md").read_bytes()
    r2 = run_cli(project.root, "render")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "written" not in r2.stdout.replace("0 written", "")
    for path, data in snap.items():
        assert path.read_bytes() == data, path

    for verb in (("doctor",), ("verify",), ("lock", "--check")):
        res = run_cli(project.root, *verb)
        assert res.returncode == 0, f"{verb} not clean:\n{res.stdout}\n{res.stderr}"


def test_verify_and_lock_check_flag_a_stale_gemini_command(project, run_cli):
    _seed(project)
    project.write()
    _set_enabled(project, ["gemini"])
    assert run_cli(project.root, "render").returncode == 0
    (project.root / ".gemini/commands/tess/wake.toml").write_text(
        'description = "x"\nprompt = "HAND EDITED"\n', encoding="utf-8"
    )
    d = run_cli(project.root, "doctor")
    assert d.returncode == 1 and ".gemini/commands/tess/wake.toml" in d.stdout
    assert "tessctl render" in d.stdout
    v = run_cli(project.root, "verify")
    assert v.returncode == 1 and ".gemini/commands/tess/wake.toml" in v.stdout
    lc = run_cli(project.root, "lock", "--check")
    assert lc.returncode == 1 and ".gemini/commands/tess/wake.toml" in lc.stdout


def test_doctor_flags_a_deleted_gemini_md(project, run_cli):
    _seed(project)
    project.write()
    _set_enabled(project, ["gemini"])
    assert run_cli(project.root, "render").returncode == 0
    (project.root / "GEMINI.md").unlink()
    d = run_cli(project.root, "doctor")
    assert d.returncode == 1, d.stdout
    assert "GEMINI.md" in d.stdout


# ---------------------------------------------------------------------------
# TOML shape and escaping
# ---------------------------------------------------------------------------

@needs_tomllib
def test_rendered_toml_parses_and_round_trips_the_body(engine, project):
    _seed(project)
    project.write()
    data = engine.render_gemini_command_toml(project.root, "add-mission")
    parsed = tomllib.loads(data.decode("utf-8"))
    assert set(parsed) == {"description", "prompt"}
    assert parsed["description"] == "Start a mission — intake first"
    assert parsed["prompt"] == (
        "# /add-mission\n\nStart a new mission with the brief: **{{args}}**\n\n"
        "See [conductor/doctrine.md](conductor/doctrine.md).\n"
    )
    assert "$ARGUMENTS" not in parsed["prompt"]


_HOSTILE = {
    "triple-single": "Body with ''' inside and a closing quote'",
    "triple-double": 'Body with """ and a \\ backslash and "quotes"',
    "trailing-quote": "ends with a quote '",
    "two-quotes": "ends with two ''",
    "control": "bell \x07 and escape \x1b and del \x7f",
    "injection": "run !{rm -rf /} and read @{secrets.txt} and @$ARGUMENTS",
    "unicode": "em dash — and emoji \U0001f600 and tab\tend",
}


@needs_tomllib
@pytest.mark.parametrize("case", sorted(_HOSTILE))
def test_hostile_bodies_stay_valid_toml_without_injection_triggers(engine, project, case):
    body = _HOSTILE[case]
    _seed(project, {"hostile": f'---\ndescription: "Desc with \\"quotes\\" and \\\\ slash"\n---\n\n{body}\n'})
    project.write()
    data = engine.render_gemini_command_toml(project.root, "hostile")
    parsed = tomllib.loads(data.decode("utf-8"))
    assert parsed["description"] == 'Desc with "quotes" and \\ slash'
    prompt = parsed["prompt"]
    assert "!{" not in prompt and "@{" not in prompt
    expected = body.replace("$ARGUMENTS", "{{args}}").replace("!{", "! {").replace("@{", "@ {")
    assert prompt == expected + "\n"


def test_missing_description_gets_a_non_empty_fallback(engine, project):
    _seed(project, {"bare": "# /bare\n\nNo frontmatter here.\n"})
    project.write()
    text = engine.render_gemini_command_toml(project.root, "bare").decode("utf-8")
    assert 'description = "Tess /bare command"' in text
    assert "No frontmatter here." in text


def test_expected_live_bytes_match_what_render_writes(engine, project):
    _seed(project)
    project.write()
    _set_enabled(project, ["gemini"])
    target = engine.RENDER_TARGETS["gemini"]
    target.render(project.root, verbose=False)
    paths = target.render_generated_paths(project.root)
    assert paths == {"AGENTS.md", "GEMINI.md",
                     ".gemini/commands/tess/wake.toml", ".gemini/commands/tess/add-mission.toml"}
    for rel in paths:
        assert target.expected_live_bytes(project.root, rel) == (project.root / rel).read_bytes(), rel
    assert target.expected_live_bytes(project.root, ".gemini/settings.json") is None
    assert target.expected_live_bytes(project.root, ".gemini/commands/tess/x/y.toml") is None
    assert target.expected_live_bytes(project.root, ".codex/config.toml") is None
    assert target.retired_paths(project.root) == set()


def test_agents_md_is_shared_byte_for_byte_with_codex(engine, project):
    _seed(project)
    project.write()
    assert (
        engine.RENDER_TARGETS["gemini"].expected_live_bytes(project.root, "AGENTS.md")
        == engine.RENDER_TARGETS["codex"].expected_live_bytes(project.root, "AGENTS.md")
    )


# ---------------------------------------------------------------------------
# Write gate and symlinks
# ---------------------------------------------------------------------------

def test_gemini_render_honours_the_manifest_write_gate(engine, project):
    _seed(project)
    project.write()
    mf_path = project.root / "tess.manifest.json"
    manifest = json.loads(mf_path.read_text(encoding="utf-8"))
    manifest["owned_globs"] = [g for g in manifest["owned_globs"] if g != "GEMINI.md"]
    mf_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(engine.GateError):
        engine.RENDER_TARGETS["gemini"].render(project.root, verbose=False)
    assert not (project.root / "GEMINI.md").exists()


def test_render_never_writes_through_a_symlinked_commands_dir(engine, project, tmp_path):
    _seed(project)
    project.write()
    outside = tmp_path / "outside"
    outside.mkdir()
    (project.root / ".gemini" / "commands").mkdir(parents=True)
    os.symlink(outside, project.root / ".gemini" / "commands" / "tess")
    engine.RENDER_TARGETS["gemini"].render(project.root, verbose=False)
    assert list(outside.iterdir()) == []


# ---------------------------------------------------------------------------
# The real repository
# ---------------------------------------------------------------------------

def test_real_repo_gemini_outputs_are_freshly_rendered(engine):
    target = engine.RENDER_TARGETS["gemini"]
    paths = target.render_generated_paths(REPO_ROOT)
    commands = sorted(p for p in paths if p.startswith(".gemini/commands/tess/"))
    assert len(commands) == 26
    committed = sorted(
        str(p.relative_to(REPO_ROOT)) for p in (REPO_ROOT / ".gemini").rglob("*") if p.is_file()
    )
    assert committed == commands, "only the 26 tess commands may live under .gemini/"
    for rel in sorted(paths):
        assert (REPO_ROOT / rel).read_bytes() == target.expected_live_bytes(REPO_ROOT, rel), (
            f"{rel} is stale: run `tessctl render --target gemini`"
        )


@needs_tomllib
def test_real_repo_commands_parse_with_description_and_prompt(engine):
    for path in sorted((REPO_ROOT / ".gemini" / "commands" / "tess").glob("*.toml")):
        parsed = _toml(path)
        assert set(parsed) == {"description", "prompt"}, path.name
        assert parsed["description"].strip(), path.name
        assert parsed["prompt"].strip(), path.name
        assert "!{" not in parsed["prompt"] and "@{" not in parsed["prompt"], path.name


def test_real_gemini_md_has_exactly_one_import_and_agents_md_has_none(engine):
    gemini_md = engine.render_gemini_md(REPO_ROOT)
    assert _gemini_import_tokens(gemini_md) == ["./AGENTS.md"]
    agents_md = engine.render_agents_md(REPO_ROOT)
    assert _gemini_import_tokens(agents_md) == [], (
        "AGENTS.md contains an `@path` token that Gemini CLI's import processor "
        "would try to inline as a file"
    )


def test_import_scanner_port_matches_gemini_rules():
    assert _gemini_import_tokens("x @./a.md y") == ["./a.md"]
    assert _gemini_import_tokens("mail a@b.md") == []
    assert _gemini_import_tokens("`@./code.md`") == []
    assert _gemini_import_tokens("@1abc @_x") == []


def test_real_worker_denylist_is_clean_for_gemini(engine):
    hits = [v for v in engine._check_worker_profile_denylist(REPO_ROOT) if v["target"] == "gemini"]
    assert hits == []
