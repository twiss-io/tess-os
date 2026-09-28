"""Current-turn capture: UserPromptSubmit appends the REDACTED prompt to
.tess/state/brain/turns.jsonl, so a quote from the turn being answered can be
verified before the runtime flushes its own transcript (which can lag).
turns.jsonl is local state (self-ignoring directory) and never committed.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from . import redact
from .config import Config, iso

MAX_TURNS_READ = 2000


def _path(cfg: Config):
    return cfg.state / "turns.jsonl"


def append(cfg: Config, runtime: str, session: str, text: str, raw_speaker: str = "operator",
           at: Optional[str] = None) -> Dict:
    """Append one redacted turn; non-principal text is never stored."""
    cfg.ensure_state()
    slug = cfg.resolve_speaker(raw_speaker)
    principal = bool(slug) and cfg.consents(slug)
    clean, counts = redact.redact(text or "")
    rows = read(cfg, limit=None)
    rec = {
        "n": (rows[-1]["n"] + 1) if rows else 1,
        "session": session or "", "runtime": runtime, "at": at or iso(cfg.now()),
        "speaker": slug if principal else raw_speaker, "principal": principal,
        "text": clean if principal else "[non-principal %s omitted: no consent]" % raw_speaker,
        "redactions": redact.total(counts),
    }
    with open(_path(cfg), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return rec


def read(cfg: Config, limit: Optional[int] = MAX_TURNS_READ) -> List[Dict]:
    p = _path(cfg)
    if not p.is_file():
        return []
    out: List[Dict] = []
    with open(p, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and "n" in rec:
                out.append(rec)
    return out[-limit:] if limit else out


def get(cfg: Config, n: int) -> Optional[Dict]:
    for rec in read(cfg, limit=None):
        if rec.get("n") == n:
            return rec
    return None


def principal_count_since(cfg: Config, since_n: int) -> int:
    return len([r for r in read(cfg, limit=None) if r.get("principal") and int(r.get("n", 0)) > since_n])
