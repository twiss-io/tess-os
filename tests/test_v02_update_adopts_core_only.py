"""
v0.2 ws-upd — `tessctl update` A2 adopts new upstream files that have NO live
path, and never overwrites what it cannot prove is upstream's.

The 0.1.4 -> v0.2.0 over-the-wire rehearsal (ws-rel, 2026-09-24) found:
  * A2 adopted only new upstream tess.lock entries WITH a live_path. Entries
    with live_path null (template fragments, GEMINI.md.tpl, roster-paths.json)
    were neither copied into .tess/core nor added to the lock. The upgraded
    install rendered AGENTS.md with `<!-- MISSING: ... -->` in place of the new
    worker sections, and roster-paths.json (shipped untracked by 0.1.4) stayed
    untracked, so v0.2's untracked-core check failed doctor and verify.
  * A2 wrote the live file for a new CLAUDE.md fragment entry even when the
    operator had published CLAUDE.md: the published edit was destroyed and the
    new entry (core-managed) disagreed with the published ones.

The fixtures are 0.1.4-shaped: the instance lock predates a core-only entry
the signed upstream adds, and a core file the old scaffold shipped untracked
is already on disk. Each test fails on 5c2d698 by assertion.
"""

from __future__ import annotations

import json

import pytest

from conftest import make_upstream

AGENTS_TPL_KEY = ".tess/core/templates/agents-md/AGENTS.md.tpl"
CODEX_CFG_KEY = ".tess/core/templates/agents-md/codex-config.toml.tpl"
HARD_FLOOR_W_KEY = ".tess/core/templates/agents-md/worker-hard-floor.md"
HARNESS_KEY = ".tess/core/templates/agents-md/harness-note.md"
NEW_FRAG_KEY = ".tess/core/templates/agents-md/shared-tasks.md"   # new, live_path null
ROSTER_KEY = ".tess/core/roster-paths.json"                       # shipped untracked
AGENTS_V1 = "# AGENTS.md fixture\n\n{{WORKER_HARD_FLOOR}}\n\n{{HARNESS_NOTE}}\n"
AGENTS_V2 = AGENTS_V1 + "\n{{WORKER_SHARED_TASKS}}\n"
NEW_FRAG = "SHARED TASKS SECTION - new in v2.1.0\n"
ROSTER = '{"universal_base": [], "paths": {}}\n'
COMMANDS = {"wake": "---\ndescription: wake\n---\n\n# /wake\n\nWake.\n"}

TPL_KEY = ".tess/core/templates/CLAUDE.md.tpl"
SETTINGS_KEY = ".tess/core/settings-core.json"
CLAUDE_FRAGS = {
    ".tess/core/templates/claude-md/rule-zero.md": "RULE ZERO FIXTURE\n",
    ".tess/core/templates/claude-md/system-laws.md": "SYSTEM LAWS FIXTURE\n",
}
HARD_FLOOR_KEY = ".tess/core/templates/claude-md/hard-floor.md"   # new CLAUDE.md input
HARD_FLOOR = "HARD FLOOR FIXTURE - never weaken\n"
CLAUDE_TPL = "# CLAUDE fixture\n\n{{CORE_RULE_ZERO}}\n\n{{CORE_HARD_FLOOR}}\n\n{{CORE_SYSTEM_LAWS}}\n"
SETTINGS = '{"root": "{{TESS_ROOT}}"}\n'


def _sha(project, text):
    return project.mod.sha256_bytes(text.encode("utf-8"))


def _set_enabled(project, names):
    mf = project.root / "tess.manifest.json"
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest.setdefault("render_targets", {})["enabled"] = list(names)
    mf.write_text(json.dumps(manifest), encoding="utf-8")


def _pin(project, gpg_key, tmp_path):
    project.framework["upstream"] = str(tmp_path / "upstream")
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr


def _untracked_core(root, lock):
    """What v0.2's untracked-core check (doctor/verify/lock --check) flags."""
    keys = set(lock["files"])
    return sorted(
        p.relative_to(root).as_posix() for p in (root / ".tess" / "core").rglob("*")
        if p.is_file() and p.name not in (".DS_Store", ".gitkeep")
        and "__pycache__" not in p.parts and p.relative_to(root).as_posix() not in keys)


def _codex_install(project, gpg_key, tmp_path, run_cli, *, roster=ROSTER):
    """An older codex install: its lock has no shared-tasks.md entry, and
    roster-paths.json sits in .tess/core without a lock entry (as 0.1.4 ships it)."""
    project.add(None, AGENTS_V1, core_key=AGENTS_TPL_KEY, render_live=False)
    project.add(None, "HARD FLOOR (worker)\n", core_key=HARD_FLOOR_W_KEY, render_live=False)
    project.add(None, "HARNESS NOTE\n", core_key=HARNESS_KEY, render_live=False)
    project.add(None, 'approval_policy = "on-request"\n', core_key=CODEX_CFG_KEY,
                render_live=False)
    for name, body in COMMANDS.items():
        project.add(f".claude/commands/{name}.md", body,
                    core_key=f".tess/core/commands/{name}.md")
    (project.root / ROSTER_KEY).write_text(roster, encoding="utf-8")
    _pin(project, gpg_key, tmp_path)
    project.write()
    _set_enabled(project, ["codex"])
    r = run_cli(project.root, "render")
    assert r.returncode == 0, r.stdout + r.stderr


def _codex_upstream(project, gpg_key, tmp_path, *, extra_core=None, extra_lock=None):
    core = {AGENTS_TPL_KEY: AGENTS_V2, HARD_FLOOR_W_KEY: "HARD FLOOR (worker)\n",
            HARNESS_KEY: "HARNESS NOTE\n", CODEX_CFG_KEY: 'approval_policy = "on-request"\n',
            NEW_FRAG_KEY: NEW_FRAG, ROSTER_KEY: ROSTER}
    core.update({f".tess/core/commands/{n}.md": b for n, b in COMMANDS.items()})
    core.update(extra_core or {})
    lock = {}
    for key, text in core.items():
        live = (f".claude/commands/{key.rsplit('/', 1)[1]}"
                if key.startswith(".tess/core/commands/") else None)
        lock[key] = {"status": "core-managed", "tier": "normal",
                     "base_sha": _sha(project, text), "live_path": live}
    lock.update(extra_lock or {})
    make_upstream(tmp_path / "upstream", gpg_key, "v2.1.0", sign="signed",
                  core_files=core, lock_files=lock)
    return lock


def test_update_adopts_core_only_upstream_files_on_014_shaped_install(
        project, gpg_key, tmp_path, run_cli):
    _codex_install(project, gpg_key, tmp_path, run_cli)
    up_lock = _codex_upstream(project, gpg_key, tmp_path)

    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    assert r.returncode == 0, f"update failed:\n{r.stdout}\n{r.stderr}"
    lock = project.lock()

    # the new fragment is extracted into core and pinned at the upstream base_sha
    frag = project.core(NEW_FRAG_KEY)
    assert frag.is_file(), f"{NEW_FRAG_KEY} was not extracted into .tess/core:\n{r.stdout}"
    assert frag.read_text(encoding="utf-8") == NEW_FRAG
    for key in (NEW_FRAG_KEY, ROSTER_KEY):
        entry = lock["files"].get(key)
        assert entry is not None, f"{key} not adopted into tess.lock:\n{r.stdout}"
        assert entry["live_path"] is None and entry["status"] == "core-managed"
        assert entry["base_sha"] == up_lock[key]["base_sha"]
    assert project.core(ROSTER_KEY).read_text(encoding="utf-8") == ROSTER
    assert _untracked_core(project.root, lock) == []

    # the render that uses the new template includes the new section
    agents = project.read_live("AGENTS.md")
    assert "SHARED TASKS SECTION" in agents and "<!-- MISSING:" not in agents, agents

    for cmd in ("doctor", "verify"):
        c = run_cli(project.root, cmd)
        assert c.returncode == 0, f"{cmd} not clean after upgrade:\n{c.stdout}\n{c.stderr}"

    # idempotent: a second update adopts nothing and changes no core or lock entry
    r2 = run_cli(project.root, "update", "--ref", "v2.1.0")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "A2: no new files to adopt" in r2.stdout
    assert project.lock()["files"] == lock["files"]


@pytest.mark.parametrize("flag", ["--dry-run", "--check"])
def test_update_dry_run_lists_core_only_adoptions_and_writes_nothing(
        project, gpg_key, tmp_path, run_cli, flag):
    _codex_install(project, gpg_key, tmp_path, run_cli)
    up_lock = _codex_upstream(project, gpg_key, tmp_path)
    # a previous fetch left the signed upstream in staging (dry-run never fetches)
    for key in (NEW_FRAG_KEY, ROSTER_KEY):
        src = tmp_path / "upstream" / key
        project.stage(key, src.read_bytes())
    (project.root / ".tess" / "staging" / "upstream-tess.lock").write_text(
        json.dumps({"schema": 1, "files": up_lock}), encoding="utf-8")
    lock_bytes = (project.root / ".tess" / "tess.lock").read_bytes()

    r = run_cli(project.root, "update", "--ref", "v2.1.0", flag)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"would adopt: {NEW_FRAG_KEY}" in r.stdout, r.stdout
    assert f"would adopt: {ROSTER_KEY}" in r.stdout, r.stdout
    assert not project.core(NEW_FRAG_KEY).exists(), "dry-run wrote a core file"
    assert (project.root / ".tess" / "tess.lock").read_bytes() == lock_bytes


def test_adoption_keeps_what_it_cannot_prove_is_upstreams(project, gpg_key, tmp_path, run_cli):
    # roster-paths.json was edited locally; the operator owns a file at a new live path
    _codex_install(project, gpg_key, tmp_path, run_cli, roster='{"local": "edit"}\n')
    project.write_live("conductor/new-doc.md", "OPERATOR'S OWN FILE\n")
    mf = project.root / "tess.manifest.json"
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["never_touch"].append(".tess/core/fenced/**")
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    bad = ".tess/core/templates/agents-md/bad-pin.md"
    fenced = ".tess/core/fenced/x.md"
    _codex_upstream(project, gpg_key, tmp_path,
                    extra_core={bad: "BAD PIN\n", fenced: "FENCED\n",
                                ".tess/core/conductor/new-doc.md": "UPSTREAM DOC\n"},
                    extra_lock={bad: {"status": "core-managed", "tier": "normal",
                                      "base_sha": _sha(project, "something else\n"),
                                      "live_path": None},
                                ".tess/core/conductor/new-doc.md": {
                                    "status": "core-managed", "tier": "normal",
                                    "base_sha": _sha(project, "UPSTREAM DOC\n"),
                                    "live_path": "conductor/new-doc.md"}})

    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    assert r.returncode == 0, f"update failed:\n{r.stdout}\n{r.stderr}"
    lock = project.lock()

    assert NEW_FRAG_KEY in lock["files"], "the safe core-only file was not adopted"
    # a locally edited core file is neither overwritten nor pinned
    assert project.core(ROSTER_KEY).read_text(encoding="utf-8") == '{"local": "edit"}\n'
    assert ROSTER_KEY not in lock["files"]
    # bytes that do not match the upstream pin, and never_touch paths, are refused
    for key in (bad, fenced):
        assert key not in lock["files"] and not project.core(key).exists(), key
        assert f"WARN  A2: not adopted {key}" in r.stdout, r.stdout
    # the operator's file at a new live path is kept; the entry is adopted
    assert project.read_live("conductor/new-doc.md") == "OPERATOR'S OWN FILE\n"
    assert lock["files"][".tess/core/conductor/new-doc.md"]["live_path"] == "conductor/new-doc.md"
    assert "KEEP  conductor/new-doc.md" in r.stdout
    # only the kept core file is left untracked, and doctor says so
    assert _untracked_core(project.root, lock) == [ROSTER_KEY]


def _claude_install(project, gpg_key, tmp_path, *, status):
    """CLAUDE.md composed from a template + fragments, all tracked to CLAUDE.md;
    hard-floor.md is in core but has no lock entry (the 0.1.4 shape)."""
    project.add("CLAUDE.md", CLAUDE_TPL, core_key=TPL_KEY, render_live=False, status=status)
    for key, text in CLAUDE_FRAGS.items():
        project.add("CLAUDE.md", text, core_key=key, render_live=False, status=status)
    project.add(".claude/settings.json", SETTINGS, core_key=SETTINGS_KEY, render_live=False)
    (project.root / HARD_FLOOR_KEY).write_text(HARD_FLOOR, encoding="utf-8")
    project.write_live("CLAUDE.md", project.mod.render_claude_md(project.root))
    project.write_live(".claude/settings.json", project.mod.render_settings_json(project.root))
    _pin(project, gpg_key, tmp_path)
    project.write()
    core = {TPL_KEY: CLAUDE_TPL, SETTINGS_KEY: SETTINGS, HARD_FLOOR_KEY: HARD_FLOOR}
    core.update(CLAUDE_FRAGS)
    up_lock = {k: {"status": "core-managed", "tier": "normal", "base_sha": _sha(project, t),
                   "live_path": ".claude/settings.json" if k == SETTINGS_KEY else "CLAUDE.md"}
               for k, t in core.items()}
    up_lock[HARD_FLOOR_KEY].update(tier="security", render="fragment")
    make_upstream(tmp_path / "upstream", gpg_key, "v2.1.0", sign="signed",
                  core_files=core, lock_files=up_lock)
    return up_lock


def test_published_claude_md_survives_a_new_fragment_entry(project, gpg_key, tmp_path, run_cli):
    _claude_install(project, gpg_key, tmp_path, status="user-published")
    edited = project.read_live("CLAUDE.md") + "\nOPERATOR PUBLISHED EDIT\n"
    project.write_live("CLAUDE.md", edited)

    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    assert r.returncode == 0, f"update failed:\n{r.stdout}\n{r.stderr}"

    assert project.read_live("CLAUDE.md") == edited, "update overwrote the published CLAUDE.md"
    lock = project.lock()
    statuses = {k: a["status"] for k, a in lock["files"].items() if a["live_path"] == "CLAUDE.md"}
    assert HARD_FLOOR_KEY in statuses
    assert set(statuses.values()) == {"user-published"}, statuses
    assert _untracked_core(project.root, lock) == []


def test_new_claude_md_fragment_is_pinned_as_upstream_and_rendered(
        project, gpg_key, tmp_path, run_cli):
    up_lock = _claude_install(project, gpg_key, tmp_path, status="core-managed")

    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    assert r.returncode == 0, f"update failed:\n{r.stdout}\n{r.stderr}"
    lock = project.lock()

    entry = dict(lock["files"][HARD_FLOOR_KEY])
    entry.pop("last_updated")
    assert entry == {"status": "core-managed", "tier": "security",
                     "base_sha": up_lock[HARD_FLOOR_KEY]["base_sha"],
                     "live_path": "CLAUDE.md", "render": "fragment"}
    assert "HARD FLOOR FIXTURE" in project.read_live("CLAUDE.md")
    assert _untracked_core(project.root, lock) == []
    for cmd in ("doctor", "verify"):
        c = run_cli(project.root, cmd)
        assert c.returncode == 0, f"{cmd} not clean after upgrade:\n{c.stdout}\n{c.stderr}"
