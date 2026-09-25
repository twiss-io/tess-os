"""Entities: folders under brain.json `entity_roots` that hold an AGENTS.md
(START HERE). The entity id is its path relative to brain/ (e.g. clients/acme).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from . import frontmatter
from .config import Config


class Entity:
    __slots__ = ("id", "name", "dir", "kind", "status")

    def __init__(self, eid: str, name: str, directory: Path, kind: str, status: str):
        self.id, self.name, self.dir, self.kind, self.status = eid, name, directory, kind, status


def discover(cfg: Config) -> List[Entity]:
    out: List[Entity] = []
    seen = set()
    for pattern in cfg.entity_roots:
        for d in sorted(cfg.root.glob(pattern.strip("/"))):
            agents = d / "AGENTS.md"
            if not d.is_dir() or not agents.is_file() or ".private" in d.parts:
                continue
            try:
                eid = d.resolve().relative_to(cfg.brain.resolve()).as_posix()
            except ValueError:
                continue
            if eid in seen:
                continue
            seen.add(eid)
            try:
                meta, _ = frontmatter.read(agents)
            except (OSError, UnicodeDecodeError):
                meta = {}
            out.append(Entity(eid, str(meta.get("name") or d.name), d, str(meta.get("kind") or d.parent.name),
                              str(meta.get("status") or "active")))
    return out


def names(cfg: Config) -> Dict[str, str]:
    """{entity id: display name} for mention matching."""
    return {e.id: e.name for e in discover(cfg)}
