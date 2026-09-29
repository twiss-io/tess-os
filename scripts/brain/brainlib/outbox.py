"""The outbox: signed rows a sandboxed shell queues in the repo until a hook moves them into the
external ledger (extstate.py). Rows are stamped (events.py) so a kept copy can never land twice or
override a newer durable row for its item."""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Dict, List, Tuple

from . import events
from .config import Config

OUTBOX = "outbox.jsonl"


def _body(row: Dict) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False)


def rows(cfg: Config, paths: List[Path]) -> List[Dict]:
    from .provenance import _eq
    out: List[Dict] = []
    for p in paths:
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for raw in lines:
            try:
                r = json.loads(raw)
            except ValueError:
                continue
            if isinstance(r, dict) and isinstance(r.get("row"), dict) and _eq(cfg, r.get("mac"), "outbox",
                                                                               _body(r["row"])):
                out.append(r["row"])
    return out


def paths(cfg: Config) -> List[Path]:
    return sorted(cfg.state.glob(OUTBOX + "*")) if cfg.state.is_dir() else []


def to_outbox(cfg: Config, new: List[Dict], seq: int, chain: str) -> bool:
    from .provenance import mac
    new = events.stamp(new, seq, chain)
    signed = [{"row": r, "mac": mac(cfg, "outbox", _body(r))} for r in new]
    if not signed or not signed[0]["mac"]:
        return False  # no key or project id: nothing can be attested (fail closed)
    cfg.ensure_state()
    with open(cfg.state / OUTBOX, "a", encoding="utf-8") as fh:
        for s in signed:
            fh.write(json.dumps(s, sort_keys=True) + "\n")
    return True


def take(cfg: Config) -> Tuple[List[Dict], List[Path]]:
    """Claim the pending outbox rows (renamed first, so a concurrent writer starts a fresh file)."""
    taken: List[Path] = []
    for p in paths(cfg):
        dst = p if p.name != OUTBOX else p.with_name("%s.draining-%d-%s" % (OUTBOX, os.getpid(), secrets.token_hex(4)))
        try:
            if dst != p:
                os.replace(str(p), str(dst))
            taken.append(dst)
        except OSError:
            continue
    return rows(cfg, taken), taken
