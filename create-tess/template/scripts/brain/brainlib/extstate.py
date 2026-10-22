"""Per-project brain state kept OUTSIDE the instance repo (GPT-6 review round 2, R5).

Round 1 kept attestations in .tess/state/brain/provenance.jsonl, inside the repo: a
repo writer could delete a "no, wait" line with its attestation, drop a `used` row
and restore an older `shown` row (replay), and rows copied from another project
verified under the machine-wide key. Now, in ~/.config/tess/brain/projects/<dir>/
(0700, files 0600, <dir> derived from the instance's real path):

  id            random project id; every MAC names it (provenance.mac).
  ledger.jsonl  append-only rows, each with a monotonic `seq`, the chain head of
                the rows before it (`prev`) and a MAC over (project id, seq,
                prev, row): attested journal lines (the per-journal-file
                manifest), sessions, captured turns, `shown` and `used` rows.
  head.json     MAC'd {seq, chain} of the last append. A ledger shorter than its
                head, or whose chain misses it, is a rollback: nothing in it is
                trusted (review only). Consumed confirmations stay consumed.
  roots.json    extra transcript roots the operator added at a terminal (roots.py).

First run / new machine / moved folder: no state yet, so journal lines already in
the repo are unverified (review only, never an error) until sync journals them
again from the runtime's own transcripts. The old repo-local provenance.jsonl is
ignored on purpose. A sandboxed shell (Codex: ~/.config is read-only to the agent)
writes MAC'd rows to .tess/state/brain/outbox.jsonl; the next hook or sync moves
them into the ledger. Each row carries a one-use event id and the ledger position
it was made against (events.py): a kept copy of a row put back later is dropped,
and a pending row never overrides a newer durable row for its item (round 3, N1).
The outbox window, stated plainly: until the next hook, a repo writer can DELETE
a pending row (a presentation or journal line then fails closed; nothing is
accepted from a pending row, since a confirmation is accepted only once its
consumption is durable here, claims.py). Code running as this user
outside any sandbox can read the key and write here, as before.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import events, outbox
from .config import Config, log_error

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows: locking degrades to a no-op
    fcntl = None

GENESIS = "0" * 64
LEDGER, HEAD = "ledger.jsonl", "head.json"
OUTBOX = outbox.OUTBOX
_CACHE: Dict[str, Tuple[Tuple, Optional[List[Dict]]]] = {}
_LEDGER: Dict[str, Tuple[Tuple, Tuple[Optional[List[Dict]], int, str, List[str]]]] = {}
_PIDS: Dict[str, str] = {}


def _real(p) -> str:
    return os.path.realpath(str(p))


def _body(row: Dict) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False)


def _chain(prev: str, mac: str) -> str:
    return hashlib.sha256((prev + mac).encode("ascii", "replace")).hexdigest()


def project_dir(cfg: Config, create: bool = True) -> Optional[Path]:
    """This instance's private state folder, or None (unsafe or unavailable: nothing verifies)."""
    from .provenance import _inside, _owned_private, key_dir
    base = key_dir() / "projects"
    d = base / hashlib.sha256(_real(cfg.root).encode("utf-8")).hexdigest()[:24]
    if _inside(str(d), str(cfg.root)):
        return None
    if create and not d.is_dir():
        try:
            for p in (key_dir(), base, d):
                p.mkdir(exist_ok=True, mode=0o700)
        except OSError:
            pass  # a sandboxed shell: read-only here; the next hook creates it
    if not d.is_dir():
        return None
    why = _owned_private(d, 0o077)
    if why:
        log_error(cfg, "brain state: unsafe folder: " + why)
        return None
    return d


def project_id(cfg: Config) -> str:
    """The stable random id of this instance's external state ('' when it cannot be read or made)."""
    d = project_dir(cfg)
    if d is None:
        return ""
    p = d / "id"
    if str(p) in _PIDS:
        return _PIDS[str(p)]
    try:
        if not p.exists():
            fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(secrets.token_hex(16))
        pid = p.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return ""
    if len(pid) != 32 or any(c not in "0123456789abcdef" for c in pid):
        log_error(cfg, "brain state: %s is not a project id; nothing verifies" % p)
        return ""
    _PIDS[str(p)] = pid
    return pid


# -- reading ------------------------------------------------------------------------------------------

def _read_ledger(cfg: Config, d: Path) -> Tuple[Optional[List[Dict]], int, str, List[str]]:
    """(rows, last seq, chain head, chain head after each seq); rows is None when rolled back or corrupted."""
    from .provenance import _eq
    rows: List[Dict] = []
    seq, chain, chains = 0, GENESIS, [GENESIS]
    lp, hp = d / LEDGER, d / HEAD
    if lp.is_file():
        with open(lp, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                try:
                    r = json.loads(raw)
                except ValueError:
                    break  # a torn final write: everything before it stands
                if not (isinstance(r, dict) and r.get("seq") == seq + 1 and r.get("prev") == chain
                        and isinstance(r.get("row"), dict)
                        and _eq(cfg, r.get("mac"), "ledger", str(seq + 1), chain, _body(r["row"]))):
                    break
                seq, chain = seq + 1, _chain(chain, r["mac"])
                chains.append(chain)
                rows.append(dict(r["row"], seq=seq))
    try:
        head = json.loads(hp.read_text(encoding="utf-8")) if hp.is_file() else None
    except (OSError, ValueError):
        head = {}
    if head is None:
        return rows, seq, chain, chains  # never written, or the very first append died before its head
    hs = head.get("seq") if isinstance(head, dict) else None
    if not (isinstance(hs, int) and _eq(cfg, head.get("mac"), "head", str(hs), str(head.get("chain")))):
        log_error(cfg, "brain state: head.json does not verify; evidence is unverified (review only)")
        return None, seq, chain, chains
    if hs > seq or chains[hs] != head.get("chain"):
        log_error(cfg, "brain state: the ledger was rolled back (%d of %d rows); evidence is unverified" % (seq, hs))
        return None, seq, chain, chains
    return rows, seq, chain, chains


def _ledger(cfg: Config, d: Path) -> Tuple[Optional[List[Dict]], int, str, List[str]]:
    """_read_ledger, re-verified only when the ledger or its head changed on disk."""
    stamp = _stamp([d / LEDGER, d / HEAD])
    hit = _LEDGER.get(str(d))
    if hit and hit[0] == stamp:
        return hit[1]
    got = _read_ledger(cfg, d)
    _LEDGER[str(d)] = (stamp, got)
    return got


def _stamp(paths: List[Path]) -> Tuple:
    out = []
    for p in paths:
        try:
            st = p.stat()
            out.append((str(p), st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((str(p), 0, -1))
    return tuple(out)


def rows(cfg: Config) -> Optional[List[Dict]]:
    """Every authenticated row, oldest first (ledger, then pending outbox rows); None = rolled back."""
    d = project_dir(cfg)
    if d is None or not project_id(cfg):
        return []
    box = outbox.paths(cfg)
    stamp = _stamp([d / LEDGER, d / HEAD, d / "id"] + box)
    hit = _CACHE.get(str(d))
    if hit and hit[0] == stamp:
        return hit[1]
    got, seq, _, chains = _ledger(cfg, d)
    if got is not None:  # a kept copy of an old row, or one older than the ledger's state for its item, never reads
        ok, _n = events.admit(got, outbox.rows(cfg, box), chains)
        got = got + [dict(r, seq=seq + i + 1, pending=True) for i, r in enumerate(ok)]
    _CACHE[str(d)] = (stamp, got)
    return got


# -- writing ------------------------------------------------------------------------------------------

def _write_ledger(cfg: Config, d: Path, new: List[Dict]) -> None:
    from .provenance import mac
    got, seq, chain, chains = _ledger(cfg, d)
    if got is None:
        raise RuntimeError("the external ledger was rolled back; refusing to extend it")
    lines, added, chains = [], [], list(chains)
    for r in new:
        seq += 1
        m = mac(cfg, "ledger", str(seq), chain, _body(r))
        if not m:
            raise RuntimeError("no key or project id")
        lines.append(json.dumps({"seq": seq, "prev": chain, "row": r, "mac": m}, sort_keys=True) + "\n")
        chain = _chain(chain, m)
        chains.append(chain)
        added.append(dict(r, seq=seq))
    fd = os.open(str(d / LEDGER), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fh.write("".join(lines))
        fh.flush()
        os.fsync(fh.fileno())
    try:  # the rows are durable now; a head that lags them is accepted (it only guards against truncation)
        tmp = d / (HEAD + ".tmp")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"seq": seq, "chain": chain, "mac": mac(cfg, "head", str(seq), chain)}, fh)
        os.replace(str(tmp), str(d / HEAD))
    except OSError as exc:
        log_error(cfg, "brain state: could not update %s" % (d / HEAD), exc)
    _LEDGER[str(d)] = (_stamp([d / LEDGER, d / HEAD]), (list(got) + added, seq, chain, chains))  # we hold the lock


def _fallback(cfg: Config, new: List[Dict], d: Optional[Path], durable: bool) -> bool:
    """No ledger write here: queue `new` in the outbox against the ledger state this shell can read (never a
    row the caller needs durable now). Always False: nothing reached the ledger."""
    if new and not durable:
        seq, chain = _ledger(cfg, d)[1:3] if d is not None else (0, GENESIS)
        outbox.to_outbox(cfg, new, seq, chain)
    return False


def append(cfg: Config, new: List[Dict], durable: bool = False) -> bool:
    """Append rows to the ledger (draining admissible outbox rows first). True when `new` is durable in the
    ledger. A sandboxed shell cannot write here: `new` then waits in the outbox, unless `durable` (the caller
    needs the row in the ledger now, e.g. a consumed confirmation) in which case nothing is written."""
    d = project_dir(cfg)
    if d is None or not project_id(cfg):
        return _fallback(cfg, new, d, durable)
    try:
        lock = os.open(str(d / "lock"), os.O_WRONLY | os.O_CREAT, 0o600)
    except OSError:  # read-only here (sandbox)
        return _fallback(cfg, new, d, durable)
    try:
        if fcntl is not None:
            fcntl.flock(lock, fcntl.LOCK_EX)
        return _append_locked(cfg, d, new, durable)
    finally:
        os.close(lock)


def _append_locked(cfg: Config, d: Path, new: List[Dict], durable: bool) -> bool:
    pending, taken = outbox.take(cfg)
    got, seq, chain, chains = _ledger(cfg, d)
    ok, dropped = events.admit(got or [], pending, chains) if got is not None else (pending, 0)
    if dropped:
        log_error(cfg, "brain state: dropped %d outbox row(s): replayed, or older than the ledger" % dropped)
    # a record seal made in the sandbox stays the sandbox's once durable (records.seal_row_trusted)
    ok = [dict(r, origin=outbox.ORIGIN) if r.get("t") == "rec" else r for r in ok]
    new = events.stamp(list(new), seq, chain)
    done = False
    try:
        if ok or new:
            _write_ledger(cfg, d, ok + new)
        done = True
    except (OSError, RuntimeError) as exc:
        log_error(cfg, "brain state: could not append to %s" % d, exc)
        outbox.to_outbox(cfg, ok + ([] if durable else new), seq, chain)
    for p in taken:
        try:
            p.unlink()
        except OSError:
            pass
    return done and bool(new)


def writable(cfg: Config) -> bool:
    """Whether this process can extend the external ledger (False in a sandboxed shell)."""
    d = project_dir(cfg)
    if d is None or not project_id(cfg):
        return False
    try:
        os.close(os.open(str(d / "lock"), os.O_WRONLY | os.O_CREAT, 0o600))
        return True
    except OSError:
        return False


def drain(cfg: Config) -> None:
    """Move outbox rows a sandboxed shell left behind into the ledger (hooks and sync call this)."""
    if outbox.paths(cfg):
        append(cfg, [])
