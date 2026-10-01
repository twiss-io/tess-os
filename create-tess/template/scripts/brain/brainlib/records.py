"""Durable records: D (decision), P (preference), C (correction), F (fact),
L (loop). Ids `<T>-YYYYMMDD-HHMM-<slug>` in operator time; never reused.

Append-only: a record body is hashed at acceptance (body_sha256) and lint
fails on any later change. Only the tool edits front matter, and only these
fields: status, superseded_by, confirmed, verified*, source_ref (pending ->
journal), body_sha256 at acceptance, confirmed_by/at.

Seals (v1.0.0 audit: record status read from unauthenticated front matter).
body_sha256 and meta_sha256 are plain hashes any writer can recompute, so a
planted or hand-edited record file (an agent's Write, a pulled commit) that
says `status: accepted` / `confirmed: true` was published as accepted memory.
Every file this tool writes is now SEALED: a row in the MAC'd external ledger
(extstate.py) naming the record id, its path and the sha256 of its exact
text. A record whose file does not match its latest seal reads, everywhere,
as `proposed` (awaiting the operator's review) and never as confirmed:
Record.status / Record.confirmed. The raw front matter stays in rec.meta.

Round 6 (GPT-6 items 9 and 10): a seal vouches only for what a trusted writer
made. A seal row names the status/confirmed of the text it seals (read from
that text, never from the caller) and counts only while the file still says
the same. A seal made where the external ledger cannot be written (the Codex
sandbox: a pending outbox row, or one a hook drained from the outbox, marked
`origin: outbox`) never vouches for an accepted/active/confirmed record, and a
record it sealed is elevated only by being rebuilt from verified fields
(promote.recheck_pending) or by the operator's confirmation. Bookkeeping never
seals a file no seal vouched for (update_fields).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import frontmatter
from .config import Config, iso, parse_iso
from .textutil import sha256_text, slugify
from oobe.state import atomic_write  # scripts/brain is on sys.path wherever brainlib loads

PREFIX = {"decision": "D", "preference": "P", "correction": "C", "fact": "F", "open_loop": "L"}
TYPE_OF = {v: k for k, v in PREFIX.items()}
ID_RX = re.compile(r"^([DPCFL])-(\d{8})-(\d{4})-([a-z0-9-]+?)(?:-(\d+))?$")
FILE_GLOB = "[DPCFL]-[0-9]*.md"
TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "records"

ORDER = {
    "decision": ["schema", "id", "type", "kind", "title", "status", "tier", "authority", "decided_by", "decider_seat",
                 "entity", "consulted", "informed", "source_quote", "also_quoted", "source_speaker", "source_at",
                 "source_ref", "source_session", "approves_quote", "delegation_ref", "detected_by", "confirmed",
                 "verified", "verified_at", "supersedes", "superseded_by", "body_sha256", "meta_sha256", "tags"],
    "preference": ["schema", "id", "type", "status", "statement", "scope", "principal", "corrects", "source_quote",
                   "source_speaker", "source_at", "source_ref", "source_session", "detected_by", "verified",
                   "verified_at", "confirmed", "supersedes", "superseded_by", "body_sha256", "meta_sha256"],
    "fact": ["schema", "id", "type", "entity", "status", "statement", "source_kind", "source_quote", "source_speaker",
             "source_at", "source_ref", "detected_by", "verified", "verified_at", "confidence", "valid_from",
             "valid_until", "last_verified", "verify_via", "confirmed", "body_sha256", "meta_sha256"],
    "open_loop": ["schema", "id", "type", "entity", "statement", "status", "owner", "due", "source_quote",
                  "source_speaker", "source_at", "source_ref", "detected_by", "verified_at", "confirmed_by",
                  "confirmed_at", "body_sha256", "meta_sha256"],
}
ORDER["correction"] = ORDER["preference"]
ACTIVE = {"accepted", "active", "proposed", "pending-verification", "waiting"}
ELEVATED = ("accepted", "active")


class Record:
    def __init__(self, path: Path, meta: Dict, body: str, text_sha: str = ""):
        self.path, self.meta, self.body = Path(path), meta, body
        self.text_sha = text_sha
        self.cfg: Optional[Config] = None
        self.sealed: Optional[bool] = None  # None: not checked (a record built in memory, or just written)
        self.seal_trusted: Optional[bool] = None  # sealed by a process that could write the external ledger

    @property
    def id(self) -> str:
        return str(self.meta.get("id") or self.path.stem)

    @property
    def kind(self) -> str:
        return TYPE_OF.get(self.id[:1], str(self.meta.get("type") or ""))

    @property
    def raw_status(self) -> str:
        """The status the file says (lint and the integrity checks read this)."""
        return str(self.meta.get("status") or "")

    @property
    def status(self) -> str:
        """The status the brain acts on: an accepted/active record whose file no seal vouches for is only
        `proposed` (awaiting the operator's review)."""
        raw = self.raw_status
        return "proposed" if raw in ELEVATED and (self.sealed is False or self.seal_trusted is False) else raw

    @property
    def confirmed(self) -> bool:
        return self.meta.get("confirmed") is True and self.sealed is not False and self.seal_trusted is not False

    def rel(self, cfg: Config) -> str:
        return self.path.relative_to(cfg.root).as_posix()


def body_hash(body: str) -> str:
    return sha256_text(body)


# Front-matter fields only this tool may change (fix round 2): a hand edit of any
# of them (a tampered title, a status flipped to accepted) fails lint.
META_HASHED = ("id", "type", "title", "statement", "status", "tier", "authority", "decided_by", "entity", "scope",
               "principal", "corrects", "source_quote", "also_quoted", "source_speaker", "source_at", "source_ref",
               "approves_quote", "delegation_ref", "confirmed", "supersedes", "superseded_by", "owner", "due")


def _norm(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    return str(v)


def meta_hash(meta: Dict) -> str:
    return sha256_text(json.dumps([[k, _norm(meta.get(k))] for k in META_HASHED]))


def load(path: Path) -> Record:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    meta, body = frontmatter.parse(text)
    return Record(path, meta, body, sha256_text(text))


def _rel(cfg: Config, path: Path) -> str:
    try:
        return Path(path).relative_to(cfg.root).as_posix()
    except ValueError:
        return str(path)


def _flags(meta: Dict) -> Tuple[str, bool]:
    return str(meta.get("status") or ""), meta.get("confirmed") is True


def seal_row_trusted(row: Dict) -> bool:
    """A seal a process that could write the external ledger made: not a pending outbox row, and not one a
    hook drained from the outbox (extstate marks those `origin: outbox`; draining vouches for nothing)."""
    from .outbox import ORIGIN
    return not row.get("pending") and row.get("origin") != ORIGIN


def seal_state(cfg: Config, rec: Record, seals: Optional[Dict[str, Dict]] = None) -> Tuple[bool, bool]:
    """(sealed, trusted). Sealed: the file is exactly what was last sealed for its id, at this path, and it
    still says the status/confirmed that seal recorded. A seal made in the sandbox never vouches for an
    accepted/active/confirmed file (GPT-6 round 6, item 10)."""
    if seals is None:
        from . import provenance
        seals = provenance.record_seals(cfg)
    row = seals.get(rec.id)
    if not (row and rec.text_sha and row.get("h") == rec.text_sha and row.get("path") == _rel(cfg, rec.path)):
        return False, False
    status, confirmed = _flags(rec.meta)
    if str(row.get("status") or "") != status or (row.get("confirmed") is True) != confirmed:
        return False, False
    trusted = seal_row_trusted(row)
    if not trusted and (status in ELEVATED or confirmed):
        return False, False
    return True, trusted


def is_sealed(cfg: Config, rec: Record, seals: Optional[Dict[str, Dict]] = None) -> bool:
    """The record's file is exactly what this tool last wrote for its id, at this path (seal_state)."""
    return seal_state(cfg, rec, seals)[0]


def seal(cfg: Config, path: Path, text: str, meta: Optional[Dict] = None, sandbox: bool = False) -> bool:
    """Record in the external ledger that this tool wrote `text` at `path` (see the module docstring).
    The id, status and confirmed flag come from `text` itself, never from `meta` (GPT-6 round 6, item 10:
    a caller could seal an active, confirmed file as `proposed`). `sandbox`: the text is not vouched for by
    a trusted writer (it re-seals a file only the sandbox sealed), so the row keeps the sandbox origin.
    A shell that cannot write the ledger (the Codex sandbox) can only queue the seal of a record that is
    not accepted/active/confirmed (outbox.admissible); such a record is re-checked by the next hook.
    True when the seal is durable in the ledger as a trusted seal."""
    from . import provenance
    from .outbox import ORIGIN
    fm = frontmatter.parse(text)[0]
    status, confirmed = _flags(fm)
    row = {"t": "rec", "id": str(fm.get("id") or (meta or {}).get("id") or Path(path).stem),
           "path": _rel(cfg, path), "h": sha256_text(text), "status": status, "confirmed": confirmed}
    if sandbox:
        row["origin"] = ORIGIN
    return provenance._append(cfg, [row]) and not sandbox


def seal_file(cfg: Config, path: Path) -> None:
    """Seal a record file another part of Tess wrote (onboarding's first decision)."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        return
    seal(cfg, path, text)


def seal_existing_once(cfg: Config) -> None:
    """Upgrade: the first time a project's ledger can be written, seal the records already on disk, so an
    instance made before seals existed keeps its accepted records. Never again after that (a `seal-init` row
    in the ledger): a record that appears later is sealed only by the tool writing it."""
    from . import extstate, provenance
    if not cfg.brain.is_dir() or provenance.seal_init_done(cfg) or extstate.rows(cfg) is None \
            or not extstate.writable(cfg):
        return
    rows = []
    for rec in _scan(cfg):
        rows.append({"t": "rec", "id": rec.id, "path": _rel(cfg, rec.path), "h": rec.text_sha,
                     "status": rec.raw_status, "confirmed": rec.meta.get("confirmed") is True})
    provenance._append(cfg, rows + [{"t": "seal-init", "records": len(rows)}])


def _scan(cfg: Config) -> List[Record]:
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


def all_records(cfg: Config) -> List[Record]:
    out = _scan(cfg)
    if out:
        from . import provenance
        seals = provenance.record_seals(cfg)
        for rec in out:
            rec.cfg = cfg
            rec.sealed, rec.seal_trusted = seal_state(cfg, rec, seals)
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


def _render(kind: str, meta: Dict, body_fields: Dict) -> str:
    body = render_body(kind, body_fields)
    meta = dict(meta)
    meta.setdefault("schema", 1)
    if meta.get("status") in ("accepted", "active") or kind in ("fact", "open_loop"):
        meta["body_sha256"] = body_hash(body)
    meta["meta_sha256"] = meta_hash(meta)
    return frontmatter.dump(meta, body, ORDER.get(kind))


def write(cfg: Config, kind: str, directory: Path, meta: Dict, body_fields: Dict) -> Record:
    path = Path(directory) / ("%s.md" % meta["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    text = _render(kind, meta, body_fields)
    _create_new(path, text)
    seal(cfg, path, text)
    rec = load(path)
    rec.cfg = cfg
    return rec


def rebuild(rec: Record, meta: Dict, body_fields: Dict) -> Record:
    """Replace a record's whole file (front matter and body) with one made from `meta` and `body_fields`
    alone, as write() would make it, and seal it as vouched for by this process (promote.recheck_pending:
    the caller built both from verified fields only)."""
    text = _render(rec.kind, dict(meta, id=rec.id), body_fields)
    atomic_write(rec.path, text)
    trusted = seal(rec.cfg, rec.path, text) if rec.cfg is not None else False
    new = load(rec.path)
    new.cfg = rec.cfg
    new.sealed, new.seal_trusted = (True, True) if trusted else (None, None)
    return new


def _create_new(path: Path, text: str) -> None:
    """Create `path` with `text`, atomically, only if it does not exist yet.

    The full text goes to a temp file in the same directory first; os.link()
    then publishes it under the final name and fails with EEXIST if a record
    is already there -- the O_EXCL guarantee (no check-then-write race, no
    clobbering a concurrent writer) without O_EXCL's window where a crash
    leaves a half-written record behind.
    """
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        try:
            os.link(tmp, str(path))
        except FileExistsError:
            raise FileExistsError("record exists: %s" % path) from None
    finally:
        os.unlink(tmp)


def update_fields(rec: Record, updates: Dict, body: Optional[str] = None, vouch: bool = False) -> Record:
    """Rewrite front matter only; the body bytes stay identical (unless `body` replaces it: then its hash
    is recomputed).

    Sealing (GPT-6 round 6, item 9: bumping `verify_attempts` sealed a planted pending record, which the
    next hook then accepted, body and all): the result is re-sealed only when a seal vouched for the file
    being changed, and keeps that seal's origin (a file only the sandbox sealed stays the sandbox's). A file
    no seal vouches for stays unsealed, whatever the change. `vouch`: the operator's confirmation of this
    very content (promote.change_status), which seals it as trusted."""
    meta = dict(rec.meta)
    meta.update(updates)
    if body is not None:
        meta.pop("body_sha256", None)
        if meta.get("status") in ("accepted", "active") or rec.kind in ("fact", "open_loop"):
            meta["body_sha256"] = body_hash(body)
    text_body = rec.body if body is None else body
    if meta.get("status") in ("accepted", "active") and not meta.get("body_sha256"):
        meta["body_sha256"] = body_hash(text_body)
    meta["meta_sha256"] = meta_hash(meta)
    text = frontmatter.dump(meta, text_body, ORDER.get(rec.kind))
    atomic_write(rec.path, text)
    new = load(rec.path)
    new.cfg = rec.cfg
    if rec.cfg is not None and (vouch or rec.sealed):
        seal(rec.cfg, rec.path, text, sandbox=not vouch and not rec.seal_trusted)
    elif rec.sealed is False:
        new.sealed, new.seal_trusted = False, False
    return new


def sort_key(rec: Record) -> str:
    try:
        return iso(parse_iso(str(rec.meta.get("verified_at") or rec.meta.get("source_at") or "")))
    except (ValueError, TypeError):
        m = ID_RX.match(rec.id)
        return "%s-%s" % (m.group(2), m.group(3)) if m else rec.id


# Folders under brain/ that never hold records (all_records skips them).
REGISTER_EXCLUDED = ("journal", "inbox", "index", "kb")


def register_target(cfg: Config, target: str) -> Tuple[str, str]:
    """('brain/<folder>', '') for a register folder inside brain/, else ('', the plain reason).

    v1.0.0 audit (unvalidated register target): `decide --register` and `inbox add --register` were joined
    onto the instance root unchecked, so `../x`, an absolute path or `brain/clients/acme/../../decisions`
    (which also passed a scoped principal's V9 glob) wrote a record outside brain/ or outside the scope.
    Now the folder must be a plain relative path under brain/ (a leading `brain/` is optional), with no
    `.`, `..` or hidden part, not journal/inbox/index/kb, and no link on the way that leads elsewhere."""
    raw = str(target or "").strip()
    bad = ("the register %r is not a folder inside brain/; use one like brain/decisions or "
           "brain/clients/acme/decisions" % raw)
    if not raw or "\\" in raw or "\x00" in raw or os.path.isabs(raw) or raw.startswith("~"):
        return "", bad
    rel = raw.strip("/")
    if rel == "brain":
        return "", bad
    if rel.startswith("brain/"):
        rel = rel[len("brain/"):]
    parts = rel.split("/")
    if any(p in ("", ".", "..") or p.startswith(".") for p in parts) or parts[0] in REGISTER_EXCLUDED:
        return "", bad
    cur = cfg.brain
    for part in parts:
        cur = cur / part
        if cur.is_symlink():
            return "", bad + " (%s is a link)" % cur.relative_to(cfg.root).as_posix()
    top, real = os.path.realpath(str(cfg.brain)), os.path.realpath(str(cfg.brain / rel))
    if not real.startswith(top + os.sep):
        return "", bad
    return "brain/" + "/".join(parts), ""


def register_rel(cfg: Config, directory: Path) -> str:
    """Target register path relative to brain/ (what V9 scope globs match)."""
    return Path(directory).resolve().relative_to(cfg.brain.resolve()).as_posix()
