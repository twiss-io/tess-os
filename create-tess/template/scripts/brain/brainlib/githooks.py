"""`tessbrain.py githooks install`: the one enforcement layer every runtime
shares. Adds (never replaces) a warn-only pre-commit brain lint and a
post-merge index regeneration next to the gate's own spliced hook block,
without changing that block's exit status. Idempotent: a marker guards each;
an earlier version's block is replaced by the current one. Both run through
the pinned launcher (.claude/hooks/run-pinned.py), never straight from the
working tree.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Dict

from . import gitutil
from .config import Config

MARK = "# tess-brain-guard v2"
END = "# /tess-brain-guard v2"
OLD_MARKS = (("# tess-brain-guard v1", "# /tess-brain-guard v1"),)
# v1.0.0 audit (unpinned working-tree exec): the v1 blocks ran
# `python3 scripts/brain/tessbrain.py` straight from the working tree, so a
# merged or pulled change to any brainlib module ran as the operator on the
# next merge or commit, with no pin, closure or anchor check. The blocks now go
# through the pinned launcher, exactly like the runtime hooks: every
# scripts/brain/**/*.py must match its pin (and the enforcement anchor must
# hold) or nothing runs. Warn-only as before: the launcher prints why it
# skipped, and the hook still exits 0. Without the launcher nothing runs.
_LAUNCH = ('t="$(git rev-parse --show-toplevel)"; l="$t/.claude/hooks/run-pinned.py"; '
           '[ -f "$t/scripts/brain/tessbrain.py" ] && [ -f "$l" ] && (cd "$t" && env -u CLAUDE_PROJECT_DIR '
           'python3 -I -B "$l" --on-fail warn --closure scripts/brain -- scripts/brain/tessbrain.py %s) || true')
BLOCKS = {
    "pre-commit": _LAUNCH % "lint --staged --warn-only",
    "post-merge": _LAUNCH % "index --quiet",
}


def _strip_old(text: str) -> str:
    """Remove an earlier version's block (MARK line through END line)."""
    for mark, end in OLD_MARKS:
        lines = text.splitlines()
        if mark not in lines:
            continue
        i = lines.index(mark)
        j = lines.index(end, i) if end in lines[i:] else i
        text = "\n".join(lines[:i] + lines[j + 1:]) + "\n"
    return text


def _insert(text: str, block: str) -> str:
    """Place the block right after the shebang: it always exits 0 and leaves $?
    untouched for what follows, so an existing hook (e.g. the gate guard,
    which may end in `exit $?` or `exec`) keeps its exact behaviour."""
    lines = text.splitlines()
    if lines and lines[0].startswith("#!"):
        return "\n".join([lines[0], block] + lines[1:]) + "\n"
    return "\n".join(["#!/bin/sh", block] + lines) + "\n"


def install(cfg: Config) -> Dict[str, str]:
    hooks = gitutil.hooks_dir(cfg.root)
    if hooks is None:
        return {"error": "not a git repository"}
    hooks.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, cmd in BLOCKS.items():
        path = hooks / name
        block = "%s\n%s\n%s" % (MARK, cmd, END)
        text = path.read_text(encoding="utf-8") if path.is_file() else "#!/bin/sh\n"
        if MARK in text:
            out[name] = "present"
            continue
        upgraded = _strip_old(text)
        path.write_text(_insert(upgraded, block), encoding="utf-8")
        mode = os.stat(str(path)).st_mode
        os.chmod(str(path), mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        out[name] = "upgraded" if upgraded != text else "installed"
    return out
