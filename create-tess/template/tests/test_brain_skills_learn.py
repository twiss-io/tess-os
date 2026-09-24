"""The six ws-learn skills (spec 9.7): byte-identical in .claude/skills and
.agents/skills, valid front matter, and every command they tell an agent to
run exists in tessbrain.py."""
import re
import sys
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

sys.path.insert(0, str(Path(fxlib.REPO) / "scripts" / "brain"))
import tessbrain  # noqa: E402

REPO = Path(fxlib.REPO)
SKILLS = ["brain-decide", "brain-remember", "brain-distill", "brain-review", "brain-save", "brain-recall"]


def _text(name, where=".agents"):
    return (REPO / where / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", SKILLS)
def test_pair_is_byte_identical_with_front_matter(name):
    a = (REPO / ".agents/skills" / name / "SKILL.md").read_bytes()
    c = (REPO / ".claude/skills" / name / "SKILL.md").read_bytes()
    assert a == c
    head = a.decode().split("---")[1]
    assert re.search(r"^name: %s$" % name, head, re.M)
    desc = re.search(r'^description: "(.+)"$', head, re.M)
    assert desc and 40 < len(desc.group(1)) <= 1024


def _subcommands():
    ap = tessbrain.build_parser()
    sub = [a for a in ap._actions if a.__class__.__name__ == "_SubParsersAction"][0]
    return sub.choices


@pytest.mark.parametrize("name", SKILLS)
def test_every_referenced_command_exists(name):
    choices = _subcommands()
    used = re.findall(r"tessbrain\.py (?:--json )?([a-z-]+)(?: ([a-z-]+))?", _text(name))
    assert used, name
    for cmd, arg in used:
        assert cmd in choices, (name, cmd)
        nested = [a for a in choices[cmd]._actions if a.__class__.__name__ == "_SubParsersAction"]
        if nested and arg:
            assert arg in nested[0].choices, (name, cmd, arg)


def test_never_rules():
    assert "Never record your own suggestion" in _text("brain-decide")
    assert "Never write records or edit files under `brain/` directly; only `inbox add`" in _text("brain-distill")
    assert "journal note" in _text("brain-save") and "Never bypass git hooks" in _text("brain-save")
    assert "Every change needs their words" in _text("brain-review")
    for name in SKILLS:
        assert not re.search(r"git (commit|push)[^\n]*--no-verify", _text(name))
