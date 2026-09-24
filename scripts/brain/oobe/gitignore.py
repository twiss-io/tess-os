"""The marked, idempotent tess-brain block in .gitignore (spec section 8).

Belt and braces: brain/.private/ and .tess/state/brain/ also carry their own
self-ignoring `.gitignore` (`*`), so they stay out of git even without this
block. The text between the markers is owned by this module; everything
outside the markers is never touched.
"""
from __future__ import annotations

from pathlib import Path

from . import state

START = "# >>> tess-brain (managed by scripts/brain/onboard.py; do not edit inside) >>>"
END = "# <<< tess-brain <<<"
BODY = [
    ".private/",
    "**/.private/",
    ".tess/state/brain/",
    "brain/**/repos/",
    "brain/**/dev.nosync/",
    "brain/clients/*/admin/*",
    "!brain/clients/*/admin/README.md",
    ".obsidian/workspace.json",
    ".obsidian/workspaces.json",
]
BLOCK = "\n".join([START] + BODY + [END]) + "\n"


def render(current: str) -> str:
    """Return .gitignore text with exactly one canonical block."""
    if START in current and END in current:
        head, rest = current.split(START, 1)
        _, tail = rest.split(END, 1)
        tail = tail[1:] if tail.startswith("\n") else tail
        return head + BLOCK + tail
    sep = "" if not current or current.endswith("\n\n") else ("\n" if current.endswith("\n") else "\n\n")
    return current + sep + BLOCK


def ensure_block(root: Path, dry: bool = False) -> bool:
    """Add or repair the block. Returns True when .gitignore changed."""
    path = root / ".gitignore"
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    new = render(current)
    if new == current:
        return False
    if not dry:
        state.atomic_write(path, new)
    return True
