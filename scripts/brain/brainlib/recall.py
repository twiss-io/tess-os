"""`tessbrain.py recall "<words>"`: grep-grade retrieval with no vector DB.

Scans brain/ and the state-card folder; ranks front-matter title/tag hits,
then body hits, then recency. Prints `path:line: text` (no LLM summary).
brain/.private/ is excluded unless --private is passed.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from . import frontmatter
from .config import Config


def _terms(query: str) -> List[str]:
    return [t for t in re.findall(r"[\w$@.-]+", (query or "").lower()) if len(t) > 1]


def search(cfg: Config, query: str, entity: Optional[str] = None, kind: Optional[str] = None,
           limit: int = 20, private: bool = False) -> List[Dict]:
    terms = _terms(query)
    if not terms:
        return []
    roots = [cfg.brain / entity] if entity else [cfg.brain, cfg.root / cfg.state_cards]
    results = []
    for root in roots:
        for p in sorted(root.rglob("*.md")) if root.is_dir() else []:
            if ".private" in p.parts and not private:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            meta, body = frontmatter.parse(text)
            if kind and str(meta.get("type") or "") != kind:
                continue
            head = " ".join(str(meta.get(k) or "") for k in ("title", "name", "statement", "tags", "id")).lower()
            head_hits = sum(1 for t in terms if t in head)
            lines = text.splitlines()
            hit_lines = [(n, l) for n, l in enumerate(lines, 1) if any(t in l.lower() for t in terms)]
            body_hits = sum(1 for t in terms if t in text.lower())
            if not head_hits and not body_hits:
                continue
            best = max(hit_lines, key=lambda nl: sum(t in nl[1].lower() for t in terms)) if hit_lines else (1, "")
            results.append({"path": p.relative_to(cfg.root).as_posix(), "line": best[0], "text": best[1].strip()[:240],
                            "score": head_hits * 3 + body_hits, "mtime": p.stat().st_mtime})
    results.sort(key=lambda r: (-r["score"], -r["mtime"], r["path"]))
    return results[:limit]


def render(results: List[Dict]) -> str:
    return "\n".join("%s:%d: %s" % (r["path"], r["line"], r["text"]) for r in results) or "(no matches in brain/)"
