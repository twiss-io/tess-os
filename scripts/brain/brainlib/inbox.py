"""The inbox: typed candidates (brain/inbox/C-*.json, spec section 9.5).

Every candidate, whatever proposed it (cue pass, distill skill, decide,
onboarding, operator), goes through verify.check() and then the promotion
policy in promote.py. Rejected candidates are kept, with the verifier's
reasons, in brain/inbox/rejected/ so the operator can see what was refused.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from . import promote, receipts, verify
from .config import Config, iso, log_error, write_json

KINDS = ("decision", "preference", "correction", "fact", "open_loop", "skill")
DETECTORS = ("cue", "distill", "decide", "onboarding", "operator")


def inbox_dir(cfg: Config) -> Path:
    return cfg.brain / "inbox"


def new_candidate(cfg: Config, kind: str, statement: str, quote: str, **kw) -> Dict:
    if kind not in KINDS:
        raise ValueError("unknown kind %r (expected one of %s)" % (kind, ", ".join(KINDS)))
    detected = kw.get("detected_by") or "operator"
    if detected not in DETECTORS:
        raise ValueError("unknown detected_by %r" % detected)
    cand = {
        "id": _next_id(cfg), "kind": kind, "op": kw.get("op") or ("supersede" if kw.get("supersedes") else "add"),
        "target": kw.get("target") or promote.default_target(kind, kw.get("entity") or ""),
        "supersedes": kw.get("supersedes") or "", "statement": statement, "quote": quote,
        "speaker": kw.get("speaker") or "", "source_ref": kw.get("source_ref") or "",
        "source_at": kw.get("source_at") or "", "entity": kw.get("entity") or "",
        "tier": kw.get("tier") or "routine", "confidence": kw.get("confidence") or "stated",
        "detected_by": detected, "external_context": bool(kw.get("external_context")),
        "verification": {"status": "pending", "reasons": [], "checked_at": ""},
    }
    for extra in ("title", "approves_quote", "also_quoted", "decision_kind", "due", "owner", "verify_via"):
        if kw.get(extra):
            cand[extra] = kw[extra]
    return cand


def _next_id(cfg: Config) -> str:
    stamp = cfg.now().strftime("%Y%m%d-%H%M")
    taken = {p.stem for p in inbox_dir(cfg).rglob("C-*.json")} if inbox_dir(cfg).is_dir() else set()
    taken |= getattr(_next_id, "_issued", set())
    n = 1
    while "C-%s-%02d" % (stamp, n) in taken:
        n += 1
    cid = "C-%s-%02d" % (stamp, n)
    _next_id._issued = taken | {cid}  # type: ignore[attr-defined]
    return cid


def save(cfg: Config, cand: Dict, sub: str = "") -> Path:
    path = inbox_dir(cfg) / sub / ("%s.json" % cand["id"]) if sub else inbox_dir(cfg) / ("%s.json" % cand["id"])
    write_json(path, {k: v for k, v in cand.items() if not k.startswith("_")})
    return path


def _drop(cfg: Config, cand: Dict) -> None:
    p = inbox_dir(cfg) / ("%s.json" % cand["id"])
    if p.exists():
        os.remove(str(p))


def pending(cfg: Config) -> List[Dict]:
    d = inbox_dir(cfg)
    out = []
    for p in sorted(d.glob("C-*.json")) if d.is_dir() else []:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            log_error(cfg, "inbox: unreadable candidate %s" % p.name, exc)
    return out


def process(cfg: Config, cand: Dict, dry_run: bool = False) -> Dict:
    """Verify one candidate and apply the promotion policy. -> outcome dict."""
    res = verify.check(cfg, cand)
    cand["verification"] = {"status": res.status, "reasons": res.reasons, "checked_at": iso(cfg.now())}
    if res.line is not None:
        promote.fill_source(cfg, cand, res.line)
    outcome = {"candidate": cand["id"], "kind": cand["kind"], "status": res.status, "reasons": res.reasons,
               "record": "", "statement": cand.get("statement", "")}
    if dry_run:
        return outcome
    receipts.append(cfg, cand.get("speaker") or "unknown", "verify", cand["id"], res.status, res.reasons)
    if res.status == "fail":
        _drop(cfg, cand)
        save(cfg, cand, "rejected")
    elif res.status == "noop":
        _drop(cfg, cand)
    elif res.status == "review" or (cand["kind"] == "fact" and not promote.principal_fact(cfg, cand)) \
            or cand["kind"] == "skill":
        if cand["kind"] == "skill":
            outcome["record"] = promote.skill_draft(cfg, cand)
            _drop(cfg, cand)
        else:
            outcome["status"] = "review"
            cand["verification"]["status"] = "review"
            save(cfg, cand)
    else:
        rec = promote.promote(cfg, cand, pending=(res.status == "pending"))
        outcome["record"] = rec.rel(cfg)
        outcome["status"] = rec.status
        receipts.append(cfg, cand.get("speaker") or "unknown", "promote", cand["id"], rec.status, [rec.id])
        _drop(cfg, cand)
    return outcome


def process_all(cfg: Config, cands: Optional[List[Dict]] = None) -> List[Dict]:
    out = []
    for cand in (cands if cands is not None else pending(cfg)):
        if cand.get("verification", {}).get("status") == "review" and cands is None:
            continue  # waiting for the operator; re-checked only on request
        try:
            out.append(process(cfg, cand))
        except Exception as exc:  # noqa: BLE001 - one bad candidate never blocks the rest
            log_error(cfg, "inbox: processing %s failed" % cand.get("id"), exc)
    return out
