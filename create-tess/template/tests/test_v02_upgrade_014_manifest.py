"""
v0.2 engine safety B — upgrading a v0.1.x install (challenge must_fix #2).

Nothing in `tessctl update` writes tess.manifest.json, and the write gate is
an allowlist. A create-tess 0.1.4 scaffold ships a manifest with codex
enabled, `.agents/**` in never_touch and `.codex/prompts/**` owned
(tests/fixtures/manifest_0_1_4.json is that file, byte-for-byte, from
create-tess/template/tess.manifest.json at commit 22d69eb). The v0.2 codex
target renders `.agents/skills/tess-*/SKILL.md`, which that manifest does not
own. The engine must NOT widen the gate or edit the manifest: the outputs are
skipped ('skipped:not-owned'), render exits 0, and ONE line names the glob
the operator can add. Retired outputs are reported, never deleted.

The codex-specific assertions switch on when the codex target declares the
skills glob (ws-rt's target); until then the same mechanism is proven with a
stub target. The v0.1.x update-gate test fails on 5c2d698 by assertion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import ns
from test_v02_render_outputs import build, render

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "manifest_0_1_4.json"
SKILLS_GLOB = ".agents/skills/tess-*/**"


@pytest.fixture(autouse=True)
def _tess_root_env(monkeypatch):
    monkeypatch.delenv("TESS_ROOT", raising=False)
    yield


def use_014_manifest(root: Path, *, extra_owned=()):
    manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))
    manifest["owned_globs"] = list(manifest["owned_globs"]) + list(extra_owned)
    data = FIXTURE.read_bytes() if not extra_owned else \
        (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    (root / "tess.manifest.json").write_bytes(data)
    return data


def lines_naming(out: str, needle: str) -> list:
    return [ln for ln in out.splitlines() if needle in ln]


def test_fixture_is_the_0_1_4_manifest_shape():
    m = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert ".agents/**" in m["never_touch"]
    assert ".codex/prompts/**" in m["owned_globs"]
    assert SKILLS_GLOB not in m["owned_globs"]
    assert m["render_targets"]["enabled"] == ["claude-code", "codex"]


def test_codex_render_on_014_manifest_exits_zero_and_never_writes_the_manifest(
        project, engine, capsys):
    root = build(project, codex=True)
    mf_bytes = use_014_manifest(root)
    # the v0.1.4 install's previous codex render left .codex/prompts behind
    old_prompt = engine._render_command_prompt_bytes(root, "wake")
    (root / ".codex" / "prompts").mkdir(parents=True, exist_ok=True)
    (root / ".codex" / "prompts" / "wake.md").write_bytes(old_prompt)
    capsys.readouterr()

    render(engine, root)                                   # must not raise / exit
    out = capsys.readouterr().out

    assert (root / "tess.manifest.json").read_bytes() == mf_bytes, "render wrote the manifest"
    assert (root / "AGENTS.md").exists() and (root / ".codex" / "config.toml").exists()
    assert (root / ".codex" / "prompts" / "wake.md").read_bytes() == old_prompt


def test_codex_skills_on_014_manifest_are_skipped_and_named(project, engine, capsys):
    codex = engine.RENDER_TARGETS["codex"]
    if SKILLS_GLOB not in codex.live_globs():
        pytest.skip("codex target does not render .agents/skills on this branch (ws-rt adds it); "
                    "the mechanism is proven by the stub-target test")
    root = build(project, codex=True)
    use_014_manifest(root)
    old_prompt = engine._render_command_prompt_bytes(root, "wake") or b"old prompt\n"
    (root / ".codex" / "prompts").mkdir(parents=True, exist_ok=True)
    (root / ".codex" / "prompts" / "wake.md").write_bytes(old_prompt)
    capsys.readouterr()

    render(engine, root)
    out = capsys.readouterr().out

    assert (root / ".codex" / "prompts" / "wake.md").read_bytes() == old_prompt, \
        "a retired output must be reported, never deleted or rewritten"
    skills = sorted(p for p in codex.render_generated_paths(root) if p.startswith(".agents/"))
    assert skills and not any((root / p).exists() for p in skills)
    assert len(lines_naming(out, SKILLS_GLOB)) == 1, out
    assert "retired" in out.lower()

    use_014_manifest(root, extra_owned=[SKILLS_GLOB])
    render(engine, root)
    assert all((root / p).is_file() for p in skills)


def test_not_owned_outputs_are_skipped_and_the_glob_is_named_once(project, engine, capsys,
                                                                   monkeypatch):
    class StubSkillsTarget(engine.RenderTarget):
        name = "stub-skills"
        doctrine_profile = "worker"
        outputs = {
            ".agents/skills/tess-wake/SKILL.md": b"---\nname: tess-wake\n---\nwake\n",
            ".agents/skills/tess-close/SKILL.md": b"---\nname: tess-close\n---\nclose\n",
            ".agents/skills/tess-help/SKILL.md": b"---\nname: tess-help\n---\nhelp\n",
        }

        def live_globs(self):
            return [SKILLS_GLOB]

        def render(self, root, verbose=False):
            self.results = engine.write_render_outputs(root, self.name, self.outputs,
                                                       verbose=verbose)
            return {"target": self.name, "status": "rendered"}

        def render_generated_paths(self, root):
            return set(self.outputs)

    stub = StubSkillsTarget()
    monkeypatch.setitem(engine.RENDER_TARGETS, "stub-skills", stub)
    root = build(project)
    mf_bytes = use_014_manifest(root)
    capsys.readouterr()

    engine.cmd_render(ns(target=["stub-skills"], list_targets=False), root)
    out = capsys.readouterr().out

    assert set(stub.results.values()) == {"skipped:not-owned"}
    assert not (root / ".agents").exists()
    assert (root / "tess.manifest.json").read_bytes() == mf_bytes
    named = lines_naming(out, SKILLS_GLOB)
    assert len(named) == 1 and "3 output(s)" in named[0], out

    # the operator adds the glob; owned_globs outranks never_touch '.agents/**'
    use_014_manifest(root, extra_owned=[SKILLS_GLOB])
    engine.cmd_render(ns(target=["stub-skills"], list_targets=False), root)
    assert set(stub.results.values()) == {"written"}
    for rel, data in stub.outputs.items():
        assert (root / rel).read_bytes() == data


def test_v01x_update_gate_blocks_a_hand_edited_render_output(project, engine, capsys):
    """A v0.1.x lock (no render_outputs) whose CLAUDE.md was hand-edited: the
    Step 1 gate seeds records for the matching outputs and BLOCKS on the hand
    edit instead of letting Step 7 overwrite it."""
    project.framework["version"] = "0.1.4"
    root = build(project)
    project.write_live("CLAUDE.md", project.read_live("CLAUDE.md") + "\n## My section\n")
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc:
        engine.cmd_update(ns(dry_run=True, check=False, to=None), root)
    out = capsys.readouterr().out

    assert exc.value.code not in (0, None)
    assert "hand-edited render output" in out
    assert "CLAUDE.md" in out
    assert "render_outputs" not in engine.load_lock(root), "a dry-run gate must not write the lock"


def test_v01x_update_gate_passes_a_pristine_install(project, engine, capsys):
    project.framework["version"] = "0.1.4"
    root = build(project)
    capsys.readouterr()
    try:
        engine.cmd_update(ns(dry_run=True, check=False, to=None), root)
    except SystemExit:
        pass   # a dry run may stop later (no upstream configured) — only the gate matters here
    out = capsys.readouterr().out
    assert "doctor gate: PASS" in out
    assert "BLOCKED" not in out
