"""Scaffold trees per mode + preset match the committed expected trees (spec section 8).

Also checks the per-file contracts every mode shares: each entity AGENTS.md
has `# START HERE` within its first 80 lines and stays within budget (6 KiB,
100 lines); the CLAUDE.md / GEMINI.md shims are exact imports; the root map
stays within 150 lines / 12 KiB; the four entity generated-block markers
are present and empty (ws-learn fills them).
"""
from __future__ import annotations

import json

import pytest

import _brain_oobe_helpers as h

CASES = ["personal", "agency-solo", "organisation-startup"]
ENTITY_MARKERS = ("decisions", "loops", "facts", "cards")
ROOT_MARKERS = ("entities", "recent-decisions", "open-loops", "health")


@pytest.fixture(scope="module", params=CASES)
def scaffold(request, tmp_path_factory):
    root = h.mini_instance(tmp_path_factory.mktemp(request.param))
    done = h.onboard_fixture(root, request.param)
    assert done.returncode == 0, done.stdout + done.stderr
    return request.param, root


def test_tree_matches_expected(scaffold):
    name, root = scaffold
    expected = (h.FIXTURES / ("expected-tree-%s.txt" % name)).read_text().split()
    assert h.tree(root) == expected


def test_every_entity_starts_here_within_budget(scaffold):
    _, root = scaffold
    agents = sorted((root / "brain").rglob("AGENTS.md"))
    assert agents, "at least one entity"
    for path in agents:
        text = path.read_text()
        head = text.split("\n")[:80]
        assert any(line.startswith("# START HERE") for line in head), path
        assert len(text.encode()) <= 6144 and text.count("\n") <= 100, path
        for marker in ENTITY_MARKERS:
            block = "<!-- tess:gen:%s:start -->\n<!-- tess:gen:%s:end -->" % (marker, marker)
            assert block in text, (path, marker)
        assert (path.parent / "CLAUDE.md").read_text() == "@AGENTS.md\n"
        assert (path.parent / "GEMINI.md").read_text() == "@./AGENTS.md\n"


def test_root_map_budget_and_markers(scaffold):
    _, root = scaffold
    text = (root / "brain" / "START-HERE.md").read_text()
    assert text.count("\n") <= 150 and len(text.encode()) <= 12288
    for marker in ROOT_MARKERS:
        assert "<!-- tess:gen:%s:start -->\n<!-- tess:gen:%s:end -->" % (marker, marker) in text
    brain = json.loads((root / "brain" / "brain.json").read_text())
    for pattern in brain["entity_roots"]:
        for ent in (p for p in root.glob(pattern) if p.is_dir()):
            rel = ent.relative_to(root / "brain").as_posix()
            assert "](%s/AGENTS.md)" % rel in text, "entity %s missing from the map" % rel


def test_generated_files_are_flagged(scaffold):
    _, root = scaffold
    for rel in ("profile.md", "learned.md", "open-loops.md", "decisions/INDEX.md", "decisions/ALL.md"):
        assert "\ngenerated: true\n" in (root / "brain" / rel).read_text(), rel


def test_private_areas_keep_only_pointers():
    import tempfile
    from pathlib import Path
    root = h.mini_instance(Path(tempfile.mkdtemp()))
    assert h.onboard_fixture(root, "personal").returncode == 0
    for area in ("health", "money"):
        text = (root / "brain" / "life" / "areas" / area / "AGENTS.md").read_text()
        assert "brain/.private/areas/%s/" % area in text and "privacy: limited" in text
        assert (root / "brain" / ".private" / "areas" / area).is_dir()
    assert h.git(root, "check-ignore", "-q", "brain/.private/areas/health/x.md", check=False).returncode == 0


def test_org_seats_have_exactly_one_holder_and_quarter_file():
    import tempfile
    from pathlib import Path
    root = h.mini_instance(Path(tempfile.mkdtemp()))
    assert h.onboard_fixture(root, "organisation-startup").returncode == 0
    seats = sorted(p for p in (root / "brain" / "org" / "seats").glob("*.md") if p.name != "CHART.md")
    assert [s.stem for s in seats] == ["founder-ceo", "growth", "operations", "product"]
    assert 'holder: "Sam Ilunga"' in (root / "brain/org/seats/founder-ceo.md").read_text()
    score = (root / "brain/org/metrics/scorecard.md").read_text()
    assert score.count("\n| ") == 6, "startup preset scorecard: header + 5 rows"
    assert (root / "brain/org/priorities/2026-Q3.md").exists()


def test_seat_chart_is_generated_from_the_cards_and_follows_add_seat(tmp_path):
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "organisation-startup").returncode == 0
    chart = root / "brain" / "org" / "seats" / "CHART.md"
    text = chart.read_text()
    assert "generated: true" in text
    assert "| [founder-ceo](founder-ceo.md) | Sam Ilunga | - |" in text
    assert text.count("| unfilled |") == 3
    assert "(seats/CHART.md)" in (root / "brain" / "org" / "AGENTS.md").read_text()
    added = h.onboard(root, "add", "seat", "Head of Finance")
    assert added.returncode == 0, added.stderr
    assert "| [Head of Finance](head-of-finance.md) | unfilled | - |" in chart.read_text()
    before = chart.read_bytes()
    h.git(root, "add", "-A")
    h.git(root, "commit", "-qm", "seat")
    assert h.onboard(root, "apply").returncode == 0
    assert chart.read_bytes() == before and h.git(root, "status", "--porcelain").stdout == ""
