"""BOOT block: one canonical text in both operator stubs, rendered into CLAUDE.md
and AGENTS.md within budget (spec 6.1, E5-E7).

The BOOT is what makes onboarding self-starting in every runtime that loads
CLAUDE.md or AGENTS.md, so these tests pin: byte-identity with
scripts/brain/BOOT.md, position (before the file-placement rules it
overrides), the AGENTS.md size budget, and the worker denylist.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BOOT = (REPO / "scripts" / "brain" / "BOOT.md").read_text()
CONDUCTOR_LINE = ("- As conductor, you run onboarding and brain reads and writes yourself; "
                  "they are not specialist work for the crew.\n")


def test_boot_is_the_frozen_block():
    lines = BOOT.splitlines()
    assert lines[0] == "## Second brain: read this first" and len(lines) == 8
    assert lines[2].startswith("- First reply of every session:")
    assert [ln.split(":")[0] for ln in lines[3:7]] == ["- Setup", "- Orient", "- Record", "- Save"]
    assert "{{ASSISTANT_NAME}}" in BOOT and "{{OPERATOR_NAME}}" in BOOT


def test_both_stubs_carry_boot_byte_for_byte():
    identity = (REPO / "operator" / "identity-stub.md").read_text()
    facts = (REPO / "operator" / "build-facts-stub.md").read_text()
    assert BOOT in identity and BOOT in facts
    assert identity.endswith(BOOT + CONDUCTOR_LINE)
    assert CONDUCTOR_LINE not in facts
    assert re.search(r"(?m)^inject: true$", facts)


def test_rendered_boot_identical_in_claude_and_agents(engine):
    claude = engine.render_claude_md(REPO)
    agents = engine.render_agents_md(REPO)
    rendered = engine.apply_token_sub(BOOT, REPO)
    assert "{{" not in rendered
    assert rendered in claude and rendered in agents
    assert CONDUCTOR_LINE in claude and CONDUCTOR_LINE not in agents


def test_committed_entry_files_equal_a_fresh_render(engine):
    assert (REPO / "CLAUDE.md").read_text() == engine.render_claude_md(REPO)
    assert (REPO / "AGENTS.md").read_text() == engine.render_agents_md(REPO)


def test_agents_md_budget():
    text = (REPO / "AGENTS.md").read_text()
    assert text.count("\n") < 100
    # 12000 -> 12800 (e2e round 2): the first-reply line (hooks-status check + plain greeting).
    # Codex reads up to project_doc_max_bytes (32 KiB by default).
    assert len(text.encode("utf-8")) <= 12800


@pytest.mark.parametrize("phrase", ["always dispatch", "never execute solo", "rule zero",
                                    "outcome orchestrator", "dispatch brief contract", "dispatch-guard.sh"])
def test_boot_has_no_worker_denylist_phrase(engine, phrase):
    assert phrase in engine.WORKER_DOCTRINE_DENYLIST
    assert phrase not in BOOT.lower()


def test_second_brain_section_comes_before_the_rules_it_overrides():
    agents = (REPO / "AGENTS.md").read_text()
    claude = (REPO / "CLAUDE.md").read_text()
    assert agents.index("## Second brain: read this first") < agents.index("### File Placement")
    assert claude.index("## Second brain: read this first") < claude.index("## Directory Structure")
    line_no = claude[: claude.index("## Second brain: read this first")].count("\n") + 1
    assert line_no <= 40
