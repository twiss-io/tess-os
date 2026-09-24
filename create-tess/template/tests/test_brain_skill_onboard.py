"""The brain-onboard skill (spec 6.2, 6.4, 9.7, 5.3).

Claude Code reads only .claude/skills; Codex, Gemini CLI and Kimi read
.agents/skills: the two copies must be byte-identical. The description is
the instruction-level trigger, so its first words are pinned. Every CLI
command and field the skill tells a model to use must exist in onboard.py,
so the instructions can never drift from the tool.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CLAUDE = REPO / ".claude" / "skills" / "brain-onboard" / "SKILL.md"
AGENTS = REPO / ".agents" / "skills" / "brain-onboard" / "SKILL.md"
TEXT = CLAUDE.read_text()

sys.path.insert(0, str(REPO / "scripts" / "brain"))
from oobe import answers  # noqa: E402


def front_matter(text: str) -> dict:
    assert text.startswith("---\n")
    block = text.split("---\n", 2)[1]
    out = {}
    for ln in block.strip().splitlines():
        key, _, value = ln.partition(":")
        out[key.strip()] = value.strip().strip('"')
    return out


def test_copies_are_byte_identical():
    assert CLAUDE.read_bytes() == AGENTS.read_bytes()


def test_front_matter_name_and_trigger_description():
    fm = front_matter(TEXT)
    assert fm["name"] == "brain-onboard"
    assert fm["description"].startswith(
        "START HERE when brain/brain.json is missing or onboarding is not complete")
    assert len(fm["description"]) <= 1024


def test_status_first_and_one_question_per_turn():
    assert TEXT.index("status --json") < TEXT.index("## 2.")
    assert "one question per turn" in TEXT.lower()
    assert "Never invent or paraphrase an answer" in TEXT
    assert "--quote" in TEXT and "verbatim" in TEXT


def test_every_cli_command_in_the_skill_exists():
    used = set(re.findall(r"scripts/brain/onboard\.py ([a-z-]+)", TEXT))
    help_text = subprocess.run([sys.executable, str(REPO / "scripts" / "brain" / "onboard.py"), "--help"],
                               capture_output=True, text=True).stdout
    assert used >= {"status", "answer", "apply", "defer", "skip", "convert-clone", "add", "add-mode", "restore"}
    for cmd in used:
        assert cmd in help_text, cmd


def test_every_field_in_the_skill_is_a_real_field():
    for field in answers.FIELD_STEP:
        assert "`%s`" % field in TEXT, field


@pytest.mark.parametrize("runtime", ["Claude Code", "Codex CLI", "Gemini CLI", "Kimi"])
def test_trust_line_per_runtime(runtime):
    assert "**%s" % runtime in TEXT


def test_covers_defer_skip_convert_and_seed_push():
    for needle in ("defer --days 7", "skip --quote", "convert-clone --yes",
                   "git push --no-verify -u origin main", "never run\n`--no-verify` yourself"):
        assert needle in TEXT, needle
