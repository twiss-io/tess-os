"""Hash-chained receipts for verify/promote: one JSONL file per principal per
month under .tess/state/brain/receipts/ (local state, never committed).

Each line carries sha256(prev_sha256 + canonical JSON of the entry), so an
edited or deleted line breaks the chain (`verify_chain`). Failures to write
a receipt are logged and never block learning.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List

from .config import Config, iso, log_error

GENESIS = "0" * 64


def _path(cfg: Config, principal: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in principal or "unknown")
    return cfg.state / "receipts" / safe / ("%s.jsonl" % cfg.now().strftime("%Y-%m"))


def _digest(prev: str, entry: Dict) -> str:
    body = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256((prev + body).encode("utf-8")).hexdigest()


def _last_sha(path: Path) -> str:
    if not path.is_file():
        return GENESIS
    last = GENESIS
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                last = json.loads(line).get("sha256") or last
            except ValueError:
                continue
    return last


def append(cfg: Config, principal: str, action: str, subject: str, status: str, detail: List[str]) -> None:
    try:
        cfg.ensure_state()
        path = _path(cfg, principal)
        path.parent.mkdir(parents=True, exist_ok=True)
        prev = _last_sha(path)
        entry = {"at": iso(cfg.now()), "principal": principal, "action": action, "subject": subject,
                 "status": status, "detail": list(detail)[:10], "prev_sha256": prev}
        entry["sha256"] = _digest(prev, {k: v for k, v in entry.items() if k != "sha256"})
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
    except OSError as exc:
        log_error(cfg, "receipts: append failed", exc)


def verify_chain(path: Path) -> List[str]:
    """-> list of problems (empty == intact)."""
    problems, prev = [], GENESIS
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            try:
                entry = json.loads(line)
            except ValueError:
                problems.append("line %d: not JSON" % n)
                continue
            if entry.get("prev_sha256") != prev:
                problems.append("line %d: chain break" % n)
            want = _digest(entry.get("prev_sha256", ""), {k: v for k, v in entry.items() if k != "sha256"})
            if entry.get("sha256") != want:
                problems.append("line %d: digest mismatch" % n)
            prev = entry.get("sha256") or prev
    return problems
