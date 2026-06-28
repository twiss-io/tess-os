"""
RENDER-ORDERING GUARD — proves the tracked-render E2E (test_tracked_render_e2e.py)
genuinely catches the render-before-core-advance bug (Reid HIGH), not just that it
happens to pass on the fixed engine.

We build a NEUTERED copy of the engine whose Step 7 render runs BEFORE A1
(core-advance) — the exact pre-fix ordering — and run the same tracked-render
upgrade against it.  The neutered engine MUST leave the live CLAUDE.md stale
(rendered from the OLD core) and doctor + verify MUST then FAIL.  This locks in
that the reorder is load-bearing: revert Step 7 back above A1 and this guard goes
red.

The neuter is done in-memory on a copy — the real engine on disk is never touched.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import types

import pytest

from conftest import ENGINE_SRC, make_upstream
from conftest import Project  # noqa: F401  (Project is used via the builder below)
import conftest

# Reuse the exact scenario content from the tracked-render E2E.
from test_tracked_render_e2e import (
    TPL, RULE_ZERO_V1, RULE_ZERO_V2, SETTINGS_V1, SETTINGS_V2,
    _FRAGMENTS, _TPL_KEY, _SETTINGS_KEY,
)


# ---------------------------------------------------------------------------
# Build a neutered engine: render BEFORE core-advance (the pre-fix ordering)
# ---------------------------------------------------------------------------

# The fixed engine renders here (post-A1/A2):
_FIXED_RENDER_BLOCK = (
    '        if not dry_run:\n'
    '            print("\\nStep 7: render (from new core, post-A1/A2) …")\n'
    '            _do_render(root, verbose=True)\n'
)
# Neutered: disable the post-advance render entirely.
_DISABLED_RENDER_BLOCK = (
    '        if not dry_run:\n'
    '            print("\\nStep 7: render NEUTERED (disabled post-A1)")\n'
    '            pass\n'
)

# Step 5-6 apply line — we splice a premature render right after it (pre-A1).
_APPLY_LINE = (
    '        print("\\nStep 5-6: plan and apply …")\n'
    '        _apply_per_file_resolution(root, lock, dry_run=dry_run)\n'
)
_APPLY_LINE_PLUS_PREMATURE = (
    _APPLY_LINE
    + '        if not dry_run:\n'
    + '            # NEUTER: premature render (pre-A1) — reproduces the ordering bug\n'
    + '            _do_render(root, verbose=True)\n'
)


def _load_neutered_engine(tmp_path):
    src = ENGINE_SRC.read_text(encoding="utf-8")

    # Fail LOUD if the anchors ever move — a silent no-op neuter would make this
    # guard pass for the wrong reason.
    assert src.count(_FIXED_RENDER_BLOCK) == 1, "post-A1 render anchor not found (engine refactored?)"
    assert src.count(_APPLY_LINE) == 1, "Step 5-6 apply anchor not found (engine refactored?)"

    src = src.replace(_FIXED_RENDER_BLOCK, _DISABLED_RENDER_BLOCK)
    src = src.replace(_APPLY_LINE, _APPLY_LINE_PLUS_PREMATURE)

    tmp_path.mkdir(parents=True, exist_ok=True)
    engine_file = tmp_path / "tessctl_neutered"
    engine_file.write_text(src, encoding="utf-8")

    loader = importlib.machinery.SourceFileLoader("tessctl_neutered", str(engine_file))
    spec = importlib.util.spec_from_loader("tessctl_neutered", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _ns(**kw):
    return types.SimpleNamespace(**kw)


def _seed_tracked_render(project):
    project.add("CLAUDE.md", TPL, core_key=_TPL_KEY, render_live=False)
    for core_key, content in _FRAGMENTS.items():
        project.add("CLAUDE.md", content, core_key=core_key, render_live=False)
    project.add(".claude/settings.json", SETTINGS_V1, core_key=_SETTINGS_KEY,
                render_live=False)
    project.write_live("CLAUDE.md", project.mod.render_claude_md(project.root))
    project.write_live(".claude/settings.json",
                       project.mod.render_settings_json(project.root))


def test_neutered_render_ordering_is_caught(gpg_key, tmp_path):
    neutered = _load_neutered_engine(tmp_path / "engine")
    project = conftest.Project(tmp_path / "proj", neutered)

    _seed_tracked_render(project)
    project.add("conductor/custom.md", "A\nB\nC\n", status="locally-modified")
    project.write_live("conductor/custom.md", "A-LOCAL\nB\nC\n")

    project.framework["upstream"] = str(tmp_path / "upstream")
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr
    project.write()
    assert "RULE ZERO V1" in project.read_live("CLAUDE.md")

    up_core = {
        _TPL_KEY: TPL,
        ".tess/core/templates/claude-md/rule-zero.md": RULE_ZERO_V2,   # CHANGED
        ".tess/core/templates/claude-md/system-laws.md": _FRAGMENTS[".tess/core/templates/claude-md/system-laws.md"],
        ".tess/core/templates/claude-md/orchestrators.md": _FRAGMENTS[".tess/core/templates/claude-md/orchestrators.md"],
        ".tess/core/templates/claude-md/commands.md": _FRAGMENTS[".tess/core/templates/claude-md/commands.md"],
        ".tess/core/templates/claude-md/directory.md": _FRAGMENTS[".tess/core/templates/claude-md/directory.md"],
        _SETTINGS_KEY: SETTINGS_V2,                                     # CHANGED
        ".tess/core/conductor/custom.md": "A\nB\nC-UP\n",
    }
    make_upstream(tmp_path / "upstream", gpg_key, "v2.1.0", sign="signed",
                  core_files=up_core)

    # Run the upgrade through the NEUTERED engine.  The update itself "succeeds"
    # (cmd_update never re-checks render freshness) — that is precisely the trap.
    neutered.cmd_update(
        _ns(ref="v2.1.0", to=None, dry_run=False, check=False, trust_on_first_use=False),
        project.root,
    )

    # The blind spot made visible: live CLAUDE.md is STALE (old fragment), because
    # render ran before A1 advanced the core.
    live_claude = project.read_live("CLAUDE.md")
    assert "RULE ZERO V1" in live_claude, "expected stale v1 render under neutered ordering"
    assert "RULE ZERO V2" not in live_claude, "neuter did not actually reproduce the bug"

    # doctor MUST fail — uncaptured drift on the tracked CLAUDE.md / settings.json.
    with pytest.raises(SystemExit) as ei_doctor:
        neutered.cmd_doctor(_ns(json_out=False, fix=False, path=None), project.root)
    assert ei_doctor.value.code == 1, "doctor should fail (exit 1) on stale tracked render"

    # verify MUST fail — live drift vs the advanced core.
    with pytest.raises(SystemExit) as ei_verify:
        neutered.cmd_verify(_ns(), project.root)
    assert ei_verify.value.code == 1, "verify should fail (exit 1) on stale tracked render"
