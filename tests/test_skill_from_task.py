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
  * ★ CRITICAL (Cyra, live-reproduced on macOS, PR #140 re-review): the
    `.claude/skills/` refusal is INODE-IDENTITY based (`os.path.samefile`,
    mirroring PR #117's proven `tessctl memory adopt` fix verbatim), never
    a case-sensitive string comparison — a `Path.is_relative_to()` string
    check missed a case-folded `--out .CLAUDE/skills/x` on macOS APFS/
    Windows NTFS (both case-insensitive) while CI (Linux, case-sensitive)
    stayed green. Covered two ways: an unconditional, FS-independent test
    of the comparison PRIMITIVES directly (a same-inode, differently-typed
    pair constructed via symlink, so it holds on ext4 too, not just an
    opportunistically case-insensitive runner) and an opportunistic,
    runtime-gated test of the exact real-world scenario end-to-end via the
    CLI, whenever the runner's OWN filesystem actually case-folds.
  * MED (Cyra): the `skill_generated` ledger event records the RESOLVED
    `--out` target, so a later ledger/audit review can detect an
    out-of-bounds write after the fact.
  * LOW (Reid): a relative `--out` is anchored to `root` (TESS_ROOT), never
    the caller's `Path.cwd()` — proven by invoking from a cwd that is
    deliberately not `root`.
  * Issue #141 (LOW, Reid — follow-up from PR #140's re-review of commit
    `0b9e860`): a CI regression-net guard that fires on EVERY CI run,
    regardless of the runner's OS/filesystem — unlike the opportunistic
    real-case-fold test (which SKIPS on a case-sensitive runner) or the
    FS-independent primitive test (which, on its own, would not catch a
    revert of `_skill_reject_out_under_claude_skills` back to a string
    comparison). Asserts the MECHANISM: the refusal genuinely invokes
    `os.path.samefile`, not just that it produces the right answer today.
  * Issue #141 (LOW, Cyra — the other half of the same issue, resolved
    2026-07-21): the refusal now ALSO covers the operator's GLOBAL, per-
    machine `~/.claude/skills` (`CLAUDE_SKILLS_LIVE_DIR` resolved against
    `Path.home()`, not just `root`) — confirmed empirically that the host
    loads skills from there too, a distinct directory from any repo's
    local `.claude/skills/`. Covered with the SAME rigor as the repo-local
    boundary: a literal `--out` under a controlled fake `$HOME` is refused
    (never touching the real operator machine); an FS-independent,
    same-inode/differently-spelled alias (constructed via symlink, holding
    on every POSIX filesystem regardless of case-folding) is refused via
    `_skill_global_claude_skills_root`/`_path_is_prefix` directly; a
    legitimate default drafts write still succeeds with the global check
    active; `--force` does not override the global refusal either; and
    `_skill_global_claude_skills_root()` itself returns `None` (never
    raises, never silently permits) when `Path.home()` cannot determine a
    home directory at all — proven by forcing that exact `RuntimeError`.
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


def _run_with_home(root, home, *args):
    """Same as `_run` but with `$HOME` overridden for the subprocess —
    issue #141 (Cyra) global `~/.claude/skills` coverage below. Never
    touches the real operator machine's actual home directory: `home` is
    always a throwaway `tmp_path` subdirectory the test itself controls,
    and `Path.home()` (POSIX) resolves via the `HOME` env var first, so
    overriding it here is a genuine, faithful simulation of "a different
    operator's global skills dir", not a mock of the check itself."""
    env = {**os.environ, "TESS_ROOT": str(root), "HOME": str(home)}
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


def _fs_is_case_insensitive(tmp_path) -> bool:
    """Runtime detection (never a hardcoded platform-name guess) of whether
    the ACTUAL filesystem backing `tmp_path` folds case — macOS APFS and
    Windows NTFS do by default; Linux ext4/overlay (this repo's CI runner)
    does not. Used to gate the opportunistic real-case-fold CLI test below
    (PR #140 re-review, Cyra CRITICAL): writes a probe file under one
    spelling and checks whether a DIFFERENTLY-cased spelling reads it back."""
    probe_dir = tmp_path / f"_case_probe_{os.getpid()}"
    probe_dir.mkdir(exist_ok=True)
    (probe_dir / "CaseProbeFile").write_text("x", encoding="utf-8")
    return (probe_dir / "caseprobefile").exists()


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
# ★ CRITICAL regression (Cyra, live-reproduced on macOS APFS, PR #140
# re-review — the SAME bug class as PR #117's Cyra HOLE 1): the first
# version of the `.claude/skills/` refusal above compared `Path.resolve()`
# output with `Path.is_relative_to()` — a case-SENSITIVE STRING comparison.
# macOS APFS (and Windows NTFS) are case-INSENSITIVE, so `--out
# .CLAUDE/skills/evil-skill` resolved to a DIFFERENT string than
# `.claude/skills` even though it is THE SAME DIRECTORY on disk — the
# string check silently passed and the write landed in the real live skill
# set. CI (Linux, case-sensitive) never exercised this path, which is
# EXACTLY why it shipped green — so these tests are written to hold
# regardless of the runner's own filesystem case-(in)sensitivity, never by
# relying on it.
# ---------------------------------------------------------------------------

def test_inode_identity_catches_same_location_naive_string_check_would_miss(engine, tmp_path):
    """FS-INDEPENDENT regression test — exercises the comparison PRIMITIVES
    directly (`_paths_are_same_location` / `_path_is_prefix`,
    `.tess/bin/tessctl`, reused verbatim from PR #117's own proven
    `tessctl memory adopt` fix), not just the CLI on whatever filesystem
    happens to be under the test runner. Native case-folding itself can
    only be reproduced on an actually case-insensitive filesystem (see the
    opportunistic test below) — but the ROOT CAUSE this regression guards
    against is broader than case-folding alone: it is ANY same-inode pair
    of paths whose STRINGS differ, which a symlink reproduces identically
    on every POSIX filesystem (ext4, APFS, ...), independent of case rules.
    Deliberately calls the comparison with a RAW, NOT-`.resolve()`d child
    path — proving the safety property holds at the primitive layer itself,
    not only because `Path.resolve()` happens to normalize it away first.
    """
    real_skills = tmp_path / ".claude" / "skills"
    real_skills.mkdir(parents=True)
    forbidden = real_skills.resolve()

    # A same-INODE, differently-SPELLED alias — the portable stand-in for
    # "macOS/Windows treat these two spellings as the same directory
    # natively." Deliberately a DISTINCT name (not a literal case-variant
    # of `.claude`) so this construction itself works identically whether
    # the underlying filesystem case-folds or not (a literal `.CLAUDE`
    # symlink next to an existing `.claude` would collide/fail to even
    # create on a case-insensitive filesystem, since the OS would see them
    # as the same path already).
    alias_parent = tmp_path / "sneaky-alias-parent"
    alias_parent.mkdir()
    alias = alias_parent / "alias-for-skills"
    alias.symlink_to(real_skills)
    raw_child = alias / "evil-skill"  # NOT .resolve()d — simulates a pre-normalization view

    # The naive STRING check this replaced would MISS it (this is the bug):
    assert raw_child.is_relative_to(forbidden) is False, (
        "sanity: the raw alias path must NOT look like a string-prefix match — "
        "otherwise this test isn't proving anything about inode vs. string identity"
    )
    # The INODE-based check (the fix) catches it:
    assert engine._paths_are_same_location(forbidden, alias) is True
    assert engine._path_is_prefix(forbidden, raw_child) is True
    assert engine._path_is_prefix(forbidden, alias) is True

    # Negative control — a genuinely unrelated location (no shared inode
    # anywhere in its ancestry) must NOT be flagged; this isn't a blanket
    # false-positive machine.
    unrelated = tmp_path / "totally-unrelated" / "skills" / "fine-skill"
    unrelated.parent.mkdir(parents=True)
    assert engine._path_is_prefix(forbidden, unrelated) is False

    # Full-integration bonus (still FS-independent): the actual production
    # entrypoint, called with the RAW alias path, also refuses — locking in
    # that `_skill_reject_out_under_claude_skills` really does route through
    # `_path_is_prefix`/`_paths_are_same_location` end to end, not just that
    # those primitives are independently correct in isolation.
    fake_root = tmp_path  # only `root / CLAUDE_SKILLS_LIVE_DIR` is read
    with pytest.raises(engine.SkillError, match="claude/skills"):
        engine._skill_reject_out_under_claude_skills(fake_root, raw_child)


def test_out_under_claude_skills_refusal_routes_through_os_path_samefile(engine, tmp_path, monkeypatch):
    """CI regression-net guard (issue #141, Reid LOW — re-review of commit
    `0b9e860`): asserts the MECHANISM, not just the FS behavior. On Linux CI
    the real case-fold test below SKIPS (a case-sensitive filesystem cannot
    construct the scenario at all), and the FS-independent primitive test
    above passes against BOTH the fixed code and the OLD, vulnerable
    `Path.is_relative_to()` string-compare code (it exercises the
    primitives directly via a symlink alias, never the actual
    `_skill_reject_out_under_claude_skills` comparison path for an ordinary,
    non-symlinked target). Net effect before this test existed: a future
    revert of `_skill_reject_out_under_claude_skills` back to
    `Path.is_relative_to()` would NOT be caught by anything that runs on
    Linux CI — the regression would only ever surface on a developer's
    macOS/Windows machine.

    Fixed by monkeypatching `os.path.samefile` — the one syscall the
    inode-identity fix routes through (`_paths_are_same_location` ->
    `os.path.samefile`) — and asserting `_skill_reject_out_under_claude_skills`
    genuinely invokes it for an ordinary refused `--out`. This proves the
    refusal routes through inode identity, not a string comparison, and
    fires on every CI run regardless of the runner's own filesystem
    case-(in)sensitivity."""
    real_skills = tmp_path / ".claude" / "skills"
    real_skills.mkdir(parents=True)

    calls = []
    real_samefile = os.path.samefile

    def spy(a, b):
        calls.append((a, b))
        return real_samefile(a, b)

    monkeypatch.setattr(os.path, "samefile", spy)

    target = tmp_path / ".claude" / "skills" / "sneaky-skill"
    with pytest.raises(engine.SkillError, match="claude/skills"):
        engine._skill_reject_out_under_claude_skills(tmp_path, target)

    assert calls, (
        "_skill_reject_out_under_claude_skills did not call os.path.samefile "
        "at all while refusing this --out target. If this assertion ever "
        "fires, the refusal has been reverted to a string comparison (e.g. "
        "Path.is_relative_to()) and the case-fold/inode-identity bug class "
        "(#133 / PR #140's CRITICAL re-review fix) has silently regressed — "
        "this guard exists specifically to catch that on Linux CI, where "
        "the case-fold class of test below cannot even run."
    )


def test_out_under_claude_skills_refused_via_real_case_fold_when_fs_supports_it(sroot, tmp_path):
    """Opportunistic, runtime-gated (never hardcoded by platform name) proof
    of the EXACT scenario Cyra reproduced live: `--out .CLAUDE/skills/
    evil-skill` (upper-case) against a real, existing lower-case
    `.claude/skills`, through the FULL CLI end-to-end path. Only runs when
    the test runner's OWN filesystem is actually case-insensitive (macOS
    APFS, Windows NTFS — both real deployment targets); cleanly skipped
    (never silently "passed") on a case-sensitive runner such as this
    repo's Linux CI, where a native case-fold literally cannot be
    constructed at all — see the unconditional, FS-independent primitive
    test above for the guarantee that holds regardless."""
    if not _fs_is_case_insensitive(tmp_path):
        pytest.skip(
            "this filesystem is case-sensitive (no native case-fold to reproduce here) — "
            "see test_inode_identity_catches_same_location_naive_string_check_would_miss "
            "for the FS-independent guarantee"
        )
    (sroot / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    task_id = _new_task(sroot, "Real case-fold bypass probe")
    case_variant_target = sroot / ".CLAUDE" / "skills" / "evil-skill"

    r = _from_task(sroot, task_id, "--out", str(case_variant_target))
    assert r.returncode != 0, (
        "CRITICAL: a case-folded --out must be refused — "
        f"got exit 0, stdout={r.stdout!r}"
    )
    assert "claude/skills" in (r.stdout + r.stderr).lower()
    assert not any((sroot / ".claude" / "skills").iterdir()), (
        "nothing must land in the real live skill set via the case-folded path"
    )


# ---------------------------------------------------------------------------
# Issue #141 (Cyra LOW, resolved 2026-07-21) — the SECOND forbidden root:
# the operator's GLOBAL, per-machine `~/.claude/skills`, not just the
# in-repo `root / ".claude/skills"` covered above. Confirmed empirically
# that the Claude Code host ALSO loads skills from there — a real,
# populated directory distinct from any repo's local `.claude/skills/`.
# Every test below is FS-independent: none of it relies on the test
# runner's own filesystem happening to case-fold (unlike the opportunistic
# real-case-fold test above, which is deliberately runtime-gated and skips
# on a case-sensitive runner) — and none of it ever touches the real
# operator machine's actual `$HOME`; `HOME` is always overridden to a
# throwaway `tmp_path` subdirectory the test itself owns.
# ---------------------------------------------------------------------------

def test_out_under_global_claude_skills_refused_literal(sroot, tmp_path):
    """A literal `--out` resolving under a (fake, controlled) `~/.claude/
    skills` is refused via the full CLI end-to-end path — mirrors
    `test_out_under_claude_skills_refused_literal` exactly, but for the
    GLOBAL root instead of the in-repo one."""
    fake_home = tmp_path / "fake-home-literal"
    fake_home.mkdir()
    task_id = _new_task(sroot, "Literal --out under global ~/.claude/skills")
    target = fake_home / ".claude" / "skills" / "sneaky-skill"

    r = _run_with_home(
        sroot, fake_home, "skill", "from-task", task_id, "--harness", "ada", "--out", str(target),
    )
    assert r.returncode != 0
    assert "claude/skills" in (r.stdout + r.stderr)
    assert not target.exists()
    assert not (fake_home / ".claude" / "skills").exists(), (
        "the refusal must fire BEFORE anything (even the parent dir) is created on disk"
    )


def test_out_under_global_claude_skills_refused_even_with_force(sroot, tmp_path):
    """`--force` governs the non-empty-target-directory conflict only — it
    must not clear the GLOBAL boundary refusal either, mirroring the
    in-repo root's own `--force` test."""
    fake_home = tmp_path / "fake-home-force"
    fake_home.mkdir()
    task_id = _new_task(sroot, "Force does not override the global boundary")
    target = fake_home / ".claude" / "skills" / "sneaky-skill"

    r = _run_with_home(
        sroot, fake_home, "skill", "from-task", task_id, "--harness", "ada",
        "--out", str(target), "--force",
    )
    assert r.returncode != 0
    assert "claude/skills" in (r.stdout + r.stderr)


def test_out_under_global_claude_skills_refused_via_inode_identity_case_variant(engine, tmp_path, monkeypatch):
    """FS-INDEPENDENT case-variant regression for the GLOBAL root — mirrors
    `test_inode_identity_catches_same_location_naive_string_check_would_miss`
    exactly, but proves the GLOBAL `~/.claude/skills` boundary specifically
    (a `fake_root` with NO `.claude/skills` anywhere under it is used, so
    the in-repo check above cannot be what fires here — only the global
    one can be responsible for the refusal). Constructs a same-INODE,
    differently-spelled alias via a symlink — the portable stand-in for "a
    case-insensitive filesystem treats these two spellings as the same
    directory natively" that holds on EVERY POSIX filesystem, ext4
    (this repo's Linux CI) included, never relying on the runner's own
    case-folding the way a literal `.CLAUDE` vs `.claude` variant would."""
    fake_home = tmp_path / "fake-home-inode"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    real_global_skills = fake_home / ".claude" / "skills"
    real_global_skills.mkdir(parents=True)
    forbidden = real_global_skills.resolve()

    alias_parent = tmp_path / "sneaky-global-alias-parent"
    alias_parent.mkdir()
    alias = alias_parent / "alias-for-global-skills"
    alias.symlink_to(real_global_skills)
    raw_child = alias / "evil-skill"  # NOT .resolve()d — pre-normalization view

    # Sanity: the naive STRING check the repo-local fix already replaced
    # would MISS this too — same bug class, same proof shape.
    assert raw_child.is_relative_to(forbidden) is False, (
        "sanity: the raw alias path must not look like a string-prefix match"
    )

    # The primitive layer catches it (reused verbatim, not re-forked):
    assert engine._paths_are_same_location(forbidden, alias) is True
    assert engine._path_is_prefix(forbidden, raw_child) is True

    # `_skill_global_claude_skills_root()` resolves to the SAME real
    # location `HOME` was pointed at.
    assert engine._skill_global_claude_skills_root() == forbidden

    # Full-integration: a `fake_root` that has NO `.claude/skills` anywhere
    # under it — proves the GLOBAL check alone is what refuses this, not
    # the in-repo one, which has nothing to match here.
    fake_root = tmp_path / "unrelated-repo-root"
    fake_root.mkdir()
    with pytest.raises(engine.SkillError, match="claude/skills"):
        engine._skill_reject_out_under_claude_skills(fake_root, raw_child)


def test_default_out_dir_still_succeeds_with_global_check_active(sroot, tmp_path):
    """The legitimate default drafts write (no `--out` at all — lands under
    `.tess/state/skills/drafts/<slug>`) still succeeds once the global
    `~/.claude/skills` check is active — proves the new boundary doesn't
    accidentally reject an ordinary, non-conflicting write just because a
    (fake, controlled, otherwise-unrelated) `$HOME` now resolves and gets
    checked on every call."""
    fake_home = tmp_path / "fake-home-legit-write"
    fake_home.mkdir()
    task_id = _new_task(sroot, "Legit drafts write with global check active")

    r = _run_with_home(sroot, fake_home, "skill", "from-task", task_id, "--harness", "ada")
    assert r.returncode == 0, r.stdout + r.stderr
    out_dir = Path(r.stdout.splitlines()[0].split("->")[-1].strip())
    assert out_dir.parent.parent == sroot / ".tess" / "state" / "skills"
    assert out_dir.parent.name == "drafts"
    assert (out_dir / "SKILL.md").is_file()
    assert (out_dir / "provenance.json").is_file()


def test_custom_out_dir_outside_both_roots_still_succeeds_with_global_check_active(sroot, tmp_path):
    """A legitimate CUSTOM `--out` (outside both the in-repo AND the global
    forbidden roots) still succeeds — the global check must not over-reject
    a target that merely happens to share no relationship with either
    boundary."""
    fake_home = tmp_path / "fake-home-custom"
    fake_home.mkdir()
    task_id = _new_task(sroot, "Custom --out with global check active")
    custom = tmp_path / "my-custom-drafts" / "widget-skill"

    r = _run_with_home(sroot, fake_home, "skill", "from-task", task_id, "--harness", "ada", "--out", str(custom))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (custom / "SKILL.md").is_file()
    assert (custom / "provenance.json").is_file()


def test_skill_global_claude_skills_root_returns_none_when_home_undeterminable(engine, monkeypatch):
    """`_skill_global_claude_skills_root()`'s ONE `None`-returning branch:
    `Path.home()`'s own documented failure mode (`RuntimeError('Could not
    determine home directory.')` — no `HOME` env var and no password-
    database entry). Forced directly (rather than relying on actually
    unsetting `HOME` in this process, which on POSIX usually still resolves
    via the `pwd` module and would NOT reliably reproduce the failure) —
    proving the helper degrades to `None`, never raises out to the caller,
    and never fabricates a fake forbidden root."""
    def _raise_no_home():
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(engine.Path, "home", staticmethod(_raise_no_home))
    assert engine._skill_global_claude_skills_root() is None


def test_reject_out_check_does_not_crash_when_home_undeterminable(engine, tmp_path, monkeypatch):
    """When the global-root helper returns `None`, `_skill_reject_out_
    under_claude_skills` must not crash and must still enforce the
    in-repo boundary correctly — the global check degrading to "nothing to
    check" must never take the whole function down with it, and must never
    accidentally suppress the repo-local check either."""
    def _raise_no_home():
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(engine.Path, "home", staticmethod(_raise_no_home))

    fake_root = tmp_path / "repo-root"
    (fake_root / ".claude" / "skills").mkdir(parents=True)

    # The in-repo boundary still fires correctly.
    with pytest.raises(engine.SkillError, match="claude/skills"):
        engine._skill_reject_out_under_claude_skills(fake_root, fake_root / ".claude" / "skills" / "sneaky")

    # An ordinary, unrelated --out still resolves cleanly (no crash, no
    # spurious refusal) even though the global helper can't determine home.
    legit = fake_root / "drafts" / "some-skill"
    resolved = engine._skill_reject_out_under_claude_skills(fake_root, legit)
    assert resolved == legit.resolve()


def test_relative_out_dir_anchored_to_root_not_cwd(sroot, tmp_path):
    """LOW (Reid, PR #140 re-review): a relative `--out` is anchored to
    ROOT, never the caller's `Path.cwd()`. The forbidden-root check itself
    is anchored to `root` — anchoring the candidate `--out` to whatever
    the shell's cwd happens to be (which need not equal `root`; `TESS_ROOT`
    is an independent env var) rested the two sides of that comparison on
    different, only-sometimes-equal reference frames. Invokes from a cwd
    that is deliberately NOT `root` to prove the anchor is now correct."""
    task_id = _new_task(sroot, "Relative --out anchor check")
    elsewhere_cwd = tmp_path / "elsewhere-cwd"
    elsewhere_cwd.mkdir()
    env = {**os.environ, "TESS_ROOT": str(sroot)}
    r = subprocess.run(
        [sys.executable, str(sroot / ".tess" / "bin" / "tessctl"), "skill", "from-task", task_id,
         "--harness", "ada", "--out", "relative-drafts/my-skill"],
        cwd=str(elsewhere_cwd), env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    out_dir = Path(r.stdout.splitlines()[0].split("->")[-1].strip())
    assert out_dir == sroot / "relative-drafts" / "my-skill", (
        "a relative --out must resolve against TESS_ROOT, not the caller's shell cwd"
    )
    assert not (elsewhere_cwd / "relative-drafts").exists(), (
        "must NOT have landed relative to the caller's cwd"
    )


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


def test_skill_generated_ledger_event_records_resolved_out_dir(sroot):
    """MED (Cyra, PR #140 re-review): the `skill_generated` ledger event
    must record the RESOLVED `--out` target — without it, a later ledger/
    audit review has no way to detect (after the fact) that a generation
    landed somewhere unexpected; the event previously recorded only THAT a
    draft was scaffolded, never WHERE."""
    task_id = _new_task(sroot, "Ledger records out_dir")
    r = _from_task(sroot, task_id, harness="ada")
    assert r.returncode == 0, r.stdout + r.stderr
    out_dir = Path(r.stdout.splitlines()[0].split("->")[-1].strip())

    events = _events(sroot, task_id)
    skill_events = [e for e in events if e["event"] == "skill_generated"]
    assert len(skill_events) == 1
    assert str(out_dir.resolve()) in skill_events[0]["summary"], (
        "the resolved --out target must appear in the ledger summary"
    )


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
