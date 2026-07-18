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
