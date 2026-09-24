"""Generated journal indexes: brain/journal/INDEX.md (months) ->
journal/YYYY/MM/INDEX.md (days) -> journal/YYYY/MM/YYYY-MM-DD.md (sessions).
Every session file is therefore reachable from START HERE.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from . import frontmatter, gen, lookup
from .config import Config
from .gen import Item


def _session_item(cfg: Config, path: Path, ref: str) -> Item:
    try:
        meta = frontmatter.read(path)[0] if path.is_file() else lookup.session_meta(cfg, ref)
    except (OSError, UnicodeDecodeError):
        meta = {}
    who = ", ".join(meta.get("speakers") or []) or "no principal turns"
    return Item(path.stem, path, "", " · %s · %s turns · %s" % (meta.get("runtime", "?"), meta.get("turns", 0), who))


def pages(cfg: Config) -> Dict[Path, str]:
    out: Dict[Path, str] = {}
    by_day: Dict[str, List[str]] = {}
    for ref in lookup.session_files(cfg):
        if not (cfg.root / ref).is_file():
            continue  # capture.journal=local: nothing committed to index
        rel = ref[len("brain/journal/"):]
        day = "/".join(rel.split("/")[:3])
        by_day.setdefault(day, []).append(ref)
    months: Dict[str, List[str]] = {}
    jroot = cfg.brain / "journal"
    for day, refs in sorted(by_day.items()):
        y, m, d = day.split("/")
        month_dir = jroot / y / m
        items = []
        for ref in sorted(refs):
            p = cfg.root / ref
            items.append(_session_item(cfg, p, ref))
        lines, extra = gen.listing(cfg.brain, month_dir, items, "journal-%s-%s-%s" % (y, m, d), "Sessions %s" % day)
        out.update(extra)
        out[month_dir / ("%s-%s-%s.md" % (y, m, d))] = gen.page("Journal %s-%s-%s" % (y, m, d), lines)
        months.setdefault("%s/%s" % (y, m), []).append("%s-%s-%s" % (y, m, d))
    if not months and not jroot.is_dir():
        return out
    for ym, days in months.items():
        month_dir = jroot / ym
        out[month_dir / "INDEX.md"] = gen.page("Journal %s" % ym.replace("/", "-"),
                                               [Item(d, month_dir / ("%s.md" % d)).render(month_dir) for d in sorted(days, reverse=True)])
    items = [Item(ym.replace("/", "-"), jroot / ym / "INDEX.md") for ym in sorted(months, reverse=True)]
    lines, extra = gen.listing(cfg.brain, jroot, items, "journal-months", "Journal months")
    out.update(extra)
    out[jroot / "INDEX.md"] = gen.page("Journal (one file per session; verbatim, redacted)", lines)
    return out
