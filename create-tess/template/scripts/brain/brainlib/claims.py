"""Operator-confirmed transitions (promote, confirm, reject, retract): consumption first, then the change.

GPT-6 review round 3 (N1): a confirmation used to be applied first and its `used`
row written after, and in a sandboxed shell that row only reached the repo-side
outbox, where a repo writer could delete it and replay the operator's words. Now
the (line, item) consumption is written to the EXTERNAL ledger before anything
is changed or reported accepted. A sandboxed shell (Codex: ~/.config is
read-only to the agent) cannot write there, so it only QUEUES the confirmation
(a signed `used` row carrying the claim) and reports it pending; the item stays
as it was. The next sync outside the sandbox (the hooks start one) drains the
claim into the ledger, which consumes the line durably, re-checks every rule in
confirm.find against the current item, applies the change, and records an
`applied` row. A deleted claim confirms nothing; a replayed one is dropped
(events.py) or already applied.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple

from . import confirm, extstate, inbox, index, promote, provenance, records, verify
from .config import Config, iso, log_error

Out = Tuple[int, object]

PENDING = ("The operator's words confirm %s, but this shell cannot write the brain's private state (a sandbox), "
           "so the confirmation is queued: it is recorded and applied by the next hook, when this turn ends. "
           "%s stays %s until then. Tell the operator exactly that; do not say it was accepted.")


def run_candidate(cfg: Config, cand: Dict, dry: bool) -> Out:
    outcome = inbox.process(cfg, cand, dry_run=dry)
    rc = 0
    if not dry:
        rc, msgs = index.regenerate(cfg)
        if msgs:
            outcome["index"] = msgs
    if outcome["status"] == inbox.OVER_CAP:
        return 3, outcome
    return (1 if outcome["status"] == "fail" else rc), outcome


def _consume(cfg: Config, line, item_id: str, action: str, quote: str, h: str, state: str) -> Optional[Out]:
    """None once (line, item) is durably consumed in the external ledger; else the reply to return now."""
    # one answer per presentation: the same message can be both a journal line and a captured turn (two refs)
    row = {"t": "used", "ref": line.ref, "id": item_id, "shown": (provenance.last_shown(cfg, item_id) or {}).get("eid")}
    if extstate.append(cfg, [row], durable=True):
        return None
    if extstate.writable(cfg):  # the ledger itself refused (rolled back): nothing may be accepted
        return 1, {"ok": False, "error": "could not record the confirmation in the brain's private state; "
                                         "nothing changed (see .tess/state/brain/errors.log)"}
    if not provenance.mac(cfg, "claim"):  # no key or project state yet: nothing could even be queued
        return 1, {"ok": False, "error": "the brain's private state is not set up yet (a hook outside the sandbox "
                                         "makes it); nothing changed: ask the operator again next turn"}
    extstate.append(cfg, [dict(row, claim={"action": action, "quote": quote, "h": h})])
    return 0, {"ok": True, "id": item_id, "status": "pending", "pending": True,
               "note": PENDING % (item_id, item_id, state)}


def _find(cfg: Config, item_id: str, quote: str, action: str, h: str, claim: Optional[Dict]):
    if claim is None:
        return confirm.find(cfg, item_id, quote, action, h)
    if (claim.get("claim") or {}).get("h") != h:
        return None, "%s changed after the confirmation was queued" % item_id
    line, why = confirm.find(cfg, item_id, quote, action, h, except_eid=str(claim.get("eid") or ""))
    if line is not None and line.ref != claim.get("ref"):
        return None, "the queued confirmation names another operator line"
    return line, why


def apply_promote(cfg: Config, a, claim: Optional[Dict] = None) -> Out:
    cands = {c["id"]: c for c in inbox.pending(cfg)}
    if a.id not in cands:
        return 1, {"error": "no inbox candidate %s" % a.id}
    h = confirm.candidate_hash(cands[a.id])
    line, err = _find(cfg, a.id, a.quote, "promote", h, claim)
    if line is None:
        return 1, {"error": "V1/V2: %s" % err}
    held = None if claim else _consume(cfg, line, a.id, "promote", a.quote, h, "an inbox candidate")
    if held:
        return held
    cand = dict(cands[a.id], confirmed_ref=line.ref)
    cand[verify.APPROVED] = True
    cand["verification"] = {"status": "pending", "reasons": [], "checked_at": ""}
    code, out = run_candidate(cfg, cand, False)
    rid = str(out.get("record", "")).rsplit("/", 1)[-1][:-3] if out.get("record") else ""
    if rid and rid.startswith(("D-", "P-", "C-", "F-", "L-")):
        res = promote.change_status(cfg, rid, "confirm", a.quote, line)  # the operator's approval confirms it
        out["status"] = res.get("status", out.get("status"))
        out["confirmed"] = bool(res.get("confirmed"))
        index.regenerate(cfg)
    return code, out


def apply_status(cfg: Config, a, claim: Optional[Dict] = None) -> Out:
    cands = {c["id"]: c for c in inbox.pending(cfg)}
    if a.id in cands:  # an inbox candidate (C-YYYYMMDD-HHMM-NN), not a C- correction record
        if a.action != "reject":
            return 1, {"error": "%s is an inbox candidate: reject it, or promote it with the operator's words" % a.id}
        c = cands[a.id]
        h = confirm.candidate_hash(c)
        line, err = _find(cfg, a.id, a.quote, "reject", h, claim)
        if line is None:
            return 1, {"error": "V1/V2: %s" % err}
        held = None if claim else _consume(cfg, line, a.id, "reject", a.quote, h, "in the inbox")
        if held:
            return held
        c["verification"] = {"status": "fail", "reasons": ["rejected by operator: %s" % a.quote],
                             "checked_at": iso(cfg.now())}
        inbox.save(cfg, c, "rejected")
        (inbox.inbox_dir(cfg) / ("%s.json" % a.id)).unlink()
        index.regenerate(cfg)
        return 0, {"ok": True, "candidate": a.id, "status": "rejected"}
    rec = records.find(cfg, a.id)
    if rec is None:
        return 1, {"ok": False, "error": "no record %s" % a.id}
    h = confirm.record_hash(rec)
    line, err = _find(cfg, rec.id, a.quote, a.action, h, claim)
    if line is None:
        return 1, {"ok": False, "error": "V1/V2: %s" % err}
    held = None if claim else _consume(cfg, line, rec.id, a.action, a.quote, h, rec.status)
    if held:
        return held
    res = promote.change_status(cfg, rec.id, a.action, a.quote, line)
    index.regenerate(cfg)
    return (0 if res.get("ok") else 1), res


def settle(cfg: Config) -> List[Dict]:
    """Apply confirmations a sandboxed shell queued, once their consumption is durable in the external ledger
    (sync calls this, outside the sandbox). Each claim is applied at most once; a stale one is closed unapplied."""
    todo = [r for r in provenance._load(cfg)["claims"] if str(r.get("eid")) not in provenance._load(cfg)["applied"]]
    if not todo or not extstate.writable(cfg):
        return []
    done: List[Dict] = []
    for row in todo:
        c = row["claim"]
        a = SimpleNamespace(id=str(row.get("id") or ""), quote=str(c.get("quote") or ""), action=str(c.get("action")))
        try:
            fn = apply_promote if a.action == "promote" else apply_status
            code, res = fn(cfg, a, claim=row)
        except Exception as exc:  # noqa: BLE001 - one bad claim never blocks sync
            log_error(cfg, "brain: applying the queued confirmation of %s failed" % a.id, exc)
            code, res = 1, {"error": str(exc)}
        why = "" if code == 0 else str((res or {}).get("error") or "not applied")
        extstate.append(cfg, [{"t": "applied", "claim": row["eid"], "id": a.id, "ok": code == 0, "why": why[:300]}],
                        durable=True)
        done.append({"id": a.id, "action": a.action, "ok": code == 0, "why": why})
    return done
