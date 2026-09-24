"""Durable records: D (decision), P (preference), C (correction), F (fact),
L (loop). Ids `<T>-YYYYMMDD-HHMM-<slug>` in operator time; never reused.

Append-only: a record body is hashed at acceptance (body_sha256) and lint
fails on any later change. Only the tool edits front matter, and only these
fields: status, superseded_by, confirmed, verified*, source_ref (pending ->
journal), body_sha256 at acceptance, confirmed_by/at.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from . import frontmatter
from .config import Config, iso, parse_iso
from .textutil import sha256_text, slugify

PREFIX = {"decision": "D", "preference": "P", "correction": "C", "fact": "F", "open_loop": "L"}
TYPE_OF = {v: k for k, v in PREFIX.items()}
ID_RX = re.compile(r"^([DPCFL])-(\d{8})-(\d{4})-([a-z0-9-]+?)(?:-(\d+))?$")
FILE_GLOB = "[DPCFL]-[0-9]*.md"
TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "record-bodies"

ORDER = {
    "decision": ["schema", "id", "type", "kind", "title", "status", "tier", "authority", "decided_by", "decider_seat",
                 "entity", "consulted", "informed", "source_quote", "also_quoted", "source_speaker", "source_at",
                 "source_ref", "source_session", "approves_quote", "delegation_ref", "detected_by", "confirmed",
                 "verified", "verified_at", "supersedes", "superseded_by", "body_sha256", "tags"],
    "preference": ["schema", "id", "type", "status", "statement", "scope", "principal", "corrects", "source_quote",
                   "source_speaker", "source_at", "source_ref", "source_session", "detected_by", "verified",
                   "verified_at", "confirmed", "supersedes", "superseded_by", "body_sha256"],
    "fact": ["schema", "id", "type", "entity", "status", "statement", "source_kind", "source_quote", "source_speaker",
             "source_at", "source_ref", "detected_by", "verified", "verified_at", "confidence", "valid_from",
             "valid_until", "last_verified", "verify_via", "confirmed", "body_sha256"],
    "open_loop": ["schema", "id", "type", "entity", "statement", "status", "owner", "due", "source_quote",
                  "source_speaker", "source_at", "source_ref", "detected_by", "verified_at", "confirmed_by",
                  "confirmed_at", "body_sha256"],
}
ORDER["correction"] = ORDER["preference"]
ACTIVE = {"accepted", "active", "proposed", "pending-verification", "waiting"}


class Record:
    def __init__(self, path: Path, meta: Dict, body: str):
        self.path, self.meta, self.body = Path(path), meta, body

    @property
    def id(self) -> str:
        return str(self.meta.get("id") or self.path.stem)

    @property
    def kind(self) -> str:
        return TYPE_OF.get(self.id[:1], str(self.meta.get("type") or ""))

    @property
    def status(self) -> str:
        return str(self.meta.get("status") or "")

    def rel(self, cfg: Config) -> str:
        return self.path.relative_to(cfg.root).as_posix()


def body_hash(body: str) -> str:
    return sha256_text(body)


def load(path: Path) -> Record:
    meta, body = frontmatter.read(path)
    return Record(path, meta, body)


def all_records(cfg: Config) -> List[Record]:
    out: List[Record] = []
    if not cfg.brain.is_dir():
        return out
    for p in sorted(cfg.brain.rglob(FILE_GLOB)):
        rel = p.relative_to(cfg.brain).parts
        if ".private" in rel or rel[0] in ("journal", "inbox", "index", "kb"):
            continue
        if ID_RX.match(p.stem):
            try:
                out.append(load(p))
            except (OSError, UnicodeDecodeError):
                continue
    return out


def find(cfg: Config, rid: str) -> Optional[Record]:
    for r in all_records(cfg):
        if r.id == rid:
            return r
    return None


def new_id(cfg: Config, kind: str, at: str, text: str, taken: Optional[set] = None) -> str:
    try:
        t = cfg.local(at)
    except (ValueError, TypeError):
        t = cfg.now()
    base = "%s-%s-%s" % (PREFIX[kind], t.strftime("%Y%m%d-%H%M"), slugify(text))
    used = taken if taken is not None else {r.id for r in all_records(cfg)}
    rid, n = base, 2
    while rid in used:
        rid = "%s-%d" % (base, n)
        n += 1
    return rid


def render_body(kind: str, fields: Dict) -> str:
    name = {"open_loop": "loop"}.get(kind, kind)
    tpl = (TEMPLATES / ("%s.md" % name)).read_text(encoding="utf-8")
    safe = {k: ("" if v is None else v) for k, v in fields.items()}
    return tpl.format_map(_Default(safe))


class _Default(dict):
    def __missing__(self, key):
        return ""


def write(cfg: Config, kind: str, directory: Path, meta: Dict, body_fields: Dict) -> Record:
    body = render_body(kind, body_fields)
    meta = dict(meta)
    meta.setdefault("schema", 1)
    if meta.get("status") in ("accepted", "active") or kind in ("fact", "open_loop"):
        meta["body_sha256"] = body_hash(body)
    path = Path(directory) / ("%s.md" % meta["id"])
    if path.exists():
        raise FileExistsError("record exists: %s" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter.dump(meta, body, ORDER.get(kind)), encoding="utf-8")
    return load(path)


def update_fields(rec: Record, updates: Dict) -> Record:
    """Rewrite front matter only; the body bytes stay identical."""
    meta = dict(rec.meta)
    meta.update(updates)
    if meta.get("status") in ("accepted", "active") and not meta.get("body_sha256"):
        meta["body_sha256"] = body_hash(rec.body)
    rec.path.write_text(frontmatter.dump(meta, rec.body, ORDER.get(rec.kind)), encoding="utf-8")
    return load(rec.path)


def sort_key(rec: Record) -> str:
    try:
        return iso(parse_iso(str(rec.meta.get("verified_at") or rec.meta.get("source_at") or "")))
    except (ValueError, TypeError):
        m = ID_RX.match(rec.id)
        return "%s-%s" % (m.group(2), m.group(3)) if m else rec.id


def register_rel(cfg: Config, directory: Path) -> str:
    """Target register path relative to brain/ (what V9 scope globs match)."""
    return Path(directory).resolve().relative_to(cfg.brain.resolve()).as_posix()
