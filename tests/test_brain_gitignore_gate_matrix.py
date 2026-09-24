"""Ignore matrix + a REAL gate-hooked commit for every tracked brain path (spec G14, E1-E3).

`git check-ignore` alone cannot catch the bug that sank two of the three
designs (paths that are not ignored but are refused by the pre-commit
gate), so this suite also commits every tracked brain path through the
instance's installed `tessctl gate install-hooks` hooks and asserts
`publish-clean: OK`. Needs PyYAML (tessctl), like the rest of the suite.
"""
from __future__ import annotations

import pytest

import _brain_oobe_helpers as h

TRACKED = [
    "brain/brain.json", "brain/journal/2026/09/24/1405-claude-abcd1234.md",
    "brain/clients/acme/AGENTS.md", "brain/clients/acme/kb/research/x.md",
    "brain/decisions/D-x.md", "memory/projects/x.md",
    "brain/clients/acme/admin/README.md", "brain/org/seats/founder-ceo.md",
    "brain/org/clients/acme/admin/README.md",
    "brain/life/areas/health/AGENTS.md", "brain/life/areas/health/CLAUDE.md",
    "brain/life/areas/health/GEMINI.md", "brain/life/areas/money/AGENTS.md",
    "brain/life/areas/money/CLAUDE.md", "brain/life/areas/money/GEMINI.md",
    "brain/life/areas/fitness/notes.md",
]
IGNORED = [
    ".tess/state/brain/turns.jsonl", "brain/.private/x", ".private/x",
    "brain/clients/acme/admin/contract.pdf", ".env", "brain/clients/acme/repos/app/x.py",
    "brain/life/areas/health/.private/labs.md", "scripts/brain/oobe/__pycache__/x.pyc",
    "brain/org/clients/acme/admin/contract.pdf", "brain/org/units/ops/clients/acme/admin/nda.pdf",
    "brain/life/areas/health/labs-2026.md", "brain/life/areas/money/statements/2026-09.pdf",
]


@pytest.fixture(scope="module")
def instance(tmp_path_factory):
    root = h.full_instance(tmp_path_factory.mktemp("gate"))
    h.git(root, "add", "-A")
    seed = h.git(root, "commit", "-qm", "seed", check=False)
    assert seed.returncode == 0, seed.stdout + seed.stderr
    return root


@pytest.mark.parametrize("rel", TRACKED)
def test_tracked(instance, rel):
    assert h.git(instance, "check-ignore", "-q", rel, check=False).returncode == 1


@pytest.mark.parametrize("rel", IGNORED)
def test_ignored(instance, rel):
    assert h.git(instance, "check-ignore", "-q", rel, check=False).returncode == 0


def test_real_gate_commit_of_every_tracked_brain_path(instance):
    for rel in TRACKED:
        path = instance / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("probe\n")
    h.git(instance, "add", "--", *TRACKED)
    done = h.git(instance, "-c", "user.name=p", "-c", "user.email=p@example.invalid",
                 "commit", "-m", "probe", check=False)
    out = done.stdout + done.stderr
    assert done.returncode == 0, out
    assert "publish-clean: OK" in out
    assert h.git(instance, "status", "--porcelain").stdout == ""


def test_gate_still_refuses_the_old_placement_paths(instance):
    """The reason brain/ exists: kb/ and clients/<x>/ are refused at commit."""
    for rel in ("kb/research/2026-09-24-x.md", "clients/acme/AGENTS.md"):
        path = instance / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("probe\n")
        h.git(instance, "add", "-f", "--", rel)
        done = h.git(instance, "commit", "-m", "old path", check=False)
        assert done.returncode != 0 and "BLOCKED" in done.stdout + done.stderr, rel
        h.git(instance, "reset", "-q", "--", rel)
        path.unlink()
