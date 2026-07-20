"""
Issue #131 — the SKILL DRAFT SCAFFOLD (`tessctl skill from-task <id>`), the
"gets smarter from your work" pattern: a completed task + its REAL ledger
trail (a sibling of the TASK STORE — tests/test_task_store.py — and the
ACCOUNTABILITY LEDGER — tests/test_accountability_ledger.py — it draws on,
reusing the AUDIT PACK region's own task-scoped ledger collector —
tests/test_audit_pack.py) becomes a scaffolded, DRAFT, human-reviewed
reusable skill fitting the REAL `.claude/skills/*/SKILL.md` progressive-
disclosure format.

Coverage:
  * A NARRATED task (real notes + evidence recorded) scaffolds a step
    sequence matching the REAL ledger event summaries verbatim, and a
    reusable-instructions section carrying the REAL note text/evidence
    verbatim — no gap-flags, nothing fabricated.
  * A MECHANICAL-ONLY task (ledger events exist — the auto-logged creation
    event — but no notes/evidence recorded) produces an explicit gap-flag
    ("no notes were recorded...") — never fabricated procedural prose.
  * An EMPTY-trail task (engine-level: a task record with ZERO matching
    ledger events, only reachable by writing the record directly, bypassing
    `tasks new`'s own auto-log) produces the explicit "no derivable step
    sequence" gap, not silently narrated content.
  * A source task not marked `done` gets a prominent WARNING banner in
    `SKILL.md`; a `done` task does not.
  * `SKILL.md`'s frontmatter is valid YAML with `name`/`description`/
    `status: draft`/`source_task` present — the loadable-format proxy
    check (the real loader is the Claude Code host itself, not anything in
    this repo).
  * The default `--out` lands under `.tess/state/skills/drafts/<slug>` —
    NEVER `.claude/skills/` (the live, core-managed, host-loaded skill
    set) — the auto-activation scope-boundary guarantee.
  * `--out`/`--force` conflict handling mirrors `audit export`'s own
    precedent exactly: a non-empty target is refused without `--force`,
    accepted (overwritten) with it; a custom `--out` works.
  * An unknown task id is refused with a clear message, non-zero exit.
  * Generation is READ-ONLY against the task record (no `rev`/`updated_at`
    change) — the SOLE accountability artifact is the new `skill_generated`
    ledger line, logged through the EXISTING `_ledger_auto_log` append
    path, schema-accepted, and visible to a SUBSEQUENT `tessctl audit
    export --task <id>` — proving it lands in the SAME accountability
    ledger, not a side channel.
  * `provenance.json` embeds the source-task snapshot + every matched
    ledger event verbatim, traceable back to the live ledger
    (`tessctl log view --task <id>` reproduces the identical event list).
  * Schema/lint coverage for the new `skill_generated` ledger event class.
  * Issue #133 (Cyra LOW, PR #132 review follow-up): an operator-explicit
    `--out` that resolves under `.claude/skills/` (the live skill set) is
    refused — as the literal path, as the forbidden root itself, via a
    `..` traversal, and via a symlink whose target resolves there — and the
    refusal is unconditional (`--force` does not clear it). Nothing is
    written to disk once it fires.
  * Issue #133 (Reid LOW): doc-accuracy regression pinning the REAL
    `--help` flag set (`--out`/`--force`/`--harness`/`--session`/
    `--persona`/`--json`) — no `--slug` flag exists.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT, ENGINE_SRC

CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"
SCHEMA_FILES = ("task.schema.json", "ledger-event.schema.json")


@pytest.fixture
def sroot(tmp_path):
    """Mirrors tests/test_task_stuck_packet.py's / tests/test_audit_pack.py's
    own fixture exactly — a minimal synthetic root with just enough
    (tess.manifest.json, the task + ledger-event contracts, the real engine)
    for `tasks`/`log`/`skill` subcommands."""
    root = tmp_path / "os"
    contracts_dir = root / "core" / "contracts"
    contracts_dir.mkdir(parents=True)
    for name in SCHEMA_FILES:
        shutil.copy2(CONTRACTS_SRC / name, contracts_dir / name)
    (root / "tess.manifest.json").write_text(
        json.dumps({"schema": 1, "owned_globs": [], "never_touch": [".tess/state/**"]}),
        encoding="utf-8",
    )
    bin_dir = root / ".tess" / "bin"
    bin_dir.mkdir(parents=True)
    dst_engine = bin_dir / "tessctl"
    shutil.copy2(ENGINE_SRC, dst_engine)
    os.chmod(dst_engine, 0o755)
    return root


def _run(root, *args):
    env = {**os.environ, "TESS_ROOT": str(root)}
    return subprocess.run(
        [sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
        cwd=str(root), env=env, capture_output=True, text=True,
    )


def _task_path(root, task_id):
    return root / ".tess" / "state" / "tasks" / f"{task_id}.json"


def _new_task(root, title="Fix login bug", harness="claude-code", **kw):
    args = ["tasks", "new", title, "--harness", harness]
    for k, v in kw.items():
        args += [f"--{k.replace('_', '-')}", str(v)]
    r = _run(root, *args)
    assert r.returncode == 0, r.stdout + r.stderr
    task_id = r.stdout.splitlines()[0].split("—")[1].strip()
    return task_id


def _set_task(root, task_id, *extra_args, harness="claude-code"):
    r = _run(root, "tasks", "set", task_id, *extra_args, "--harness", harness)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def _events(root, task_id):
    v = _run(root, "log", "view", "--task", task_id, "--json")
    assert v.returncode == 0, v.stdout + v.stderr
    return json.loads(v.stdout)


def _from_task(root, task_id, *extra_args, harness="ada"):
    return _run(root, "skill", "from-task", task_id, "--harness", harness, *extra_args)


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "SKILL.md must open with a YAML frontmatter fence"
    end = text.index("\n---\n", 4)
    fm_text = text[4:end]
    return yaml.safe_load(fm_text)


# ---------------------------------------------------------------------------
# Narrated task — real steps, real instructions, nothing fabricated.
# ---------------------------------------------------------------------------

def test_narrated_task_produces_real_step_sequence_and_instructions(sroot):
    task_id = _new_task(sroot, "Fix login bug")
    _set_task(
        sroot, task_id, "--status", "in_progress",
        "--add-note", "wired the endpoint, auth 401s went away after rotating the secret",
        "--by", "Ada",
    )
    _set_task(sroot, task_id, "--add-evidence", "src/auth/login.py")
    _set_task(sroot, task_id, "--status", "done")

    real_events = _events(sroot, task_id)
    assert len(real_events) >= 3  # creation + 2 sets + done

    r = _from_task(sroot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr

    out_dir = Path(r.stdout.splitlines()[0].split("->")[-1].strip())
    skill_text = (out_dir / "SKILL.md").read_text(encoding="utf-8")
    provenance = json.loads((out_dir / "provenance.json").read_text(encoding="utf-8"))

    # Every REAL (pre-generation) ledger summary appears verbatim.
    for e in real_events:
        assert e["summary"] in skill_text, f"real ledger summary missing from SKILL.md: {e['summary']!r}"

    # The real note + evidence appear verbatim.
    assert "wired the endpoint, auth 401s went away after rotating the secret" in skill_text
    assert "src/auth/login.py" in skill_text

    # A narrated trail carries no gap-flags.
    assert provenance["trail"]["completeness"] == "narrated"
    assert provenance["reusable_instructions"]["gap_flags"] == []
    assert "must be filled in" not in skill_text.lower()


def test_provenance_events_match_live_ledger_exactly(sroot):
    task_id = _new_task(sroot, "Ship the widget")
    _set_task(sroot, task_id, "--add-note", "shipped via the standard release flow", "--by", "Ada")
    pre_events = _events(sroot, task_id)

    r = _from_task(sroot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr
    out_dir = Path(r.stdout.splitlines()[0].split("->")[-1].strip())
    provenance = json.loads((out_dir / "provenance.json").read_text(encoding="utf-8"))

    assert provenance["trail"]["events"] == pre_events, "provenance.json must embed the REAL events verbatim"
    assert provenance["trail"]["event_count"] == len(pre_events)
    assert provenance["source_task"]["id"] == task_id


# ---------------------------------------------------------------------------
# Mechanical-only (thin) trail — gap-flagged, nothing invented.
# ---------------------------------------------------------------------------

def test_mechanical_only_task_flags_gap_no_fabrication(sroot):
    task_id = _new_task(sroot, "Untouched task")  # only the auto-logged creation event exists
    r = _from_task(sroot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr
    out_dir = Path(r.stdout.splitlines()[0].split("->")[-1].strip())
    skill_text = (out_dir / "SKILL.md").read_text(encoding="utf-8")
    provenance = json.loads((out_dir / "provenance.json").read_text(encoding="utf-8"))

    assert provenance["trail"]["completeness"] == "mechanical-only"
    assert provenance["trail"]["event_count"] == 1
    gap_flags = provenance["reusable_instructions"]["gap_flags"]
    assert any("no task notes were recorded" in g.lower() for g in gap_flags)
    assert any("no evidence paths were recorded" in g.lower() for g in gap_flags)
    assert "No task notes were recorded — nothing here is invented." in skill_text
    assert "Gaps a human must fill in before this skill is authoritative" in skill_text


def test_empty_trail_task_produces_explicit_gap_not_narrated_content(sroot, engine):
    """Engine-level: a task record written directly to disk (bypassing
    `tasks new`'s own auto-log), so it has ZERO matching ledger events —
    only reachable this way through the normal CLI, but a real, tested,
    fail-closed case (never silently treated as narrated)."""
    task_id = "T-20260720-orphan-task-aaaa"
    record = {
        "id": task_id, "title": "Orphan task (no ledger events)", "status": "backlog",
        "owner": None, "assignee": None, "target_harness": "any",
        "claim": {"host": None, "pid": None, "uuid": None, "claimed_at": None, "heartbeat_at": None},
        "created_by": {"harness": "claude-code", "session": None},
        "created_at": "2026-07-20T00:00:00Z", "updated_at": "2026-07-20T00:00:00Z",
        "rev": 1, "depends_on": [], "evidence": [], "notes": [], "blocked": None,
    }
    path = _task_path(sroot, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    r = _from_task(sroot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr
    out_dir = Path(r.stdout.splitlines()[0].split("->")[-1].strip())
    skill_text = (out_dir / "SKILL.md").read_text(encoding="utf-8")
    provenance = json.loads((out_dir / "provenance.json").read_text(encoding="utf-8"))

    assert provenance["trail"]["completeness"] == "empty"
    assert provenance["trail"]["event_count"] == 0
    assert provenance["trail"]["step_sequence"] == []
    assert "no derivable step sequence" in skill_text.lower()
    assert "no ledger events matched this task at all" in skill_text.lower() or any(
        "no ledger events matched" in g.lower() for g in provenance["reusable_instructions"]["gap_flags"]
    )


# ---------------------------------------------------------------------------
# Status warning banner.
# ---------------------------------------------------------------------------

def test_status_not_done_gets_warning_banner(sroot):
    task_id = _new_task(sroot, "In-flight task")
    r = _from_task(sroot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr
    out_dir = Path(r.stdout.splitlines()[0].split("->")[-1].strip())
    skill_text = (out_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "WARNING" in skill_text
    assert "not `done`" in skill_text


def test_status_done_has_no_warning_banner(sroot):
    task_id = _new_task(sroot, "Completed task")
    _set_task(sroot, task_id, "--status", "done")
    r = _from_task(sroot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr
    out_dir = Path(r.stdout.splitlines()[0].split("->")[-1].strip())
    skill_text = (out_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "WARNING" not in skill_text


# ---------------------------------------------------------------------------
# Loadable format — real progressive-disclosure frontmatter shape.
# ---------------------------------------------------------------------------

def test_frontmatter_is_valid_yaml_with_required_keys(sroot):
    task_id = _new_task(sroot, "Frontmatter check")
    r = _from_task(sroot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr
    out_dir = Path(r.stdout.splitlines()[0].split("->")[-1].strip())
    skill_text = (out_dir / "SKILL.md").read_text(encoding="utf-8")

    fm = _frontmatter(skill_text)
    assert isinstance(fm["name"], str) and fm["name"]
    assert isinstance(fm["description"], str) and fm["description"]
    assert fm["status"] == "draft"
    assert fm["source_task"] == task_id
    assert fm["generated_by"] == "tessctl skill from-task"
    assert "generated_at" in fm


def test_real_shipped_skills_have_the_same_frontmatter_fence_shape():
    """Sanity check against the REAL, shipped `.claude/skills/*/SKILL.md`
    files this scaffold is meant to fit alongside — proves the generated
    file's `---\\n...\\n---\\n` fence convention matches the actual format,
    not an invented lookalike."""
    real_skill = REPO_ROOT / ".claude" / "skills" / "browser-use" / "SKILL.md"
    assert real_skill.is_file()
    text = real_skill.read_text(encoding="utf-8")
    fm = _frontmatter(text)
    assert "name" in fm and "description" in fm


# ---------------------------------------------------------------------------
# Never auto-activated — draft location + `.claude/skills/` untouched.
# ---------------------------------------------------------------------------

def test_default_out_dir_is_state_skills_drafts(sroot):
    task_id = _new_task(sroot, "Fix login bug")
    r = _from_task(sroot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr
    out_dir = Path(r.stdout.splitlines()[0].split("->")[-1].strip())
    assert out_dir.parent.parent == sroot / ".tess" / "state" / "skills"
    assert out_dir.parent.name == "drafts"
    assert (out_dir / "SKILL.md").is_file()
    assert (out_dir / "provenance.json").is_file()


def test_generation_never_touches_claude_skills(sroot):
    task_id = _new_task(sroot, "Fix login bug")
    r = _from_task(sroot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (sroot / ".claude" / "skills").exists(), (
        "a generated draft must never be written into the LIVE, core-managed skill set"
    )


# ---------------------------------------------------------------------------
# `--out` under `.claude/skills/` is refused (issue #133, Cyra LOW — PR #132
# review follow-up). An operator-explicit `--out .claude/skills/<x>`
# previously bypassed the drafts-only/human-review boundary this command is
# architected around (`_atomic_write_bytes` writes unconditionally and never
# routed through `check_manifest_write_gate`). Path-normalized FIRST: a
# literal path, the root itself, a `..` traversal, and a symlink that
# resolves there are all caught the same way — refusal is unconditional,
# `--force` does not clear it, and nothing is ever written to disk once it
# fires.
# ---------------------------------------------------------------------------

def test_out_under_claude_skills_refused_literal(sroot):
    task_id = _new_task(sroot, "Literal --out under .claude/skills")
    target = sroot / ".claude" / "skills" / "sneaky-skill"
    r = _from_task(sroot, task_id, "--out", str(target))
    assert r.returncode != 0
    assert "claude/skills" in (r.stdout + r.stderr)
    assert not target.exists()
    assert not (sroot / ".claude" / "skills").exists(), (
        "the refusal must fire BEFORE anything (even the parent dir) is created on disk"
    )


def test_out_exactly_claude_skills_root_refused(sroot):
    """`--out` pointing AT `.claude/skills` itself (no subdirectory) is
    refused the same way — the check must catch the forbidden root itself,
    not only paths strictly beneath it."""
    task_id = _new_task(sroot, "Out is the skills root itself")
    target = sroot / ".claude" / "skills"
    r = _from_task(sroot, task_id, "--out", str(target))
    assert r.returncode != 0
    assert "claude/skills" in (r.stdout + r.stderr)


def test_out_under_claude_skills_refused_via_dotdot_traversal(sroot):
    """A `--out` string that never literally contains `.claude/skills` as a
    clean prefix but RESOLVES there via `..` components must be refused
    identically — proves the check compares the RESOLVED path, never a raw
    substring/prefix match against the operator's original argument."""
    task_id = _new_task(sroot, "Dotdot traversal into .claude/skills")
    sibling = sroot.parent / "elsewhere"
    sibling.mkdir(exist_ok=True)
    traversal_out = sibling / ".." / sroot.name / ".claude" / "skills" / "via-dotdot"
    assert ".." in traversal_out.parts  # sanity: this really is a traversal string
    r = _from_task(sroot, task_id, "--out", str(traversal_out))
    assert r.returncode != 0
    assert "claude/skills" in (r.stdout + r.stderr)
    assert not (sroot / ".claude" / "skills").exists()


def test_out_under_claude_skills_refused_via_symlink(sroot):
    """A `--out` reached through a symlink whose target resolves under
    `.claude/skills/` must be refused identically to the literal path —
    proves the check dereferences symlinks (`Path.resolve()`) before
    comparing, never just the literal `--out` string (C1-style containment,
    same discipline `check_manifest_write_gate` already applies elsewhere in
    this file)."""
    task_id = _new_task(sroot, "Symlink into .claude/skills")
    (sroot / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    link_parent = sroot / "elsewhere"
    link_parent.mkdir(exist_ok=True)
    link = link_parent / "sneaky-link"
    link.symlink_to(sroot / ".claude" / "skills")

    r = _from_task(sroot, task_id, "--out", str(link / "via-symlink"))
    assert r.returncode != 0
    assert "claude/skills" in (r.stdout + r.stderr)
    assert not any((sroot / ".claude" / "skills").iterdir()), (
        "nothing must land in the live skill set even reached through the symlink"
    )


def test_out_under_claude_skills_refused_even_with_force(sroot):
    """`--force` governs the SEPARATE non-empty-target-directory conflict
    only (below) — it must never clear the `.claude/skills/` boundary
    refusal."""
    task_id = _new_task(sroot, "Force does not override the boundary")
    target = sroot / ".claude" / "skills" / "sneaky-skill"
    r = _from_task(sroot, task_id, "--out", str(target), "--force")
    assert r.returncode != 0
    assert "claude/skills" in (r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# --out / --force conflict handling (mirrors `audit export`'s own precedent).
# ---------------------------------------------------------------------------

def test_out_dir_conflict_refused_without_force(sroot):
    task_id = _new_task(sroot, "Conflict check")
    r1 = _from_task(sroot, task_id)
    assert r1.returncode == 0, r1.stdout + r1.stderr

    r2 = _from_task(sroot, task_id)
    assert r2.returncode != 0
    assert "already exists and is not empty" in (r2.stdout + r2.stderr)
    assert "--force" in (r2.stdout + r2.stderr)


def test_out_dir_force_overwrites(sroot):
    task_id = _new_task(sroot, "Force overwrite check")
    r1 = _from_task(sroot, task_id)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    out_dir = Path(r1.stdout.splitlines()[0].split("->")[-1].strip())

    _set_task(sroot, task_id, "--add-note", "a note added between the two generations", "--by", "Ada")
    r2 = _from_task(sroot, task_id, "--out", str(out_dir), "--force")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    skill_text = (out_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "a note added between the two generations" in skill_text


def test_custom_out_dir(sroot, tmp_path):
    task_id = _new_task(sroot, "Custom out check")
    custom = tmp_path / "my-custom-drafts" / "widget-skill"
    r = _from_task(sroot, task_id, "--out", str(custom))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (custom / "SKILL.md").is_file()
    assert (custom / "provenance.json").is_file()


# ---------------------------------------------------------------------------
# Unknown task / required flags.
# ---------------------------------------------------------------------------

def test_unknown_task_id_refused(sroot):
    r = _from_task(sroot, "T-nope")
    assert r.returncode != 0
    assert "no such task" in (r.stdout + r.stderr)


def test_harness_flag_is_required(sroot):
    task_id = _new_task(sroot, "Requires harness")
    r = _run(sroot, "skill", "from-task", task_id)
    assert r.returncode == 2  # argparse required= usage error


# ---------------------------------------------------------------------------
# Doc-accuracy regression (issue #133, Reid LOW): docs/STATE_LAYER.md used to
# reference a `--slug` flag that never existed on this command — `<slug>` is
# always a placeholder for the auto-derived output directory name, never an
# operator-supplied CLI parameter. Pins the REAL flag set directly against
# `--help` output, so a future doc claiming a flag that isn't here is caught
# by test drift, not just prose review.
# ---------------------------------------------------------------------------

def test_help_lists_exactly_the_real_flags_no_phantom_slug(sroot):
    r = _run(sroot, "skill", "from-task", "--help")
    assert r.returncode == 0, r.stdout + r.stderr
    help_text = r.stdout
    assert "--slug" not in help_text, "no --slug flag exists — the slug is always auto-derived"
    for flag in ("--out", "--force", "--harness", "--session", "--persona", "--json"):
        assert flag in help_text, f"expected real flag {flag!r} missing from --help output"


# ---------------------------------------------------------------------------
# Read-only against the task record; accountability via the ledger only.
# ---------------------------------------------------------------------------

def test_generation_does_not_mutate_task_record(sroot):
    task_id = _new_task(sroot, "Immutable check")
    before = json.loads(_task_path(sroot, task_id).read_text())

    r = _from_task(sroot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr

    after = json.loads(_task_path(sroot, task_id).read_text())
    assert after == before, "tessctl skill from-task must never mutate the source task record"


def test_skill_generated_ledger_event_is_logged(sroot):
    task_id = _new_task(sroot, "Ledger check")
    before_count = len(_events(sroot, task_id))

    r = _from_task(sroot, task_id, harness="ada")
    assert r.returncode == 0, r.stdout + r.stderr

    events = _events(sroot, task_id)
    assert len(events) == before_count + 1
    # NOTE: `log view --task` sorts across shards by `ts` alone (second
    # resolution) — a same-second event in a DIFFERENT origin shard than
    # the task's creation event is not guaranteed to sort strictly after
    # it (documented, pre-existing cross-shard ordering imprecision; see
    # `_skill_collect_task_events`'s own docstring). Find the new event by
    # its event class instead of assuming list position.
    skill_events = [e for e in events if e["event"] == "skill_generated"]
    assert len(skill_events) == 1
    new_event = skill_events[0]
    assert new_event["refs"]["task"] == task_id
    assert new_event["actor"]["harness"] == "ada"
    assert "draft skill" in new_event["summary"]
    assert task_id in new_event["summary"]


def test_skill_generated_event_visible_to_subsequent_audit_export(sroot, tmp_path):
    task_id = _new_task(sroot, "Cross-subsystem check")
    r = _from_task(sroot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr

    pack_dir = tmp_path / "pack"
    a = _run(sroot, "audit", "export", "--task", task_id, "--out", str(pack_dir))
    assert a.returncode == 0, a.stdout + a.stderr
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    all_events = [e for shard in manifest["shards"] for e in shard["events"]]
    assert any(e["event"] == "skill_generated" for e in all_events), (
        "the skill_generated ledger line must be visible to a later audit export — "
        "same accountability ledger, not a side channel"
    )


# ---------------------------------------------------------------------------
# --json / human output.
# ---------------------------------------------------------------------------

def test_json_output_includes_scaffold_and_out_dir(sroot):
    task_id = _new_task(sroot, "JSON output check")
    r = _from_task(sroot, task_id, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["scaffold"]["source_task"]["id"] == task_id
    assert Path(payload["out_dir"]).is_dir()


def test_human_output_shows_draft_disclaimer(sroot):
    task_id = _new_task(sroot, "Human output check")
    r = _from_task(sroot, task_id)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "DRAFT — unreviewed" in r.stdout


# ---------------------------------------------------------------------------
# Slug determinism / collision safety.
# ---------------------------------------------------------------------------

def test_slug_derived_from_title_and_task_id_suffix(sroot, engine):
    task_id = "T-20260720-fix-login-bug-9c1e"
    record = {"id": task_id, "title": "Fix login bug!!"}
    slug = engine._skill_slug_for_task(record)
    assert slug == "fix-login-bug-9c1e"


def test_two_tasks_with_same_title_get_distinct_slugs(sroot):
    id_a = _new_task(sroot, "Duplicate title")
    id_b = _new_task(sroot, "Duplicate title")
    assert id_a != id_b

    ra = _from_task(sroot, id_a)
    rb = _from_task(sroot, id_b)
    assert ra.returncode == 0, ra.stdout + ra.stderr
    assert rb.returncode == 0, rb.stdout + rb.stderr
    out_a = Path(ra.stdout.splitlines()[0].split("->")[-1].strip())
    out_b = Path(rb.stdout.splitlines()[0].split("->")[-1].strip())
    assert out_a != out_b


# ---------------------------------------------------------------------------
# Schema / lint coverage (engine-level, no subprocess) — mirrors
# tests/test_task_stuck_packet.py's own `test_ledger_event_schema_accepts_
# blocked` exactly, for the new `skill_generated` class.
# ---------------------------------------------------------------------------

def test_ledger_event_schema_accepts_skill_generated(engine):
    schema = engine.load_contract_schema(REPO_ROOT, "ledger-event")
    base_dir = REPO_ROOT / "core" / "contracts"
    inst = {
        "ts": "2026-07-20T00:00:00Z",
        "actor": {"harness": "h", "model": None, "session": None, "persona": None},
        "event": "skill_generated",
        "refs": {"task": "T-20260720-x-aaaa", "mission": None},
        "summary": "x",
        "seq": 0,
        "prev_hash": "0" * 64,
        "hash": "a" * 64,
    }
    violations = engine.schema_validate(inst, schema, schema, base_dir)
    assert violations == []


def test_lint_ledger_event_skill_generated_requires_task_ref(engine):
    inst = {
        "event": "skill_generated",
        "refs": {"task": None, "mission": None},
    }
    violations = engine._lint_ledger_event(inst)
    assert any("task-scoped" in v for v in violations)


def test_skill_generated_is_in_ledger_events_and_task_scoped_constants(engine):
    assert "skill_generated" in engine.LEDGER_EVENTS
    assert "skill_generated" in engine.LEDGER_TASK_SCOPED_EVENTS
