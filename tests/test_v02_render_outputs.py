"""
v0.2 engine safety B — render-output protection (bug 7) and the render
record every write goes through (`tess.lock` `render_outputs`).

Behavioural regression tests (each fails on 5c2d698 by assertion, not by a
missing helper):

  * a captured (locally-modified) CLAUDE.md survives `tessctl render`;
  * `doctor --fix` keeps a hand edit to `.codex/config.toml`, exits non-zero
    and names it a hand-edited render output;
  * with `AGENTS.md -> CLAUDE.md` symlinked and codex enabled, `render` no
    longer writes the worker AGENTS.md digest into CLAUDE.md;
  * a hand-edited CLAUDE.md survives both `render` and `restore`;
  * a v0.1.1-shaped lock (no render_outputs) loads and the first render
    seeds records without rewriting a hand-edited AGENTS.md.

Non-regression guards (pass on 5c2d698 too, and must keep passing): a stale
render is still rewritten (CLAUDE.md.local.md flow) and a profile change on a
lock with no records (the create-tess bake path) still re-renders.

Interface tests exercise write_render_output() directly (they do not exist on
5c2d698 and are not counted as proof).
"""

from __future__ import annotations

import json
import os

import pytest

from conftest import REPO_ROOT, ns


TPL = (
    "# Tess OS Fixture\n"
    "\n"
    "Root: {{TESS_ROOT}}\n"
    "Operator: {{OPERATOR_NAME}}\n"
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
TPL_KEY = ".tess/core/templates/CLAUDE.md.tpl"
FRAGMENTS = {
    ".tess/core/templates/claude-md/rule-zero.md": "RULE ZERO FIXTURE — always dispatch.\n",
    ".tess/core/templates/claude-md/system-laws.md": "System laws fixture.\n",
    ".tess/core/templates/claude-md/orchestrators.md": "Orchestrators fixture.\n",
    ".tess/core/templates/claude-md/commands.md": "Commands fixture.\n",
    ".tess/core/templates/claude-md/directory.md": "Directory fixture.\n",
}
SETTINGS_KEY = ".tess/core/settings-core.json"
SETTINGS = '{"root": "{{TESS_ROOT}}", "feature_flag": "fixture"}\n'

AGENTS_TPL = (
    "# AGENTS.md Fixture\n"
    "\n"
    "{{WORKER_HARD_FLOOR}}\n"
    "\n"
    "{{WORKER_GATE_COMPLIANCE}}\n"
    "\n"
    "{{HARNESS_NOTE}}\n"
)
AGENTS_TPL_KEY = ".tess/core/templates/agents-md/AGENTS.md.tpl"
AGENTS_FRAGMENTS = {
    ".tess/core/templates/agents-md/worker-hard-floor.md": "HARD FLOOR FIXTURE\n",
    ".tess/core/templates/agents-md/gate-compliance.md": "GATE COMPLIANCE FIXTURE\n",
    ".tess/core/templates/agents-md/harness-note.md": "HARNESS NOTE FIXTURE\n",
}
CODEX_CONFIG_KEY = ".tess/core/templates/agents-md/codex-config.toml.tpl"
CODEX_CONFIG = 'approval_policy = "on-request"\nsandbox_mode = "workspace-write"\n'
COMMANDS = {
    "wake": "---\ndescription: wake fixture\n---\n\n# /wake\n\nWake.\n",
    "close": "---\ndescription: close fixture\n---\n\n# /close\n\nClose.\n",
}


# ---------------------------------------------------------------------------
# fixture builders
# ---------------------------------------------------------------------------

def seed_claude(project, *, security_fragment=None, fragment_status=None):
    """CLAUDE.md = .tpl + 5 fragments (6 lock entries sharing one live_path),
    plus settings-core -> .claude/settings.json. Live files are written as a
    prior render would have left them."""
    project.add("CLAUDE.md", TPL, core_key=TPL_KEY, render_live=False)
    for core_key, content in FRAGMENTS.items():
        extra = {}
        if security_fragment == core_key:
            extra["tier"] = "security"
        status = (fragment_status or {}).get(core_key, "core-managed")
        project.add("CLAUDE.md", content, core_key=core_key, render_live=False,
                    status=status, **extra)
    project.add(".claude/settings.json", SETTINGS, core_key=SETTINGS_KEY, render_live=False)


def render_claude_live(project):
    mod = project.mod
    project.write_live("CLAUDE.md", mod.render_claude_md(project.root))
    project.write_live(".claude/settings.json", mod.render_settings_json(project.root))


def seed_agents(project):
    project.add(None, AGENTS_TPL, core_key=AGENTS_TPL_KEY, render_live=False)
    for core_key, content in AGENTS_FRAGMENTS.items():
        project.add(None, content, core_key=core_key, render_live=False)
    project.add(None, CODEX_CONFIG, core_key=CODEX_CONFIG_KEY, render_live=False)
    for name, body in COMMANDS.items():
        project.add(f".claude/commands/{name}.md", body,
                    core_key=f".tess/core/commands/{name}.md", render_live=True)


def set_enabled(project, names):
    mf = project.root / "tess.manifest.json"
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest.setdefault("render_targets", {})["enabled"] = list(names)
    mf.write_text(json.dumps(manifest), encoding="utf-8")


def build(project, *, codex=False, **claude_kw):
    seed_claude(project, **claude_kw)
    if codex:
        seed_agents(project)
    project.write()
    if codex:
        set_enabled(project, ["claude-code", "codex"])
    render_claude_live(project)
    return project.root


def render(engine, root):
    engine.cmd_render(ns(target=None, list_targets=False), root)


@pytest.fixture(autouse=True)
def _tess_root_env(monkeypatch):
    monkeypatch.delenv("TESS_ROOT", raising=False)
    yield


# ---------------------------------------------------------------------------
# Bug 7 — behavioural regressions
# ---------------------------------------------------------------------------

def test_captured_claude_md_survives_render(project, engine):
    root = build(project)
    edited = project.read_live("CLAUDE.md") + "\nMY CAPTURED EDIT\n"
    project.write_live("CLAUDE.md", edited)

    engine.cmd_capture(ns(path="CLAUDE.md", all=False, dry_run=False,
                          rationale="", source="manual"), root)
    render(engine, root)

    assert project.read_live("CLAUDE.md") == edited, \
        "render re-rendered a captured (locally-modified) CLAUDE.md"


def test_doctor_fix_keeps_hand_edited_codex_config(project, engine, capsys):
    root = build(project, codex=True)
    render(engine, root)                      # a real render: records rendered_sha
    cfg = root / ".codex" / "config.toml"
    assert cfg.exists()
    edited = cfg.read_text(encoding="utf-8") + '\n[mcp_servers.local]\ncommand = "x"\n'
    cfg.write_text(edited, encoding="utf-8")
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc:
        engine.cmd_doctor(ns(fix=True, json_out=False, path=None), root)
    out = capsys.readouterr().out

    assert exc.value.code not in (0, None), "doctor --fix exited 0 over a hand-edited render output"
    assert cfg.read_text(encoding="utf-8") == edited, "doctor --fix destroyed the hand edit"
    assert "hand-edited render output" in out


def test_symlinked_agents_md_never_clobbers_claude_md(project, engine, capsys):
    root = build(project, codex=True)
    agents = root / "AGENTS.md"
    if agents.exists() or agents.is_symlink():
        agents.unlink()
    os.symlink("CLAUDE.md", agents)
    capsys.readouterr()

    render(engine, root)
    out = capsys.readouterr().out

    claude = (root / "CLAUDE.md").read_bytes()
    assert not claude.startswith(b"# AGENTS.md"), "codex wrote AGENTS.md through the symlink into CLAUDE.md"
    assert claude == engine.render_claude_md(root).encode("utf-8")
    assert agents.is_symlink()
    assert "AGENTS.md" in out and "symlink" in out


def test_hand_edited_claude_md_survives_render_and_restore(project, engine, capsys):
    root = build(project)
    render(engine, root)                      # records CLAUDE.md's rendered_sha
    edited = project.read_live("CLAUDE.md") + "\nHAND EDIT — keep me\n"
    project.write_live("CLAUDE.md", edited)
    capsys.readouterr()

    render(engine, root)
    assert project.read_live("CLAUDE.md") == edited, "render destroyed a hand edit"
    assert "hand-edited render output" in capsys.readouterr().out

    engine.cmd_restore(ns(dry_run=False), root)
    assert project.read_live("CLAUDE.md") == edited, "restore destroyed a hand edit"


def test_v011_lock_first_render_seeds_records_and_keeps_hand_edited_agents_md(project, engine):
    project.framework["version"] = "0.1.1"
    project.framework["upstream_ref"] = "v0.1.1"
    root = build(project, codex=True)
    mod = project.mod
    # The v0.1.x install's previous render, then a hand edit to AGENTS.md.
    agents_edited = mod.render_agents_md(root) + "\n## My own worker notes\n"
    project.write_live("AGENTS.md", agents_edited)
    project.write_live(".codex/config.toml", mod.render_codex_config_toml(root))
    lock_before = engine.load_lock(root)
    assert "render_outputs" not in lock_before      # v0.1.1 shape
    assert lock_before["framework"]["version"] == "0.1.1"

    render(engine, root)

    assert project.read_live("AGENTS.md") == agents_edited, "first render rewrote a hand-edited AGENTS.md"
    lock = engine.load_lock(root)
    records = lock.get("render_outputs") or {}
    assert records.get("CLAUDE.md", {}).get("rendered_sha") == mod.sha256_file(root / "CLAUDE.md")
    assert records.get(".codex/config.toml", {}).get("rendered_sha") == \
        mod.sha256_file(root / ".codex" / "config.toml")
    assert "AGENTS.md" not in records, "a hand edit must not be blessed as a render"


# ---------------------------------------------------------------------------
# Non-regression: stale renders are still re-rendered
# ---------------------------------------------------------------------------

def test_stale_render_is_rewritten_local_md_flow(project, engine):
    """The documented home for a CLAUDE.md edit (CLAUDE.md.local.md) keeps
    working: CLAUDE.md is a stale render, so render rewrites it."""
    root = build(project)
    render(engine, root)
    (root / "CLAUDE.md.local.md").write_text("LOCAL SHADOW NOTE\n", encoding="utf-8")

    render(engine, root)

    assert "LOCAL SHADOW NOTE" in project.read_live("CLAUDE.md")
    assert project.read_live("CLAUDE.md") == engine.render_claude_md(root)


def test_profile_change_on_lock_without_records_still_rerenders(project, run_cli):
    """create-tess bake path: a lock with no render_outputs, then
    `set-operator` — the profile save seeds records first, so the rename is
    rendered rather than kept as a 'hand edit'."""
    root = build(project)
    assert "render_outputs" not in project.lock()

    r = run_cli(root, "set-operator", "--", "Alex Rivera")
    assert r.returncode == 0, r.stdout + r.stderr

    assert "Operator: Alex Rivera" in project.read_live("CLAUDE.md")
    d = run_cli(root, "doctor")
    assert d.returncode == 0, d.stdout + d.stderr


# ---------------------------------------------------------------------------
# Interface: write_render_output
# ---------------------------------------------------------------------------

def test_write_render_output_results(project, engine):
    root = build(project)
    w = engine.write_render_output
    data = engine.render_claude_md(root).encode("utf-8")

    assert w(root, "CLAUDE.md", data, "claude-code") == "unchanged"
    rec = engine.render_output_record(engine.load_lock(root), "CLAUDE.md")
    assert rec == {"target": "claude-code", "status": "rendered",
                   "rendered_sha": engine.sha256_bytes(data)}

    # stale render -> written
    (root / "CLAUDE.md").write_bytes(data)
    assert w(root, "CLAUDE.md", data + b"new\n", "claude-code") == "written"
    assert (root / "CLAUDE.md").read_bytes() == data + b"new\n"

    # hand edit -> kept; force -> written (pre-image snapshotted)
    (root / "CLAUDE.md").write_bytes(data + b"new\nhand\n")
    assert w(root, "CLAUDE.md", data, "claude-code") == "skipped:hand-edited"
    assert (root / "CLAUDE.md").read_bytes() == data + b"new\nhand\n"
    assert w(root, "CLAUDE.md", data, "claude-code", force=True) == "written"
    snaps = list((root / ".tess" / "snapshots").rglob("CLAUDE.md"))
    assert any(p.read_bytes() == data + b"new\nhand\n" for p in snaps)

    # not owned -> skipped, never raises, manifest untouched
    mf_before = (root / "tess.manifest.json").read_bytes()
    assert w(root, "not-owned/output.md", b"x", "codex") == "skipped:not-owned"
    assert not (root / "not-owned").exists()
    assert (root / "tess.manifest.json").read_bytes() == mf_before

    # symlink final component -> skipped, target untouched
    (root / "AGENTS.md").symlink_to("CLAUDE.md")
    before = (root / "CLAUDE.md").read_bytes()
    assert w(root, "AGENTS.md", b"worker digest", "codex") == "skipped:symlink"
    assert (root / "CLAUDE.md").read_bytes() == before


def test_write_render_output_status_and_foreign(project, engine):
    root = build(project, codex=True)
    render(engine, root)                                  # lock now tracks render outputs
    lock = engine.load_lock(root)
    assert "render_outputs" in lock

    # a file Tess never wrote, on a lock that tracks render outputs -> foreign
    (root / "prompts").mkdir(exist_ok=True)
    (root / "prompts" / "wake.md").write_text("my own prompt\n", encoding="utf-8")
    assert engine.write_render_output(root, "prompts/wake.md", b"tess prompt\n", "generic") \
        == "skipped:foreign"

    # explicit statuses win, force never overrides them
    for status in ("user-published", "locally-modified", "held", "foreign"):
        lock = engine.load_lock(root)
        lock["render_outputs"][".codex/config.toml"]["status"] = status
        engine.save_lock(root, lock)
        assert engine.write_render_output(root, ".codex/config.toml", b"x\n", "codex",
                                          force=True) == f"skipped:{status}"
    assert engine.render_output_status(engine.load_lock(root), ".codex/config.toml") == "foreign"


def test_publish_render_output_without_lock_entry(project, engine, capsys):
    """`tessctl publish AGENTS.md` (no tess.lock entry) keeps the edited file
    and records user-published, so render stops writing it."""
    root = build(project, codex=True)
    render(engine, root)
    edited = project.read_live("AGENTS.md") + "\nMine now.\n"
    project.write_live("AGENTS.md", edited)

    engine.cmd_publish(ns(path="AGENTS.md", tag=None, force=False), root)
    render(engine, root)

    assert project.read_live("AGENTS.md") == edited
    assert engine.render_output_status(engine.load_lock(root), "AGENTS.md") == "user-published"


def test_render_is_idempotent_on_the_lock(project, engine):
    root = build(project, codex=True)
    render(engine, root)
    lock1 = (root / ".tess" / "tess.lock").read_bytes()
    render(engine, root)
    assert (root / ".tess" / "tess.lock").read_bytes() == lock1


def test_repo_lock_render_records_match_committed_files():
    """The shipped lock's render_outputs (copied into every create-tess
    scaffold) must describe the committed render outputs byte-for-byte:
    otherwise a fresh install would treat its own rendered files as hand
    edits on the first rename. Re-run `tessctl render` after changing any
    render input, and commit the lock with the outputs."""
    import yaml  # noqa: PLC0415 — engine dependency, always present in CI

    lock = yaml.safe_load((REPO_ROOT / ".tess" / "tess.lock").read_text(encoding="utf-8"))
    records = lock.get("render_outputs")
    assert isinstance(records, dict) and {"CLAUDE.md", "AGENTS.md"} <= set(records), \
        "the repo lock must carry render records for its committed render outputs"
    import hashlib
    stale = []
    for rel, rec in sorted(records.items()):
        p = REPO_ROOT / rel
        sha = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "MISSING"
        if rec.get("status") == "rendered" and rec.get("rendered_sha") != sha:
            stale.append(rel)
    assert not stale, f"render_outputs records out of date (re-run `tessctl render`): {stale}"
