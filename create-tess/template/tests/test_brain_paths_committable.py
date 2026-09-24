"""Brain paths stay committable through the instance gate (spec G15, E1, E4).

Uses tessctl's OWN glob matcher (path_matches_globs) against its OWN
publish-clean private globs and the manifest's owned_globs, so a future
engine or manifest change that would silently make the brain uncommittable
(or let tessctl overwrite it) fails here first.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import _brain_oobe_helpers as h

REPO = Path(__file__).resolve().parent.parent
PROBE_PATHS = [
    "brain/brain.json", "brain/START-HERE.md", "brain/journal/2026/09/24/1405-claude-abcd1234.md",
    "brain/clients/acme/AGENTS.md", "brain/clients/acme/kb/research/x.md", "brain/decisions/D-x.md",
    "brain/org/people/x.md", "brain/life/areas/work/AGENTS.md", "brain/kb/research/x.md",
    "brain/inbox/C-20260924-1412-01.json", "memory/projects/x.md",
]


@pytest.fixture(scope="module")
def generated_paths(tmp_path_factory):
    out = set(PROBE_PATHS)
    for case in ("personal", "agency-solo", "organisation-startup"):
        out.update((h.FIXTURES / ("expected-tree-%s.txt" % case)).read_text().split())
    return sorted(out)


def test_no_brain_path_matches_a_publish_clean_private_glob(engine, generated_paths):
    for rel in generated_paths:
        hit = [g for g in engine._PUBLISH_CLEAN_PRIVATE_GLOBS if engine.path_matches_globs(rel, [g])]
        assert hit == [], "%s would be BLOCKED at commit by %s" % (rel, hit)


def test_no_brain_path_is_owned_by_tessctl(engine, generated_paths):
    owned = json.loads((REPO / "tess.manifest.json").read_text())["owned_globs"]
    for rel in generated_paths:
        assert not engine.path_matches_globs(rel, owned), "%s is writable by tessctl render/update" % rel


def test_local_state_is_still_private(engine):
    """Sanity: the matcher is live. The old placement paths ARE blocked."""
    for rel in (".tess/state/brain/turns.jsonl", "kb/research/x.md", "clients/acme/AGENTS.md"):
        assert any(engine.path_matches_globs(rel, [g]) for g in engine._PUBLISH_CLEAN_PRIVATE_GLOBS), rel


def test_brain_tools_are_not_lock_managed():
    lock = (REPO / ".tess" / "tess.lock").read_text()
    assert "scripts/brain/" not in lock and "brain-onboard" not in lock
