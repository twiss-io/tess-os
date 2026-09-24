"""`tessbrain.py lint`: exit 1 on any error (0 with --warn-only).

Checks: accepted records carry source_quote/source_at and a source_ref that
resolves to a line containing the quote; accepted bodies match body_sha256;
records are reachable from START HERE; people files carry no deny-listed key
and no NRIC/FIN value; AGENTS chain <= 24 KiB (warn 20); entity AGENTS.md
<= 6 KiB / 100 lines with START HERE in the first 80 lines.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from . import caps, entities, frontmatter, gitutil, lookup, reach, records
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
