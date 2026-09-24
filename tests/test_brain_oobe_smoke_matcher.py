"""The live smoke's identity matcher must assert O9/O10 as written, and must be able to fail.

O10 (Codex): the reply names 'Tess', 'brain-onboard' AND at least one 'tess-' skill.
O9 (Claude): the reply names 'Tess' and at least 2 of /add-mission|/wake|/close|/help|brain-onboard.
The function under test is extracted from tests/smoke/brain_oobe_live.sh and run in bash.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

SMOKE = Path(__file__).resolve().parent / "smoke" / "brain_oobe_live.sh"


def _ident_ok_src() -> str:
    m = re.search(r"(?ms)^ident_ok\(\) \{.*?^\}", SMOKE.read_text())
    assert m, "ident_ok() not found in the smoke script"
    return m.group(0)


def _ident_ok(rt: str, reply: str, tmp_path: Path) -> bool:
    f = tmp_path / "reply.txt"
    f.write_text(reply)
    script = _ident_ok_src() + f'\nident_ok "{rt}" "{f}"\n'
    return subprocess.run(["bash", "-c", script]).returncode == 0


@pytest.mark.parametrize("reply, ok", [
    ("I'm Tess. Try `brain-onboard`, `tess-wake` and `tess-help`.", True),
    ("I'm Tess. Skills: brain-onboard, tess-add-mission.", True),
    ("I'm Tess. Skills: tess-wake, tess-help, tess-close.", False),   # no brain-onboard
    ("I'm Tess. Skills: brain-onboard and brain-save.", False),       # no tess- skill
    ("I'm your assistant: brain-onboard, tess-wake.", False),         # no Tess
    ("I'm Tess. I can help with code review and planning.", False),
])
def test_codex_matcher_is_o10_as_written(reply, ok, tmp_path):
    assert _ident_ok("codex", reply, tmp_path) is ok


@pytest.mark.parametrize("reply, ok", [
    ("I'm Tess: /add-mission, /wake, /help.", True),
    ("I'm Tess: /wake and brain-onboard.", True),
    ("I'm Tess: /wake only.", False),
    ("I'm Claude: /add-mission, /wake.", False),
])
def test_claude_matcher_is_o9_as_written(reply, ok, tmp_path):
    assert _ident_ok("claude", reply, tmp_path) is ok
