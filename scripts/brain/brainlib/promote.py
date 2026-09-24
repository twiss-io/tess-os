"""Promotion policy (spec section 10.6) and record lifecycle operations.

decision routine -> accepted only once V12 (settle.py) passes: the operator
confirmed it, or its session settled with no doubt; otherwise it waits in review
decision material -> proposed
preference/correction -> active, confirmed:false  fact (principal words) -> active
fact (assistant/tool/external) -> review           open loop -> proposed, always
skill -> brain/skills-drafts/ only                 quote only in turns -> pending-verification
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from . import lookup, records, verify
from .config import Config, iso
from .textutil import clip, contains, slugify


def default_target(kind: str, entity: str) -> str:
    base = "brain/%s" % entity.strip("/") if entity else "brain"
    if kind == "decision":
        return base + "/decisions"
    if kind in ("preference", "correction"):
        return "brain/profile"
    if kind == "fact":
        return base + "/facts"
    if kind == "open_loop":
        return base + "/loops"
    return "brain/skills-drafts"


def fill_source(cfg: Config, cand: Dict, line: lookup.JLine) -> None:
    cand["source_ref"] = line.ref
    if line.principal and not cand.get("speaker"):
        cand["speaker"] = line.speaker
    if not cand.get("source_at"):
        cand["source_at"] = lookup.line_time(cfg, line)
    cand["_source_principal"] = bool(line.principal)
    cand["_source_kind"] = line.kind


def principal_fact(cfg: Config, cand: Dict) -> bool:
    return bool(cand.get("_source_principal")) and cand.get("_source_kind") in ("msg", "turn")


def _link(cfg: Config, directory: Path, ref: str) -> str:
    if not ref or ref.startswith("turns:"):
        return "`%s` (local turn; re-verified at next sync)" % (ref or "unknown")
    path, _, label = ref.partition("#")
    target = cfg.root / path
    try:
        rel = Path(_relpath(target, directory))
    except ValueError:
        rel = Path(path)
    return "[%s#%s](%s#%s)" % (Path(path).name, label, rel.as_posix(), label)


def _relpath(target: Path, start: Path) -> str:
    import os
    return os.path.relpath(str(target), str(start))


def _session(cfg: Config, ref: str) -> str:
    if not ref or ref.startswith("turns:"):
        return ""
    meta = lookup.session_meta(cfg, ref.partition("#")[0])
    return "%s:%s" % (meta.get("runtime", ""), meta.get("session_id", "")) if meta else ""


def promote(cfg: Config, cand: Dict, pending: bool = False) -> records.Record:
    kind = cand["kind"]
    directory = cfg.root / (cand.get("target") or default_target(kind, cand.get("entity") or ""))
    now = iso(cfg.now())
    quote, statement = cand.get("quote") or "", cand.get("statement") or cand.get("quote") or ""
    at = cand.get("source_at") or now
    rid = records.new_id(cfg, kind, at, cand.get("title") or quote or statement)
    speaker = cand.get("speaker") or ""
    common = {"id": rid, "source_quote": quote, "source_speaker": speaker, "source_at": at,
              "source_ref": cand.get("source_ref") or "", "detected_by": cand.get("detected_by") or "operator",
              "verified_at": now}
    body = {"quote": quote, "statement": statement, "speaker": speaker,
            "source_link": _link(cfg, directory, cand.get("source_ref") or "")}
    status = _status(kind, cand, pending)
    if kind == "decision":
        meta = dict(common, type="decision", kind=cand.get("decision_kind") or "decision",
                    title=cand.get("title") or clip(quote, 80), status=status, tier=cand.get("tier") or "routine",
                    authority="approval" if cand.get("approves_quote") else "principal", decided_by=speaker,
                    decider_seat="", entity=cand.get("entity") or "", consulted=[], informed=[],
                    also_quoted=list(cand.get("also_quoted") or []), source_session=_session(cfg, common["source_ref"]),
                    approves_quote=cand.get("approves_quote") or "", delegation_ref="",
                    confirmed=bool(cand.get("confirmed_ref")), confirmed_ref=cand.get("confirmed_ref") or "",
                    verified=not pending, supersedes=cand.get("supersedes") or "", superseded_by="", tags=[])
        body.update(title=meta["title"], context="", consequences="Not recorded yet.")
    elif kind in ("preference", "correction"):
        meta = dict(common, type=kind, status=status, statement=statement, scope=cand.get("scope") or "global",
                    principal=speaker, corrects=cand.get("supersedes") or "", source_session=_session(
                        cfg, common["source_ref"]), verified=not pending, confirmed=False,
                    supersedes=cand.get("supersedes") or "", superseded_by="")
        sup = cand.get("supersedes")
        body["corrects_line"] = (" Supersedes %s." % sup) if sup else ""
    elif kind == "fact":
        kind_src = "principal" if cand.get("_source_principal", True) else "assistant"
        meta = dict(common, type="fact", entity=cand.get("entity") or "", status=status, statement=statement,
                    source_kind=kind_src, verified=not pending, confidence=cand.get("confidence") or "stated",
                    valid_from=at[:10], valid_until="", last_verified=now[:10],
                    verify_via=cand.get("verify_via") or "", confirmed=False)
        body.update(source_kind=kind_src, verify_via=meta["verify_via"] or "the source line")
    else:
        meta = dict(common, type="loop", entity=cand.get("entity") or "", statement=statement, status=status,
                    owner=cand.get("owner") or speaker, due=cand.get("due") or "", confirmed_by="",
                    confirmed_at="")
        body.update(owner=meta["owner"] or "unassigned", due=meta["due"] or "not set")
    rec = records.write(cfg, kind, directory, meta, body)
    if cand.get("supersedes"):
        _supersede(cfg, cand["supersedes"], rec.id)
    return rec


def profile_cap_error(cfg: Config, cand: Dict) -> str:
    """Would promoting this preference/correction push brain/profile.md over its cap?"""
    if cand.get("kind") not in ("preference", "correction"):
        return ""
    from . import caps, index
    recs = records.all_records(cfg)
    rid = records.new_id(cfg, cand["kind"], cand.get("source_at") or iso(cfg.now()), cand.get("quote") or "x",
                         {r.id for r in recs})
    fake = records.Record(cfg.brain / "profile" / ("%s.md" % rid),
                          {"id": rid, "status": "active", "statement": cand.get("statement") or cand.get("quote"),
                           "confirmed": False, "verified_at": iso(cfg.now())}, "")
    sup = cand.get("supersedes") or ""
    kept = [r for r in recs if r.id != sup]
    err = caps.profile(cfg, index.profile_text(cfg, kept + [fake]))
    return ("brain/profile.md would be over its cap (%s); not promoted. consolidate: brain-review --consolidate"
            % err) if err else ""


def _status(kind: str, cand: Dict, pending: bool) -> str:
    if pending:
        return "pending-verification"
    if kind == "decision":
        return "proposed" if (cand.get("tier") == "material") else "accepted"
    if kind == "open_loop":
        return "proposed"
    return "active"


def _supersede(cfg: Config, old_id: str, new_id: str) -> None:
    old = records.find(cfg, old_id)
    if old is not None and not old.meta.get("superseded_by"):
        records.update_fields(old, {"superseded_by": new_id, "status": "superseded"})


def skill_draft(cfg: Config, cand: Dict) -> str:
    d = cfg.brain / "skills-drafts"
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("%s.md" % slugify(cand.get("title") or cand.get("statement") or cand["id"]))
    if not p.exists():
        p.write_text("---\nname: %s\ndescription: %s\nsource_ref: %s\n---\n\n%s\n" % (
            p.stem, clip(cand.get("statement") or "", 200), cand.get("source_ref") or "",
            cand.get("statement") or ""), encoding="utf-8")
    return p.relative_to(cfg.root).as_posix()


def recheck_pending(cfg: Config) -> List[Dict]:
    """Records in pending-verification: journal hit -> promote; 2 failed syncs -> unverified."""
    out = []
    for rec in records.all_records(cfg):
        if rec.status != "pending-verification" or rec.meta.get("detected_by") == "onboarding":
            continue
        quote = str(rec.meta.get("source_quote") or "")
        hits = [h for h in lookup.search(cfg, quote) if h.kind != "turn" and h.principal] if quote else []
        if hits:
            line = hits[0]
            kind = rec.kind
            cand = {"kind": kind, "quote": quote, "statement": rec.meta.get("statement") or rec.meta.get("title"),
                    "title": rec.meta.get("title") or "", "source_ref": line.ref, "tier": rec.meta.get("tier"),
                    "target": records.register_rel(cfg, rec.path.parent), "speaker": line.speaker,
                    "detected_by": rec.meta.get("detected_by") or ""}
            res = verify.check(cfg, dict(cand, statement=cand["statement"] or quote))
            if kind == "decision" and res.status in ("pass", "noop"):  # V12 even when the quote matches itself
                res = verify.settle_check(cfg, cand, line)
            if res.status == "waiting":
                out.append({"record": rec.id, "status": rec.status, "reason": res.reasons[-1]})
                continue
            if res.status in ("pass", "noop", "review"):
                status = _status(kind, cand, False) if res.status != "review" else "proposed"
                upd = {"status": status, "source_ref": line.ref, "verified": True, "verified_at": iso(cfg.now()),
                       "source_speaker": line.speaker, "source_session": _session(cfg, line.ref)}
                if cand.get("confirmed_ref"):
                    upd.update(confirmed=True, confirmed_ref=cand["confirmed_ref"])
                if kind == "decision":
                    upd["decided_by"] = rec.meta.get("decided_by") or line.speaker
                records.update_fields(rec, upd)
                out.append({"record": rec.id, "status": status})
                continue
        tries = int(rec.meta.get("verify_attempts") or 0) + 1
        upd = {"verify_attempts": tries}
        if tries >= 2:
            upd["status"] = "unverified"
        records.update_fields(rec, upd)
        out.append({"record": rec.id, "status": upd.get("status", "pending-verification")})
    return out


def change_status(cfg: Config, rid: str, action: str, quote: str) -> Dict:
    """reject | retract | confirm, each backed by the principal's own verified words."""
    rec = records.find(cfg, rid)
    if rec is None:
        return {"ok": False, "error": "no record %s" % rid}
    hits = [h for h in lookup.search(cfg, quote) if h.principal] if len((quote or "").strip()) >= 2 else []
    if not hits:
        return {"ok": False, "error": "V1/V2: the quote is not a principal's words in the journal or current turn"}
    line = hits[0]
    now = iso(cfg.now())
    if action == "confirm":
        upd = {"confirmed": True}
        if rec.status == "proposed":
            upd["status"] = "accepted" if rec.kind == "decision" else "active"
        if rec.kind == "open_loop":
            upd.update(confirmed_by=line.speaker, confirmed_at=now)
        rec = records.update_fields(rec, upd)
        return {"ok": True, "record": rec.id, "status": rec.status, "confirmed": True}
    if action == "reject":
        rec = records.update_fields(rec, {"status": "rejected"})
        return {"ok": True, "record": rec.id, "status": "rejected"}
    cand = {"kind": "correction", "quote": quote, "statement": "Retracts %s: %s" % (rid, quote),
            "source_ref": line.ref, "speaker": line.speaker, "detected_by": "operator", "target": "brain/profile"}
    fill_source(cfg, cand, line)
    new = promote(cfg, cand, pending=line.kind == "turn")
    records.update_fields(records.find(cfg, rid), {"status": "retracted", "superseded_by": new.id})
    return {"ok": True, "record": rid, "status": "retracted", "by": new.id}


def quote_in(line_text: str, quote: str) -> bool:
    return contains(line_text, quote)
