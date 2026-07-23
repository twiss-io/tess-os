"""
Issue #21 — a renamed conductor must read consistently everywhere a scaffold
renders, not just in the historic 3-file `_NAME_BEARING` subset
(conductor/identity.md, conductor/personality.md, clients/_template/CLAUDE.md).

Before this fix, `cmd_rename` / `cmd_set_operator` / `cmd_pathway` called only
`_render_enabled_targets()`, which for the claude-code target is `_do_render()`
— hardcoded to that 3-file subset (plus CLAUDE.md/.claude/settings.json). Any
OTHER core-managed file carrying an {{ASSISTANT_NAME}} token (e.g.
conductor/guardrails.md, conductor/doctrine.md, agents/**, .claude/commands/**
— all of which hardcoded the literal default name "Tess" in prose before this
fix's content pass added the token) would silently stay stale on rename: the
propagation gap issue #21 reports as "residual hardcoded default naming in
deep doctrine."

Fixed by `_rerender_identity_surfaces()`, which additionally runs
`_do_restore()` — the SAME target-agnostic, lock-entry-driven core -> live
sync `cmd_init` / `cmd_restore` already use, which calls
`render_core_to_live()` (-> `apply_token_sub()`) for every core-managed file,
not just the templated 3. This test seeds REAL shipped core content
(.tess/core/conductor/guardrails.md, .tess/core/commands/help.md) — both
touched by issue #21's content fix and both OUTSIDE the `_NAME_BEARING` list
— so the assertions exercise the actually-shipped doctrine, not a synthetic
stand-in that could pass while the real files still regress.

Follow-up audit (same issue, continued fix): the original content pass swept
`conductor/**`, `agents/**`, and `.claude/commands/**` but missed three
JSON render surfaces that go through the exact same `apply_token_sub()` path
— `apply_token_sub` substitutes on raw text regardless of file extension, so
JSON is just as live as markdown here: `.tess/core/settings-core.json` (a
literal "Tess" inside the `PostToolUse` hook's embedded systemMessage JSON
string) and two `core/contracts/**` schemas —
`.tess/core/contracts/crew-plan.schema.json` and
`.tess/core/contracts/verdict.schema.json` — both quoting doctrine prose
that itself already carried the token (`conductor/orchestra-model.md`,
`conductor/verification-routing.md`) but hardcoded the literal name in their
own `description` fields. `test_rename_propagates_to_previously_hardcoded_contract_schema`
below proves the fix on `core/contracts/**` — a third distinct
`owned_globs` entry — the same way the two tests above prove it for
`conductor/**` and `.claude/commands/**`.
"""
from __future__ import annotations

from conftest import REPO_ROOT

_REAL_CONDUCTOR = REPO_ROOT / ".tess" / "core" / "conductor"
_REAL_COMMANDS = REPO_ROOT / ".tess" / "core" / "commands"
_REAL_CONTRACTS = REPO_ROOT / ".tess" / "core" / "contracts"

# Minimal CLAUDE.md render surface — required so the claude-code target's
# `_do_render()` compile step (CLAUDE.md/.claude/settings.json) doesn't error
# before ever reaching the doctrine-corpus files under test.
_TPL = "# {{ASSISTANT_NAME}} OS\n\nRoot: {{TESS_ROOT}}\n"
_TPL_KEY = ".tess/core/templates/CLAUDE.md.tpl"
_SETTINGS_KEY = ".tess/core/settings-core.json"
_SETTINGS = '{"root": "{{TESS_ROOT}}"}\n'


def _seed(project):
    """A hermetic instance carrying: the historic 3-file _NAME_BEARING subset
    (so the pre-existing propagation path keeps working — this fix is
    additive, never a replacement), PLUS two REAL doctrine files from outside
    that subset that issue #21's content fix tokenized:
      * conductor/guardrails.md — tier:security, conductor/** copy-only surface
      * .claude/commands/help.md — .claude/commands/** copy-only surface
    Both are core-managed with a live_path, so `_do_restore()` must sync them;
    before this fix, nothing did on `rename`.
    """
    root = project.root

    project.add("CLAUDE.md", _TPL, core_key=_TPL_KEY, render_live=False)
    project.add(".claude/settings.json", _SETTINGS, core_key=_SETTINGS_KEY, render_live=False)
    project.add(
        "conductor/identity.md",
        (_REAL_CONDUCTOR / "identity.md").read_text(encoding="utf-8"),
    )

    project.add(
        "conductor/guardrails.md",
        (_REAL_CONDUCTOR / "guardrails.md").read_text(encoding="utf-8"),
        tier="security",
    )
    project.add(
        ".claude/commands/help.md",
        (_REAL_COMMANDS / "help.md").read_text(encoding="utf-8"),
        core_key=".tess/core/commands/help.md",
    )
    project.add(
        "core/contracts/verdict.schema.json",
        (_REAL_CONTRACTS / "verdict.schema.json").read_text(encoding="utf-8"),
        core_key=".tess/core/contracts/verdict.schema.json",
        tier="security",
    )

    project.write()
    project.write_live("CLAUDE.md", project.mod.render_claude_md(root))
    project.write_live(".claude/settings.json", project.mod.render_settings_json(root))
    return project


def _assert_clean(run_cli, root, when: str):
    d = run_cli(root, "doctor")
    assert d.returncode == 0, f"doctor flagged drift {when}:\n{d.stdout}\n{d.stderr}"
    assert "doctor: OK" in d.stdout
    v = run_cli(root, "verify")
    assert v.returncode == 0, f"verify flagged drift {when}:\n{v.stdout}\n{v.stderr}"
    assert "verify: OK" in v.stdout


def test_rename_propagates_to_previously_hardcoded_conductor_file(project, run_cli):
    """The core regression proof: renaming the conductor must refresh a
    core-managed conductor/** doctrine file OUTSIDE the historic 3-file
    _NAME_BEARING subset."""
    _seed(project)
    root = project.root

    before = project.read_live("conductor/guardrails.md")
    assert "# Guardrails — Tess" in before
    assert "Tess orchestrates" in before

    r = run_cli(root, "rename", "Atlas")
    assert r.returncode == 0, f"rename failed:\n{r.stdout}\n{r.stderr}"

    after = project.read_live("conductor/guardrails.md")
    assert "# Guardrails — Atlas" in after, (
        "rename did not propagate into conductor/guardrails.md — the "
        "3-file _NAME_BEARING subset gap (issue #21) has regressed"
    )
    assert "Atlas orchestrates" in after
    assert "# Guardrails — Tess" not in after
    assert "Tess orchestrates" not in after

    _assert_clean(run_cli, root, "after rename (conductor/guardrails.md)")


def test_rename_propagates_to_previously_hardcoded_command_file(project, run_cli):
    """Same regression, proven on the .claude/commands/** copy-only surface
    (a different owned_globs entry than conductor/**), so the fix is proven
    to be the generic _do_restore() sync — not a one-off special case."""
    _seed(project)
    root = project.root

    before = project.read_live(".claude/commands/help.md")
    assert "for the Tess command system" in before

    r = run_cli(root, "rename", "Atlas")
    assert r.returncode == 0, f"rename failed:\n{r.stdout}\n{r.stderr}"

    after = project.read_live(".claude/commands/help.md")
    assert "for the Atlas command system" in after, (
        "rename did not propagate into .claude/commands/help.md — the "
        "3-file _NAME_BEARING subset gap (issue #21) has regressed"
    )
    assert "for the Tess command system" not in after

    _assert_clean(run_cli, root, "after rename (.claude/commands/help.md)")


def test_rename_propagates_to_previously_hardcoded_contract_schema(project, run_cli):
    """Same regression again, proven on `core/contracts/**` — a THIRD
    distinct owned_globs entry, and the first non-markdown one exercised
    here. `apply_token_sub()` substitutes on raw text regardless of file
    extension, so a JSON Schema `description` field quoting doctrine prose
    is just as live a render surface as a conductor/** .md file — the
    follow-up audit found `verdict.schema.json` (and `crew-plan.schema.json`)
    still hardcoding the literal name where they quote
    conductor/verification-routing.md's (already-tokenized) prose."""
    _seed(project)
    root = project.root

    before = project.read_live("core/contracts/verdict.schema.json")
    assert "never Tess's summary of those artifacts" in before

    r = run_cli(root, "rename", "Atlas")
    assert r.returncode == 0, f"rename failed:\n{r.stdout}\n{r.stderr}"

    after = project.read_live("core/contracts/verdict.schema.json")
    assert "never Atlas's summary of those artifacts" in after, (
        "rename did not propagate into core/contracts/verdict.schema.json — "
        "the JSON-contracts corner of the issue #21 gap has regressed"
    )
    assert "never Tess's summary of those artifacts" not in after

    _assert_clean(run_cli, root, "after rename (core/contracts/verdict.schema.json)")


def test_rename_noop_still_leaves_previously_hardcoded_file_clean(project, run_cli):
    """A no-op rename (same name) must not touch anything, and the tree must
    already read clean before any rename ever runs — the default-name
    behavior is unchanged by this fix."""
    _seed(project)
    root = project.root
    _assert_clean(run_cli, root, "before any rename (default name)")

    r = run_cli(root, "rename", "Tess")
    assert r.returncode == 0
    assert "no change" in r.stdout

    assert "# Guardrails — Tess" in project.read_live("conductor/guardrails.md")
    _assert_clean(run_cli, root, "after no-op rename")
