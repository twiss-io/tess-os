"""Reachability: every brain file must be reachable from brain/START-HERE.md
by following relative Markdown links (or [[wiki links]]). "Saved" requires it:
a file nothing links to is invisible to a zero-context agent.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from .config import Config

_MD = re.compile(r"\]\(<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\)")
_WIKI = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
EXEMPT_NAMES = {"CLAUDE.md", "GEMINI.md", ".gitkeep", ".gitignore"}
EXEMPT_TOP = {"inbox", ".private", "skills-drafts", "reviews"}


def _targets(text: str, base: Path, stems: Dict[str, Path]) -> List[Path]:
    out = []
    for raw in _MD.findall(text):
        if "://" in raw or raw.startswith(("mailto:", "#")):
            continue
        p = raw.split("#", 1)[0]
        if p:
            out.append((base / p))
    for w in _WIKI.findall(text):
        hit = stems.get(w.strip().lower()) or stems.get(Path(w.strip()).stem.lower())
        if hit:
            out.append(hit)
    return out


def _as_file(p: Path) -> Optional[Path]:
    try:
        p = Path(os.path.normpath(str(p)))
    except (OSError, ValueError):
        return None
    if p.is_dir():
        for name in ("AGENTS.md", "INDEX.md", "README.md"):
            if (p / name).is_file():
                return p / name
        return None
    return p if p.is_file() else None


def reachable(cfg: Config) -> Set[Path]:
    start = cfg.brain / "START-HERE.md"
    if not start.is_file():
        return set()
    stems = {p.stem.lower(): p for p in cfg.brain.rglob("*.md")}
    seen: Set[Path] = set()
    stack = [start]
    brain = Path(os.path.normpath(str(cfg.brain)))
    while stack:
        cur = Path(os.path.normpath(str(stack.pop())))
        if cur in seen:
            continue
        seen.add(cur)
        if cur.suffix != ".md" or brain not in cur.parents:
            continue
        try:
            text = cur.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for t in _targets(text, cur.parent, stems):
            f = _as_file(t)
            if f is not None and f not in seen:
                stack.append(f)
    return seen


def exempt(cfg: Config, path: Path) -> bool:
    rel = path.relative_to(cfg.brain).parts
    if not rel or path.name in EXEMPT_NAMES or rel[0] in EXEMPT_TOP or path.suffix != ".md":
        return True
    if rel == ("README.md",) or (len(rel) >= 2 and rel[0] == "kb" and rel[1] == "raw"):
        return True
    return "raw" in rel and "kb" in rel


def unreachable(cfg: Config, only: Optional[List[Path]] = None) -> List[Path]:
    if not cfg.brain.is_dir():
        return []
    seen = reachable(cfg)
    pool = only if only is not None else list(cfg.brain.rglob("*"))
    out = []
    for p in pool:
        p = Path(os.path.normpath(str(p)))
        if not p.is_file() or cfg.brain not in p.parents:
            continue
        if exempt(cfg, p):
            continue
        if p not in seen:
            out.append(p)
    return sorted(out)


def owning_start(cfg: Config, path: Path) -> Path:
    """The nearest START HERE (entity AGENTS.md) above a file, else brain/START-HERE.md."""
    cur = path.parent
    while cur != cfg.brain and cfg.brain in cur.parents:
        if (cur / "AGENTS.md").is_file() and cur / "AGENTS.md" != path:
            return cur / "AGENTS.md"
        cur = cur.parent
    return cfg.brain / "START-HERE.md"
