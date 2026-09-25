"""`tessbrain.py githooks install`: the one enforcement layer every runtime
shares. Adds (never replaces) a warn-only pre-commit brain lint and a
post-merge index regeneration next to the gate's own spliced hook block,
without changing that block's exit status. Idempotent: a marker guards each.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Dict

from . import gitutil
from .config import Config

MARK = "# tess-brain-guard v1"
END = "# /tess-brain-guard v1"
BLOCKS = {
    "pre-commit": 'f="$(git rev-parse --show-toplevel)/scripts/brain/tessbrain.py"; '
                  '[ -f "$f" ] && python3 "$f" lint --staged --warn-only || true',
    "post-merge": 'f="$(git rev-parse --show-toplevel)/scripts/brain/tessbrain.py"; '
                  '[ -f "$f" ] && python3 "$f" index --quiet || true',
}


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
        path.write_text(_insert(text, block), encoding="utf-8")
        mode = os.stat(str(path)).st_mode
        os.chmod(str(path), mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        out[name] = "installed"
    return out
