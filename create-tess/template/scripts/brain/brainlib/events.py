"""One-use event ids and base positions for external-ledger rows (GPT-6 review round 3, N1).

Round 2 signed an outbox row over its body alone, so a repo writer could keep a
genuine `shown` row and put it back after a newer presentation reached the
ledger: it read, and drained, as the newest one. Now every row (shown, used,
line, session, turn) is stamped when it is made with

  eid    a random one-use event id,
  base   the ledger sequence it was made against, and bhead that ledger's chain
         head at that sequence,
  made   its creation time (ns), which orders rows made against the same state,

all inside the MAC (the stamp is part of the row body). A pending (outbox) row
is admitted to the ledger, or read at all, only when its eid is not already
there, its base/bhead name a state the ledger actually passed through, and the
ledger holds no row for the same item newer than that base. A pending row can
therefore never override a newer durable row for its item, and never lands twice.
"""
from __future__ import annotations

import secrets
import time
from typing import Dict, List, Optional, Tuple

# the item a row speaks for: a newer durable row for the same item wins over any pending row made before it
KEYS = {"shown": ("id",), "line": ("ref",), "session": ("path",), "used": ("ref", "id"), "turn": ("n", "mac"),
        "applied": ("claim",), "rec": ("id",), "automation": ("runtime", "sid"), "seal-init": ()}


def item_key(r: Dict) -> Optional[Tuple]:
    f = KEYS.get(str(r.get("t")))
    return None if f is None else (r.get("t"),) + tuple(str(r.get(x)) for x in f)


def made(r: Dict) -> int:
    m = r.get("made")
    return m if isinstance(m, int) and not isinstance(m, bool) else 0


def stamp(rows: List[Dict], seq: int, chain: str) -> List[Dict]:
    """Give each unstamped row its one-use id and the ledger position it is made against."""
    now = time.time_ns()
    return [r if r.get("eid") else dict(r, eid=secrets.token_hex(16), base=seq, bhead=chain, made=now + i)
            for i, r in enumerate(rows)]


def admit(durable: List[Dict], pending: List[Dict], chains: List[str]) -> Tuple[List[Dict], int]:
    """(the pending rows that may join the ledger, oldest first; how many were dropped as replayed or stale)."""
    seen = {r.get("eid") for r in durable if r.get("eid")}
    last: Dict[Tuple, int] = {}
    for r in durable:
        k = item_key(r)
        if k is not None:
            last[k] = max(last.get(k, 0), int(r.get("seq") or 0))
    ok: List[Dict] = []
    for r in pending:
        e, b, k = r.get("eid"), r.get("base"), item_key(r)
        if not (isinstance(e, str) and len(e) == 32 and e not in seen and k is not None
                and isinstance(b, int) and not isinstance(b, bool) and 0 <= b < len(chains)
                and chains[b] == r.get("bhead") and last.get(k, 0) <= b):
            continue
        seen.add(e)
        ok.append(r)
    ok.sort(key=made)  # stable: a reordered outbox cannot reorder what it lands as
    return ok, len(pending) - len(ok)


def newer(r: Dict, cur: Optional[Dict]) -> bool:
    """Whether `r` supersedes `cur` for the same item: later creation, then later ledger position."""
    return cur is None or (made(r), int(r.get("seq") or 0)) >= (made(cur), int(cur.get("seq") or 0))
