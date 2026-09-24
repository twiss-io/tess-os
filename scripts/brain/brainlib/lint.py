"""`tessbrain.py lint`: exit 1 on any error (0 with --warn-only).

Checks: accepted records carry source_quote/source_at and a source_ref that
resolves to a line containing the quote; accepted bodies match body_sha256;
records are reachable from START HERE; one session holds at most one accepted
decision per topic, no accepted decision has a later same-topic candidate in its
session, and no unconfirmed accepted decision has a later turn that raises V12
doubt (settle.py); people files carry no deny-listed key
and no NRIC/FIN value; AGENTS chain <= 24 KiB (warn 20); entity AGENTS.md
<= 6 KiB / 100 lines with START HERE in the first 80 lines.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from . import caps, entities, frontmatter, gitutil, inbox, lookup, reach, records, settle, switch
from .config import Config
from .textutil import contains

DENY_KEYS = {"salary", "pay", "compensation", "equity", "bank", "dob", "birthday", "nric", "fin", "passport",
             "government_id", "address", "home_address", "personal_phone", "personal_email", "health", "medical",
             "diagnosis", "disability", "performance", "rating", "review", "pip", "disciplinary", "grievance", "gwc",
             "religion", "ethnicity", "marital", "family"}
NRIC = re.compile(r"\b[STFGM]\d{7}[A-Z]\b")
REQUIRED = {"decision": ("source_quote", "source_at", "source_ref"), "preference": ("source_quote", "source_ref"),
            "correction": ("source_quote", "source_ref"), "fact": ("source_ref",)}
HASHED = ("accepted", "superseded", "retracted", "active")


def _record_issues(cfg: Config, rec: records.Record) -> List[str]:
    out = []
    rel = rec.rel(cfg)
    if rec.status in ("accepted", "active") and rec.kind in REQUIRED:
        for field in REQUIRED[rec.kind]:
            if not str(rec.meta.get(field) or "").strip():
                out.append("%s: accepted record lacks %s" % (rel, field))
        ref = str(rec.meta.get("source_ref") or "")
        if ref and rec.kind in ("decision", "preference", "correction"):
            line = lookup.resolve(cfg, ref)
            if line is None or ref.startswith("turns:"):
                if not _stub_ok(cfg, ref):
                    out.append("%s: source_ref %s does not resolve" % (rel, ref))
            elif not contains(line.text, str(rec.meta.get("source_quote") or "")):
                out.append("%s: the line %s does not contain the source_quote" % (rel, ref))
    want = rec.meta.get("body_sha256")
    if rec.status in HASHED and want and records.body_hash(rec.body) != want:
        out.append("%s: body changed after acceptance (body_sha256 mismatch); supersede, never edit" % rel)
    if rec.status in ("accepted",) and rec.kind == "decision" and not want:
        out.append("%s: accepted decision has no body_sha256" % rel)
    meta_want = rec.meta.get("meta_sha256")
    if meta_want and records.meta_hash(rec.meta) != meta_want:
        out.append("%s: front matter (title, statement, status, quote, ...) was edited by hand (meta_sha256 "
                   "mismatch); supersede or use tessbrain.py review/retract, never edit" % rel)
    elif want and not meta_want:
        out.append("%s: record has body_sha256 but no meta_sha256 (front matter edited by hand)" % rel)
    return out


def _session_key(rec: records.Record) -> str:
    ref = str(rec.meta.get("source_ref") or "")
    return str(rec.meta.get("source_session") or "") or ("" if ref.startswith("turns:") else ref.partition("#")[0])


def _same_session_issues(cfg: Config, checked: List[records.Record], recs: List[records.Record]) -> List[str]:
    """Two accepted decisions from one session on the same topic: the earlier one was probably
    switched away from ("let's use Postgres" ... "actually, go with SQLite"). Same topic = a shared
    subject word, or (while either is unconfirmed) one quote reads as a switch from the other by
    the V12 rules. The verifier never auto-accepts such a pair: it was hand-written or pre-V12."""
    out = []
    acc = [r for r in recs if r.kind == "decision" and r.status == "accepted" and _session_key(r)]
    ids = {r.id for r in checked}
    for i, a in enumerate(acc):
        for b in acc[i + 1:]:
            if _session_key(a) != _session_key(b) or not ({a.id, b.id} & ids):
                continue
            qa, qb = str(a.meta.get("source_quote") or ""), str(b.meta.get("source_quote") or "")
            shared = switch.topic(_topic_text(a)) & switch.topic(_topic_text(b))
            unconfirmed = a.meta.get("confirmed") is not True or b.meta.get("confirmed") is not True
            switched = unconfirmed and bool(switch.switch_in(qa, [qb]) or switch.switch_in(qb, [qa]))
            if shared or switched:
                out.append("%s and %s: two accepted decisions on the same topic from one session (%s); the "
                           "earlier one was probably switched away from: review, supersede or retract one"
                           % (a.rel(cfg), b.rel(cfg), ", ".join(sorted(shared)) or "one reads as a switch"))
    return out


PENDING_D = ("proposed", "pending-verification", "unverified")


def _later_candidates(cfg: Config, checked: List[records.Record], recs: List[records.Record]) -> List[str]:
    """An accepted decision with a later same-topic candidate in its session (inbox or a record awaiting
    review), or, while unconfirmed, a later turn that raises V12 doubt: it was probably switched away from."""
    out = []
    pend = [(str(c.get("source_ref") or ""), str(c.get("quote") or ""), "inbox %s" % c.get("id"))
            for c in inbox.pending(cfg) if c.get("kind") == "decision"]
    pend += [(str(r.meta.get("source_ref") or ""), str(r.meta.get("source_quote") or ""), r.rel(cfg))
             for r in recs if r.kind == "decision" and r.status in PENDING_D]
    for a in checked:
        if a.kind != "decision" or a.status != "accepted":
            continue
        ref, quote = str(a.meta.get("source_ref") or ""), str(a.meta.get("source_quote") or "")
        line = lookup.resolve(cfg, ref) if ref and not ref.startswith("turns:") else None
        if line is None:
            continue
        for pref, pquote, where in pend:
            other = lookup.resolve(cfg, pref) if pref.partition("#")[0] == line.path else None
            if other is None or other.order <= line.order and pref != ref:
                continue
            shared = switch.topic(_topic_text(a)) & switch.topic(pquote)
            if pref == ref and not _after_in_line(line.text, quote, pquote):
                continue
            if shared or switch.switch_in(quote, [pquote]):
                out.append("%s: accepted, but a later candidate on the same topic in its session (%s: %r) awaits "
                           "review; review, supersede or retract one" % (a.rel(cfg), where, pquote[:60]))
                break
        else:
            why = (settle.any_doubt(cfg, line, quote, settle.strict_for(str(a.meta.get("detected_by") or "")))
                   if a.meta.get("confirmed") is not True else None)
            if why:
                out.append("%s: accepted without confirmation, but %s" % (a.rel(cfg), why))
    return out


def _after_in_line(text: str, first: str, second: str) -> bool:
    t = text.lower()
    i, j = t.find(first.lower()), t.find(second.lower())
    return i >= 0 and j > i


def _topic_text(rec: records.Record) -> str:
    return " ".join(str(rec.meta.get(k) or "") for k in ("title", "source_quote"))


def _stub_ok(cfg: Config, ref: str) -> bool:
    """A stub-only journal keeps its body local: the committed stub must exist."""
    path = ref.partition("#")[0]
    p = cfg.root / path
    return p.is_file() and bool(frontmatter.read(p)[0].get("stub"))


def _people_issues(cfg: Config, only: Optional[set]) -> List[str]:
    out = []
    for p in sorted(cfg.brain.rglob("people/*.md")) if cfg.brain.is_dir() else []:
        rel = p.relative_to(cfg.root).as_posix()
        if only is not None and rel not in only or ".private" in p.parts:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        meta, _ = frontmatter.parse(text)
        bad = sorted(k for k in meta if k.lower() in DENY_KEYS)
        if bad:
            out.append("%s: deny-listed person field(s): %s (keep a pointer to where it lives instead)"
                       % (rel, ", ".join(bad)))
        if NRIC.search(text):
            out.append("%s: contains an NRIC/FIN-shaped value" % rel)
    return out


def _agents_issues(cfg: Config) -> List[str]:
    out = []
    warn, fail = caps.chain_limits(cfg)
    for e in entities.discover(cfg):
        path = e.dir / "AGENTS.md"
        rel = cfg.rel(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        err = caps.entity_agents(cfg, text)
        if err:
            out.append("%s: entity AGENTS.md over budget (%s)" % (rel, err))
        n = caps.start_here_line(text)
        if n is None or n > 80:
            out.append("%s: '# START HERE' is not within the first 80 lines" % rel)
        total = caps.chain_bytes(cfg, e.dir)
        if total > fail:
            out.append("%s: AGENTS chain root->entity is %d B > %d B (Codex cuts silently at 32 KiB)" % (rel, total, fail))
    return out


def run(cfg: Config, staged: bool = False) -> Dict[str, List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    only = set(gitutil.staged_files(cfg.root)) if staged else None
    recs = records.all_records(cfg)
    for rec in recs:
        if only is not None and rec.rel(cfg) not in only:
            continue
        errors += _record_issues(cfg, rec)
    checked = [r for r in recs if only is None or r.rel(cfg) in only]
    errors += _same_session_issues(cfg, checked, recs)
    errors += _later_candidates(cfg, checked, recs)
    seen = reach.reachable(cfg)
    for rec in recs:
        if (only is None or rec.rel(cfg) in only) and rec.path not in seen and not reach.exempt(cfg, rec.path):
            errors.append("%s: not reachable from brain/START-HERE.md or a generated index (run tessbrain.py index)"
                          % rec.rel(cfg))
    errors += _people_issues(cfg, only)
    errors += _agents_issues(cfg)
    warn, _ = caps.chain_limits(cfg)
    for e in entities.discover(cfg):
        total = caps.chain_bytes(cfg, e.dir)
        if warn < total <= caps.chain_limits(cfg)[1]:
            warnings.append("%s: AGENTS chain is %d B (warn at %d B)" % (cfg.rel(e.dir / "AGENTS.md"), total, warn))
    return {"errors": errors, "warnings": warnings}
