"""Marker blocks: root brain/START-HERE.md (entities, recent-decisions,
open-loops, health) and each entity AGENTS.md (decisions, loops, facts,
cards). Only text between the markers is ever rewritten.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from . import caps, frontmatter, gen, records
from .config import Config, write_text_if_changed
from .gen import Item
from .textutil import clip

SEED = """# START HERE: the brain map

Operator data lives in `brain/`. Hand-written text goes outside the generated
blocks; `python3 scripts/brain/tessbrain.py index` refreshes the blocks.

## Entities

<!-- tess:gen:entities:start -->
<!-- tess:gen:entities:end -->

## Recent decisions

<!-- tess:gen:recent-decisions:start -->
<!-- tess:gen:recent-decisions:end -->

## Open loops

<!-- tess:gen:open-loops:start -->
<!-- tess:gen:open-loops:end -->

## Brain health

<!-- tess:gen:health:start -->
<!-- tess:gen:health:end -->
"""


def _entities_block(cfg: Config, ents, pages: Dict[Path, str]) -> str:
    groups: Dict[str, List] = {}
    for e in ents:
        groups.setdefault(str(Path(e.id).parent) if "/" in e.id else e.id, []).append(e)
    out: List[str] = []
    for g in sorted(groups):
        items = [Item(e.name, e.dir / "AGENTS.md", "", " (%s)" % e.status if e.status != "active" else "")
                 for e in groups[g]]
        lines, extra = gen.listing(cfg.brain, cfg.brain, items, "entities-%s" % g.replace("/", "-"), g)
        pages.update(extra)
        out += ["**%s** (%d)" % (g, len(items)), ""] + lines + [""]
    return "\n".join(out).strip() or "(no entities yet)"


def _health(cfg: Config, inbox_n: int) -> str:
    rows = [("profile.md", "what I learned about how you work"), ("learned.md", "every promotion, newest first"),
            ("decisions/INDEX.md", "active decisions"), ("decisions/ALL.md", "decision history"),
            ("open-loops.md", "open loops"), ("journal/INDEX.md", "every conversation, one file per session"),
            ("profile/INDEX.md", "all preference/correction records"), ("facts/INDEX.md", "facts"),
            ("loops/INDEX.md", "all loops")]
    lines = ["- [%s](%s): %s" % (p, p, why) for p, why in rows if (cfg.brain / p).is_file()]
    lines.append("- Inbox: %d candidate(s) awaiting review (skill `brain-review`)" % inbox_n)
    lines.append("- Check before saying \"saved\": `python3 scripts/brain/tessbrain.py status`")
    return "\n".join(lines)


def _start_here(cfg: Config, recs, ents, loops, pages: Dict[Path, str]) -> Tuple[int, List[str]]:
    path = cfg.brain / "START-HERE.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else SEED
    dec = [r for r in sorted(recs, key=lambda r: (records.sort_key(r), r.id), reverse=True)
           if r.kind == "decision" and r.status in ("accepted", "proposed")][:5]
    recent = "\n".join(Item(str(r.meta.get("title") or r.id), r.path, "%s " % records.sort_key(r)[:10],
                            " (%s)" % r.status).render(cfg.brain) for r in dec) or "(none yet)"
    recent += "\n- All: [decisions/INDEX.md](decisions/INDEX.md)"
    lp = "\n".join(Item(clip(str(r.meta.get("statement") or ""), 100), r.path).render(cfg.brain) for r in loops[:10])
    lp = (lp or "(none)") + "\n- All: [open-loops.md](open-loops.md)"
    inbox_n = len(list((cfg.brain / "inbox").glob("C-*.json"))) if (cfg.brain / "inbox").is_dir() else 0
    new = text
    for block, content, head in (("entities", _entities_block(cfg, ents, pages), "## Entities"),
                                 ("recent-decisions", recent, "## Recent decisions"),
                                 ("open-loops", lp, "## Open loops"), ("health", _health(cfg, inbox_n), "## Brain health")):
        new = gen.fill(new, block, content, head)
    err = caps.start_here(cfg, new)
    if err:
        hand = gen.strip_blocks(new)
        return caps.EXIT_OVER_CAP, ["over cap, not written: brain/START-HERE.md (%s); hand-written part is %d lines;"
                                    " move detail into entity START HERE files" % (err, hand.count("\n"))]
    write_text_if_changed(path, new)
    return 0, []


def _entity_blocks(cfg: Config, e, recs) -> Dict[str, str]:
    mine = [r for r in recs if _under(r.path, e.dir)]
    newest = sorted(mine, key=lambda r: (records.sort_key(r), r.id), reverse=True)
    dec = [r for r in newest if r.kind == "decision" and r.status == "accepted"][:5]
    d = "\n".join(Item(str(r.meta.get("title") or r.id), r.path, "%s " % records.sort_key(r)[:10]).render(e.dir)
                  for r in dec) or "(none yet)"
    if (e.dir / "decisions" / "INDEX.md").is_file():
        d += "\n- All: [decisions/INDEX.md](decisions/INDEX.md)"
    lo = [r for r in newest if r.kind == "open_loop" and r.status in ("proposed", "active", "waiting")]
    l = "\n".join(Item(clip(str(r.meta.get("statement") or ""), 100), r.path, "", " (%s)" % r.status).render(e.dir)
                  for r in lo[:10]) or "(none)"
    if (e.dir / "loops" / "INDEX.md").is_file():
        l += "\n- All: [loops/INDEX.md](loops/INDEX.md)"
    fa = [r for r in newest if r.kind == "fact" and r.status == "active" and r.meta.get("verified")][:10]
    f = "\n".join(Item(clip(str(r.meta.get("statement") or ""), 100), r.path).render(e.dir) for r in fa) or "(none)"
    if (e.dir / "facts" / "INDEX.md").is_file():
        f += "\n- All: [facts/INDEX.md](facts/INDEX.md)"
    return {"decisions": d, "loops": l, "facts": f, "cards": _cards(cfg, e)}


def _cards(cfg: Config, e) -> str:
    d = cfg.root / cfg.state_cards
    items = []
    for p in sorted(d.glob("*.md")) if d.is_dir() else []:
        try:
            meta, _ = frontmatter.read(p)
        except (OSError, UnicodeDecodeError):
            continue
        if str(meta.get("entity") or "") == e.id:
            items.append(Item(str(meta.get("title") or p.stem), p, "", " (%s)" % meta.get("status", "open")).render(e.dir))
    return "\n".join(items) or "(none)"


def _under(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def fill_all(cfg: Config, recs, ents, loops) -> Tuple[int, List[str]]:
    pages: Dict[Path, str] = {}
    rc, msgs = _start_here(cfg, recs, ents, loops, pages)
    for p, text in pages.items():
        write_text_if_changed(p, text)
    for e in ents:
        path = e.dir / "AGENTS.md"
        text = path.read_text(encoding="utf-8")
        new = text
        for block, content in _entity_blocks(cfg, e, recs).items():
            new = gen.fill(new, block, content, "## %s" % block.capitalize())
        err = caps.entity_agents(cfg, new)
        if err and new != text:
            msgs.append("over cap, not written: %s (%s)" % (cfg.rel(path), err))
            rc = caps.EXIT_OVER_CAP
            continue
        write_text_if_changed(path, new)
    return rc, msgs
