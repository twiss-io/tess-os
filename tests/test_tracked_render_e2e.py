"""
TRACKED-RENDER E2E — closes the blind spot that masked the render-before-core-
advance ordering bug (Reid HIGH).

The original acceptance test (test_clean_upgrade_e2e.py) wrote CLAUDE.md.tpl, the
claude-md/ fragments, and settings-core.json but left them UNTRACKED in tess.lock.
Because nothing tracked the render *inputs* or *outputs*, doctor/verify never
compared the live CLAUDE.md / .claude/settings.json against the post-upgrade core
— so a release that rendered from the OLD core (before A1 advanced it) passed
green anyway.  The stale-render bug was invisible.

This suite mirrors the REAL tess.lock: the template + every claude-md/ fragment
map to live_path "CLAUDE.md", and settings-core.json maps to ".claude/settings.json"
— all core-managed.  An upstream release then CHANGES a fragment and changes
settings-core.json.  After `tess update`, we assert the LIVE rendered files reflect
the NEW core, not the old.  With Step 7 render correctly sequenced AFTER A1/A2 this
passes; with the render run BEFORE core-advance it fails (doctor + verify flag the
stale CLAUDE.md as uncaptured/live drift) — see the neuter check in
tests/test_render_ordering_guard.py.
"""

from __future__ import annotations

import json

import pytest

from conftest import make_upstream


# --- v2.0.0 fragment + template + settings content (the OLD core) ------------

TPL = (
    "# Tess OS — Tracked Render\n"
    "\n"
    "Root: {{TESS_ROOT}}\n"
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

RULE_ZERO_V1 = "RULE ZERO V1 — always dispatch, never execute solo.\n"
SYSTEM_LAWS_V1 = "System laws v1.\n"
ORCHESTRATORS_V1 = "Orchestrators v1.\n"
COMMANDS_V1 = "Commands v1.\n"
DIRECTORY_V1 = "Directory v1.\n"
SETTINGS_V1 = '{"root": "{{TESS_ROOT}}", "feature_flag": "v1"}\n'

# v2.1.0 — the upstream CHANGES rule-zero + settings-core (the rest unchanged).
RULE_ZERO_V2 = "RULE ZERO V2 — TRACKED RENDER GUARD; dispatch is mandatory, fail-closed.\n"
SETTINGS_V2 = '{"root": "{{TESS_ROOT}}", "feature_flag": "v2-tracked"}\n'

# core_key → live_path mirror of the real lock's render entries.
_FRAGMENTS = {
    ".tess/core/templates/claude-md/rule-zero.md": RULE_ZERO_V1,
    ".tess/core/templates/claude-md/system-laws.md": SYSTEM_LAWS_V1,
    ".tess/core/templates/claude-md/orchestrators.md": ORCHESTRATORS_V1,
    ".tess/core/templates/claude-md/commands.md": COMMANDS_V1,
    ".tess/core/templates/claude-md/directory.md": DIRECTORY_V1,
}
_TPL_KEY = ".tess/core/templates/CLAUDE.md.tpl"
_SETTINGS_KEY = ".tess/core/settings-core.json"


def _seed_tracked_render(project):
    """Register the render inputs/outputs as core-managed lock entries, exactly
    like the production lock: template + all fragments → CLAUDE.md; settings-core
    → .claude/settings.json.  render_live=False so we render once at the end."""
    project.add("CLAUDE.md", TPL, core_key=_TPL_KEY, render_live=False)
    for core_key, content in _FRAGMENTS.items():
        project.add("CLAUDE.md", content, core_key=core_key, render_live=False)
    project.add(".claude/settings.json", SETTINGS_V1, core_key=_SETTINGS_KEY,
                render_live=False)
    # Render the live outputs once from the now-present core (pristine start state).
    project.write_live("CLAUDE.md", project.mod.render_claude_md(project.root))
    project.write_live(".claude/settings.json",
                       project.mod.render_settings_json(project.root))


def test_tracked_render_upgrade_reflects_new_core(project, gpg_key, tmp_path, run_cli):
    # -- Instance at v2.0.0: tracked render inputs + a locally-modified file ----
    _seed_tracked_render(project)
    # Operator local edit on an independent file: upstream edits line 3, operator
    # edited line 1 → clean 3-way merge must preserve the operator's edit.
    project.add("conductor/custom.md", "A\nB\nC\n", status="locally-modified")
    project.write_live("conductor/custom.md", "A-LOCAL\nB\nC\n")

    # Sanity: the live CLAUDE.md starts on the OLD fragment.
    project.framework["upstream"] = str(tmp_path / "upstream")
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr  # pinned (prod path)
    lock0 = project.write()
    assert "RULE ZERO V1" in project.read_live("CLAUDE.md")
    rz_sha_v1 = lock0["files"][".tess/core/templates/claude-md/rule-zero.md"]["base_sha"]
    sc_sha_v1 = lock0["files"][_SETTINGS_KEY]["base_sha"]

    # -- Signed upstream v2.1.0: CHANGES rule-zero fragment + settings-core -----
    up_core = {
        _TPL_KEY: TPL,
        ".tess/core/templates/claude-md/rule-zero.md": RULE_ZERO_V2,   # CHANGED
        ".tess/core/templates/claude-md/system-laws.md": SYSTEM_LAWS_V1,
        ".tess/core/templates/claude-md/orchestrators.md": ORCHESTRATORS_V1,
        ".tess/core/templates/claude-md/commands.md": COMMANDS_V1,
        ".tess/core/templates/claude-md/directory.md": DIRECTORY_V1,
        _SETTINGS_KEY: SETTINGS_V2,                                     # CHANGED
        ".tess/core/conductor/custom.md": "A\nB\nC-UP\n",
    }
    up_lock = {
        k: {"status": "core-managed", "tier": "normal",
            "live_path": ("CLAUDE.md" if "claude-md" in k or k.endswith("CLAUDE.md.tpl")
                          else ".claude/settings.json" if k == _SETTINGS_KEY
                          else "conductor/custom.md")}
        for k in up_core
    }
    make_upstream(tmp_path / "upstream", gpg_key, "v2.1.0", sign="signed",
                  core_files=up_core, lock_files=up_lock)

    # -- THE UPGRADE (through the CLI) ----------------------------------------
    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    assert r.returncode == 0, f"update failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"

    lock = project.lock()

    # (a) doctor EXIT 0 after update
    d = run_cli(project.root, "doctor")
    assert d.returncode == 0, f"doctor not clean after upgrade:\n{d.stdout}\n{d.stderr}"

    # (b) verify EXIT 0 after update
    v = run_cli(project.root, "verify")
    assert v.returncode == 0, f"verify not clean after upgrade:\n{v.stdout}\n{v.stderr}"
    assert "verify: OK" in v.stdout

    # (c) the LIVE CLAUDE.md reflects the NEW fragment content (not the old)
    live_claude = project.read_live("CLAUDE.md")
    assert "RULE ZERO V2" in live_claude, (
        "live CLAUDE.md was NOT re-rendered from the new core fragment "
        "(render ran before core-advance)"
    )
    assert "RULE ZERO V1" not in live_claude, "stale v1 fragment still present in live CLAUDE.md"

    # (d) live settings.json reflects the new settings
    live_settings = json.loads(project.read_live(".claude/settings.json"))
    assert live_settings["feature_flag"] == "v2-tracked", "settings.json not re-rendered from new core"
    assert live_settings["root"] == str(project.root)  # {{TESS_ROOT}} still substituted

    # (e) base_sha advanced + version bumped + operator edit preserved
    rz_sha_v2 = lock["files"][".tess/core/templates/claude-md/rule-zero.md"]["base_sha"]
    sc_sha_v2 = lock["files"][_SETTINGS_KEY]["base_sha"]
    assert rz_sha_v2 == project.mod.sha256_bytes(RULE_ZERO_V2.encode("utf-8"))
    assert rz_sha_v2 != rz_sha_v1, "rule-zero base_sha did not advance"
    assert sc_sha_v2 != sc_sha_v1, "settings-core base_sha did not advance"
    # core files actually hold the new upstream bytes
    assert project.core(".tess/core/templates/claude-md/rule-zero.md").read_bytes() == RULE_ZERO_V2.encode("utf-8")
    assert project.core(_SETTINGS_KEY).read_bytes() == SETTINGS_V2.encode("utf-8")
    # version bumped
    assert lock["framework"]["version"] == "2.1.0"
    assert lock["framework"]["upstream_ref"] == "v2.1.0"
    # operator local edit preserved + upstream change merged in
    merged = project.read_live("conductor/custom.md")
    assert "A-LOCAL" in merged, "operator's local edit was clobbered by the upgrade"
    assert "C-UP" in merged, "upstream change was not merged in"
    assert "<<<<<<<" not in merged
