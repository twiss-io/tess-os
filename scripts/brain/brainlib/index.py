"""`tessbrain.py index`: regenerate every generated file and marker block.

Writes only `generated: true` files and the text between tess:gen markers.
Deterministic (no wall-clock stamps), writes only on change, and refuses a
file that would go over its cap (exit 3, file left byte-identical).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from . import caps, entities, gen, journal_index, records
from .config import Config, write_text_if_changed
from .gen import Item
from .textutil import clip

ACTIVE_D = ("accepted", "proposed", "pending-verification")
OPEN_L = ("proposed", "active", "waiting")


def _date(rec: records.Record) -> str:
    return records.sort_key(rec)[:16].replace("T", " ")


def _by_dir(recs: List[records.Record], kind: str) -> Dict[Path, List[records.Record]]:
    out: Dict[Path, List[records.Record]] = {}
    for r in recs:
        if r.kind == kind:
            out.setdefault(r.path.parent, []).append(r)
    return out


def _newest(recs: List[records.Record]) -> List[records.Record]:
    return sorted(recs, key=lambda r: (records.sort_key(r), r.id), reverse=True)


def _ditem(r: records.Record) -> Item:
    return Item(str(r.meta.get("title") or r.id), r.path, "%s " % _date(r)[:10],
                " (%s%s)" % (r.status, ", material" if r.meta.get("tier") == "material" else ""))


def _decision_pages(cfg: Config, recs, writes: Dict[Path, str]) -> None:
    dirs = _by_dir(recs, "decision")
    dirs.setdefault(cfg.brain / "decisions", [])
    for d, rs in dirs.items():
        rel_key = records.register_rel(cfg, d).replace("/", "-")
        active = [r for r in _newest(rs) if r.status in ACTIVE_D and r.meta.get("kind") != "question"]
        questions = [r for r in _newest(rs) if r.meta.get("kind") == "question" and r.status in ACTIVE_D]
        lines, pages = gen.listing(cfg.brain, d, [_ditem(r) for r in active], rel_key + "-active", "Active decisions")
        writes.update(pages)
        body = ["## Active", ""] + (lines or ["(none yet)"])
        if questions:
            body += ["", "## Open questions", ""] + [_ditem(q).render(d) for q in questions]
        if d == cfg.brain / "decisions":
            subs = sorted(x for x in dirs if x != d)
            body += ["", "## Entity registers", ""] + ([Item(records.register_rel(cfg, x), x / "INDEX.md").render(d)
                                                        for x in subs] or ["(none)"])
        body += ["", "Full history: [ALL.md](ALL.md)"]
        writes[d / "INDEX.md"] = gen.page("Decisions: %s" % records.register_rel(cfg, d), body)
        lines, pages = gen.listing(cfg.brain, d, [_ditem(r) for r in _newest(rs)], rel_key + "-all", "All decisions")
        writes.update(pages)
        writes[d / "ALL.md"] = gen.page("All decisions: %s" % records.register_rel(cfg, d), lines)


def _simple_indexes(cfg: Config, recs, writes: Dict[Path, str]) -> None:
    for kind, title in (("fact", "Facts"), ("open_loop", "Loops")):
        for d, rs in _by_dir(recs, kind).items():
            items = [Item(clip(str(r.meta.get("statement") or r.id), 120), r.path, "", " (%s)" % r.status)
                     for r in _newest(rs)]
            lines, pages = gen.listing(cfg.brain, d, items, records.register_rel(cfg, d).replace("/", "-"), title)
            writes.update(pages)
            writes[d / "INDEX.md"] = gen.page("%s: %s" % (title, records.register_rel(cfg, d)), lines)
    prof = [r for r in recs if r.kind in ("preference", "correction")]
    d = cfg.brain / "profile"
    items = [Item(clip(str(r.meta.get("statement") or r.id), 120), r.path, "%s " % r.id[:1], " (%s)" % r.status)
             for r in _newest(prof)]
    lines, pages = gen.listing(cfg.brain, d, items, "profile-all", "Profile records")
    writes.update(pages)
    if prof:
        writes[d / "INDEX.md"] = gen.page("Profile records (all)", lines)


def _profile(cfg: Config, recs) -> str:
    body: List[str] = []
    for kind, title in (("preference", "Preferences"), ("correction", "Corrections")):
        act = [r for r in _newest(recs) if r.kind == kind and r.status == "active"]
        body += ["## %s" % title, ""]
        body += ["- %s ([%s](%s))%s" % (clip(str(r.meta.get("statement") or ""), 300), r.id,
                                       gen.link(cfg.brain, r.path), "" if r.meta.get("confirmed") else " *unconfirmed*")
                 for r in act] or ["(none yet)"]
        body.append("")
    return gen.page("Operator profile (what the brain has learned about how to work with you)", body)


def _learned(cfg: Config, recs) -> Tuple[str, Dict[Path, str]]:
    shown = [r for r in _newest(recs) if r.status not in ("pending-verification", "unverified")]
    cap = cfg.budgets["learned_entries"]

    def line(r, from_dir):
        ref = str(r.meta.get("source_ref") or "")
        src = ref.partition("#")
        slink = ("[source](%s#%s)" % (gen.link(from_dir, cfg.root / src[0]), src[2])) if src[0].startswith("brain/") else ref
        stmt = r.meta.get("title") if r.kind == "decision" else r.meta.get("statement")
        return "- %s · %s · \"%s\" · [%s](%s) · %s · %s%s" % (
            _date(r), r.kind.replace("_", " "), clip(str(stmt or ""), 140), r.id, gen.link(from_dir, r.path), slink,
            r.meta.get("detected_by") or "", "" if r.status in ("accepted", "active", "proposed") else " (now %s)" % r.status)
    archive: Dict[Path, List[str]] = {}
    for r in shown[cap:]:
        archive.setdefault(cfg.brain / "archive" / ("learned-%s.md" % _date(r)[:4]), []).append(line(r, cfg.brain / "archive"))
    extra = {p: gen.page("Learned (archive %s)" % p.stem[-4:], ls) for p, ls in archive.items()}
    body = [line(r, cfg.brain) for r in shown[:cap]]
    if archive:
        body += ["", "Older: " + ", ".join("[%s](archive/%s)" % (p.stem, p.name) for p in sorted(archive))]
    return gen.page("Learned (newest first; undo any line with `tessbrain.py retract <id> --quote \"...\"`)", body), extra


def _open_loops(cfg: Config, recs) -> List[records.Record]:
    return [r for r in _newest(recs) if r.kind == "open_loop" and r.status in OPEN_L]


def regenerate(cfg: Config) -> Tuple[int, List[str]]:
    """-> (exit code, messages). 0 ok, 3 when a file would go over its cap."""
    recs = records.all_records(cfg)
    ents = entities.discover(cfg)
    writes: Dict[Path, str] = {}
    _decision_pages(cfg, recs, writes)
    _simple_indexes(cfg, recs, writes)
    writes[cfg.brain / "profile.md"] = _profile(cfg, recs)
    learned, extra = _learned(cfg, recs)
    writes[cfg.brain / "learned.md"] = learned
    writes.update(extra)
    loops = _open_loops(cfg, recs)
    items = [Item(clip(str(r.meta.get("statement") or ""), 120), r.path, "", " (%s)" % r.status) for r in loops]
    lines, pages = gen.listing(cfg.brain, cfg.brain, items, "open-loops", "Open loops")
    writes.update(pages)
    writes[cfg.brain / "open-loops.md"] = gen.page("Open loops", lines)
    writes.update(journal_index.pages(cfg))
    from . import index_blocks
    msgs: List[str] = []
    rc = 0
    for path, text in sorted(writes.items()):
        err = caps.profile(cfg, text) if path.name == "profile.md" else caps.index_file(cfg, text)
        if err:
            msgs.append("over cap, not written: %s (%s); consolidate: brain-review --consolidate" % (cfg.rel(path), err))
            rc = caps.EXIT_OVER_CAP
            continue
        write_text_if_changed(path, text)
    brc, bmsgs = index_blocks.fill_all(cfg, recs, ents, loops)
    return max(rc, brc), msgs + bmsgs
