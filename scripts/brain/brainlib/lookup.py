"""Read side of the journal: resolve `path#L<n>` refs and search quotes.

A source_ref is `brain/journal/.../HHMM-<runtime>-<sid8>.md#L<n>` (a message
label, stable across appends) or `turns:<n>` for a turn not yet journaled.
Stub-only journals keep their bodies in .tess/state/brain/journal/.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from . import turns
from .config import Config
from .textutil import contains

_LINE = re.compile(r"^\[([LR])(\d+) (\S+) (\S+) (\S+)\] ?(.*)$")
_SESSION_FILE = re.compile(r"^\d{4}-[a-z0-9]+-[A-Za-z0-9]+(?:-\d+)?\.md$")


class JLine:
    __slots__ = ("ref", "label", "speaker", "channel", "text", "principal", "kind", "path", "index", "hhmm")

    @property
    def order(self):
        """Conversation order: L<k> < R<k> (the reply to L<k>) < L<k+1>."""
        try:
            return (int(str(self.label)[1:]), 1 if str(self.label).startswith("R") else 0)
        except ValueError:
            return (self.index or 0, 0)

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


_CACHE: Dict[str, List[JLine]] = {}


def parse_file(cfg: Config, path: Path, ref_path: str) -> List[JLine]:
    key = str(path)
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return []
    cached = _CACHE.get(key)
    if cached is not None and getattr(parse_file, "_m", {}).get(key) == mtime:
        return cached
    out: List[JLine] = []
    cur: Optional[JLine] = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _LINE.match(raw)
        if m:
            label = m.group(1) + m.group(2)
            speaker = m.group(4)
            principal = m.group(1) == "L" and cfg.principal(speaker) is not None
            cur = JLine(ref="%s#%s" % (ref_path, label), label=label, speaker=speaker, channel=m.group(5),
                        text=m.group(6), principal=principal, kind="msg" if m.group(1) == "L" else "reply",
                        path=ref_path, index=len(out), hhmm=m.group(3))
            out.append(cur)
        elif cur is not None and raw.startswith("  "):
            cur.text += "\n" + raw[2:]
        else:
            cur = None
    _CACHE[key] = out
    parse_file._m = dict(getattr(parse_file, "_m", {}), **{key: mtime})  # type: ignore[attr-defined]
    return out


def lines_for(cfg: Config, ref_path: str) -> List[JLine]:
    """All labelled lines of one session file (committed body, else local body)."""
    rel = ref_path[len("brain/"):] if ref_path.startswith("brain/") else ref_path
    for p in (cfg.brain / rel, cfg.state / rel):
        if p.is_file():
            got = parse_file(cfg, p, ref_path)
            if got:
                return got
    return []


def resolve(cfg: Config, ref: str) -> Optional[JLine]:
    if not ref:
        return None
    if ref.startswith("turns:"):
        try:
            rec = turns.get(cfg, int(ref.split(":", 1)[1].lstrip("#")))
        except ValueError:
            return None
        if not rec:
            return None
        return JLine(ref=ref, label="T%s" % rec["n"], speaker=rec.get("speaker"), channel=rec.get("runtime"),
                     text=rec.get("text", ""), principal=bool(rec.get("principal")), kind="turn",
                     path="turns", index=int(rec["n"]))
    path, _, label = ref.partition("#")
    for line in lines_for(cfg, path):
        if line.label == label:
            return line
    return None


def session_files(cfg: Config) -> List[str]:
    """brain-relative ref paths of every journal session file, newest first."""
    seen = set()
    for base in (cfg.brain / "journal", cfg.state / "journal"):
        if not base.is_dir():
            continue
        for p in base.glob("*/*/*/*.md"):
            if _SESSION_FILE.match(p.name):
                seen.add("brain/journal/" + p.relative_to(base).as_posix())
    return sorted(seen, reverse=True)


def search(cfg: Config, quote: str, max_files: int = 400) -> List[JLine]:
    """Journal lines then turns containing the quote; principal hits first."""
    hits: List[JLine] = []
    for ref_path in session_files(cfg)[:max_files]:
        for line in lines_for(cfg, ref_path):
            if contains(line.text, quote):
                hits.append(line)
    for rec in reversed(turns.read(cfg)):
        if contains(rec.get("text", ""), quote):
            hits.append(resolve(cfg, "turns:%s" % rec["n"]))
    hits = [h for h in hits if h is not None]
    hits.sort(key=lambda h: (not h.principal, h.kind == "turn"))
    return hits


def session_meta(cfg: Config, ref_path: str) -> Dict:
    from . import frontmatter
    rel = ref_path[len("brain/"):] if ref_path.startswith("brain/") else ref_path
    for p in (cfg.brain / rel, cfg.state / rel):
        if p.is_file():
            return frontmatter.read(p)[0]
    return {}


def line_time(cfg: Config, line: JLine) -> str:
    """Best ISO time for a line: the turn's timestamp, else session start date + HH:MM."""
    import datetime as _dt
    from .config import iso, parse_iso
    if line.kind == "turn":
        rec = turns.get(cfg, int(line.index))
        return str((rec or {}).get("at") or "")
    meta = session_meta(cfg, line.path)
    try:
        start = parse_iso(str(meta.get("started_at") or "")).astimezone(cfg.tz).replace(second=0, microsecond=0)
    except (ValueError, TypeError):
        return str(meta.get("updated_at") or "")
    if not re.match(r"^\d\d:\d\d$", line.hhmm or ""):
        return iso(start)
    t = start.replace(hour=int(line.hhmm[:2]), minute=int(line.hhmm[3:]))
    if t < start:
        t += _dt.timedelta(days=1)
    return iso(t)
