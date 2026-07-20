"""
DATA-LEAK-SAFETY (issue #92), fix 1 — reconcile .gitignore with the
manifest's never_touch set.

Uses `git check-ignore --no-index` against THIS repo's own .gitignore (not a
synthetic copy): --no-index evaluates the pattern rules only, independent of
whether a path happens to already be tracked in history — the correct check
for "would a FRESH install (create-tess `git init`s empty, this exact
.gitignore copied verbatim) ever track this path". `git ls-files` separately
confirms this repo's OWN currently-tracked set still contains exactly the
deliberately-shipped framework templates (documented, not accidental).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HAS_GIT = shutil.which("git") is not None
pytestmark = pytest.mark.skipif(not HAS_GIT, reason="git required")

REPO_ROOT = Path(__file__).resolve().parent.parent


def _check_ignore(rel: str) -> bool:
    """True if `rel` is ignored by THIS repo's .gitignore, evaluated
    independent of tracked status (--no-index)."""
    r = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "check-ignore", "--no-index", "-q", rel],
    )
    return r.returncode == 0


def _tracked(rel: str) -> bool:
    r = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--error-unmatch", rel],
        capture_output=True, text=True,
    )
    return r.returncode == 0


# ---------------------------------------------------------------------------
# Private paths must be ignored by the RULE (protects a fresh install even
# though some of these specific paths remain tracked in THIS repo's own
# history via the documented "already-tracked" grandfather — see the .md
# comment block in .gitignore).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rel", [
    "operator/profile.json",
    "operator/anything-else.md",
    "operator/anything.json",
    "kb/wiki/log.md",
    "kb/wiki/index.md",
    "kb/wiki/some-new-file.md",
    "kb/raw/some-raw-note.md",
    "notes.local.md",
    "some/nested/dir/shadow.local.md",
    "clients/AcmeCorp/anything.md",
    ".env",
    ".env.production",
    "missions/m1/mission.md",
    "missions/m1/verdicts/x.md",
    "UPGRADE-NOTES.md",
    ".mcp.json",
    ".claude/vault/vault.age",
    ".claude/vault/identity.age",
    "clients/AcmeCorp/.vault/blob.age",
    # issue #110 (found reviewing #105) — memory/tasks/ledger were the gap:
    # only .tess/state/locks/* had a content-level ignore in Phase 0.1.
    ".tess/state/memory/real-note.md",
    ".tess/state/memory/nested/dir/note.json",
    ".tess/state/tasks/graph.json",
    ".tess/state/ledger/entry.md",
    ".tess/state/locks/task.lock",
    # issue #131 (Phase 0.6, SKILL DRAFT SCAFFOLD) — a FIFTH .tess/state/**
    # subsystem, same content-level ignore.
    ".tess/state/skills/drafts/fix-login-bug-9c1e/SKILL.md",
    ".tess/state/skills/drafts/fix-login-bug-9c1e/provenance.json",
    # PR-2 (Agent Receipt EMIT wiring) — a SIXTH .tess/state/** subsystem,
    # same content-level ignore.
    ".tess/state/receipts/chain.jsonl",
    ".tess/state/receipts/nested/other-chain.jsonl",
])
def test_private_path_is_ignored(rel):
    assert _check_ignore(rel), f"{rel} must be gitignored (private overlay data)"


# ---------------------------------------------------------------------------
# Deliberately shipped framework templates: NOT ignored by the rule (a fresh
# install keeps them trackable), AND currently tracked in this repo's own
# history (the shipped default).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rel", [
    "operator/build-facts-stub.md",
    "operator/identity-stub.md",
    "operator/org-channels.md",
    "operator/user-profile.md",
    "clients/_template/CLAUDE.md",
    "missions/README.md",
    ".env.example",
    ".claude/vault/.gitkeep",
    ".claude/vault/vault.registry.json",
    # issue #110 — the .gitkeep placeholder in each .tess/state/** subdir
    # must survive the new content-ignore rule (the `!` re-include) and
    # stay tracked, exactly like every other precedent-bucket .gitkeep.
    ".tess/state/memory/.gitkeep",
    ".tess/state/tasks/.gitkeep",
    ".tess/state/ledger/.gitkeep",
    ".tess/state/locks/.gitkeep",
    # issue #131 (Phase 0.6) — same for the skills/drafts scaffold structure.
    ".tess/state/skills/.gitkeep",
    # PR-2 (Agent Receipt EMIT wiring) — same for the receipts chain-store
    # structure.
    ".tess/state/receipts/.gitkeep",
])
def test_shipped_template_is_not_ignored_and_is_tracked(rel):
    assert not _check_ignore(rel), f"{rel} is a shipped template and must stay committable"
    assert _tracked(rel), f"{rel} should be tracked in this repo's history"


# ---------------------------------------------------------------------------
# The two files that WERE explicitly un-ignored before this PR (the exact
# regression Cyra found) must now fall under the general ignore rule.
# ---------------------------------------------------------------------------

def _gitignore_rule_lines() -> set[str]:
    """Actual gitignore pattern LINES (comments/blank lines stripped) —
    avoids false positives from prose in explanatory comments that happens
    to mention a pattern by name."""
    lines = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")}


def test_kb_wiki_log_and_index_no_longer_explicitly_unignored():
    rules = _gitignore_rule_lines()
    assert "!kb/wiki/index.md" not in rules
    assert "!kb/wiki/log.md" not in rules
    assert _check_ignore("kb/wiki/log.md")
    assert _check_ignore("kb/wiki/index.md")


def test_operator_profile_json_has_no_reinclude_override():
    """The one file create-tess's writeProfile() unconditionally overwrites
    with real identity must get NO `!` exception — unlike the four static
    operator/*.md stubs."""
    rules = _gitignore_rule_lines()
    assert "!operator/profile.json" not in rules
    assert _check_ignore("operator/profile.json")


# ---------------------------------------------------------------------------
# Legitimately-tracked, non-private framework/repo content must NOT be
# gitignored — never_touch also covers "tessctl must not manage this" paths
# that are simply out of the engine's write-scope, not private data.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rel", [
    "README.md",
    "docs/STATUS.md",
    "adapters/README.md",
    "starter/CLAUDE.md",
    "main.py",
    "pyproject.toml",
    "uv.lock",
])
def test_non_private_framework_content_stays_unignored(rel):
    assert not _check_ignore(rel), f"{rel} is legitimate tracked framework content, not private data"


# ---------------------------------------------------------------------------
# issue #110 (found reviewing #105) — the literal reproduction: a real
# `git add -A` in a fresh checkout, with no pre-commit hook installed at all
# (the publish-clean gate is opt-in via `tessctl gate install-hooks` — this
# test proves the content-level .gitignore fence holds even when that hook
# was never installed, which is exactly the gap the MEDIUM finding flagged).
# Uses a real temp git repo seeded with THIS repo's own .gitignore, so a
# regression in the actual shipped rules (not a synthetic stand-in) is what
# gets caught.
# ---------------------------------------------------------------------------

def _git(root, *args, check=True):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}\n{r.stdout}")
    return r


@pytest.fixture
def fresh_checkout(tmp_path):
    """A minimal fresh git repo: THIS repo's own .gitignore plus the same
    .tess/state/{memory,tasks,ledger,locks}/.gitkeep scaffold create-tess
    ships, committed as the starting point — i.e. what a real fresh
    instance's tracked history looks like before any real data is written."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@tess.test")
    _git(tmp_path, "config", "user.name", "Test")
    shutil.copy2(REPO_ROOT / ".gitignore", tmp_path / ".gitignore")
    for sub in ("memory", "tasks", "ledger", "locks", "skills"):
        d = tmp_path / ".tess" / "state" / sub
        d.mkdir(parents=True)
        (d / ".gitkeep").write_text("", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "seed: gitignore + empty state scaffold")
    return tmp_path


def test_git_add_dash_a_never_stages_real_state_content_no_hook(fresh_checkout):
    """The exact verify Cyra ran: write real files under memory/tasks/ledger
    (+ locks for parity), `git add -A` with NO pre-commit hook installed at
    all, then confirm none of them staged — only pre-existing .gitkeep stays
    tracked, and `git status` doesn't surface the new files either."""
    for sub in ("memory", "tasks", "ledger", "locks", "skills"):
        (fresh_checkout / ".tess" / "state" / sub / "x.json").write_text(
            "data\n", encoding="utf-8"
        )

    _git(fresh_checkout, "add", "-A")

    staged = _git(fresh_checkout, "diff", "--cached", "--name-only").stdout.split()
    for sub in ("memory", "tasks", "ledger", "locks", "skills"):
        rel = f".tess/state/{sub}/x.json"
        assert rel not in staged, f"{rel} must NOT be staged by a bare `git add -A`"

    status = _git(fresh_checkout, "status", "--porcelain").stdout
    for sub in ("memory", "tasks", "ledger", "locks", "skills"):
        assert f".tess/state/{sub}/x.json" not in status, (
            f".tess/state/{sub}/x.json must not surface in `git status` at all"
        )

    # The .gitkeep placeholders remain the only tracked content in each dir.
    tracked = _git(fresh_checkout, "ls-files", ".tess/state/").stdout.split()
    assert sorted(tracked) == sorted(
        f".tess/state/{sub}/.gitkeep" for sub in ("memory", "tasks", "ledger", "locks", "skills")
    )
