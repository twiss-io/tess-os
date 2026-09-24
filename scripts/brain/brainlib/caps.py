"""Budgets for every auto-loaded or generated file (spec section 10.7).

Going over a cap is an ERROR, never a silent truncation: the writer refuses
(exit 3) and leaves the file byte-identical, and lint exits 1.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .config import Config

EXIT_OVER_CAP = 3
PAGE_SIZE = 40  # entries per generated list before paging into brain/index/


def over(text: str, max_lines: Optional[int], max_bytes: Optional[int]) -> Optional[str]:
    lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
    size = len(text.encode("utf-8"))
    if max_lines is not None and lines > max_lines:
        return "%d lines > %d" % (lines, max_lines)
    if max_bytes is not None and size > max_bytes:
        return "%d B > %d B" % (size, max_bytes)
    return None


def start_here(cfg: Config, text: str) -> Optional[str]:
    b = cfg.budgets
    return over(text, b["start_here_lines"], b["start_here_kib"] * 1024)


def index_file(cfg: Config, text: str) -> Optional[str]:
    b = cfg.budgets
    return over(text, b["index_lines"], b["start_here_kib"] * 1024)


def profile(cfg: Config, text: str) -> Optional[str]:
    return over(text, None, cfg.budgets["profile_kib"] * 1024)


def entity_agents(cfg: Config, text: str) -> Optional[str]:
    b = cfg.budgets
    return over(text, b["entity_agents_lines"], b["entity_agents_kib"] * 1024)


def start_here_line(text: str) -> Optional[int]:
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("# START HERE"):
            return n
    return None


def chain_paths(cfg: Config, entity_dir: Path) -> List[Path]:
    """Root AGENTS.md, then every AGENTS.md from brain/ down to the entity."""
    out = [cfg.root / "AGENTS.md"]
    try:
        rel = Path(entity_dir).resolve().relative_to(cfg.root.resolve())
    except ValueError:
        return out
    cur = cfg.root
    for part in rel.parts:
        cur = cur / part
        if (cur / "AGENTS.md").is_file():
            out.append(cur / "AGENTS.md")
    return [p for p in out if p.is_file()]


def chain_bytes(cfg: Config, entity_dir: Path) -> int:
    return sum(p.stat().st_size for p in chain_paths(cfg, entity_dir))


def chain_limits(cfg: Config):
    fail = cfg.budgets["agents_chain_kib"] * 1024
    return fail - 4 * 1024, fail  # (warn, fail): 20 KiB / 24 KiB by default
