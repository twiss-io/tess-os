"""Operator confirmation by id: the only path that approves, rejects or retracts.

Codex review finding 2 (2026-09-29): promote/confirm accepted any quote found
anywhere in the principal's history, so an old unrelated "yes" confirmed a new
material proposal. A confirmation now has to be:

1. the operator's AUTHENTICATED words (lookup.trusted: an attested journal line
   or a MAC-checked captured turn), never a repo-written file;
2. naming the exact id, with the action's intent in the clause that names it
   ("confirm D-...", "approve C-..., reject D-...");
3. about the content that was SHOWN: every listing (review, decide/remember
   outcomes) records a MAC'd presentation of (id, content hash, time, session),
   and the item must be unchanged since;
4. fresh: said after the latest presentation, in the session it was shown in
   when both are known, and each (line, id) pair is used once (no replays).
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Dict, List, Optional, Tuple

from . import lookup, provenance, records, turns
from .config import Config, iso, parse_iso
from .textutil import BRAIN_ID

AFFIRM = re.compile(r"(?i)\b(confirm(?:ed|s)?|approve[ds]?|accept(?:ed|s)?|promote|yes|yep|yeah|ok(?:ay)?|"
                    r"go ahead|lgtm|agreed?|correct|keep|sounds good)\b")
DENY = re.compile(r"(?i)\b(reject(?:ed|s)?|retract(?:ed|s)?|cancel|drop|scrap|remove|forget|wrong|no|nope|not|never|"
                  r"don'?t|do not)\b|n't\b")
REJECT = re.compile(r"(?i)\b(reject(?:ed|s)?|retract(?:ed|s)?|forget|wrong|drop|remove|cancel|scrap|withdraw|undo|"
                    r"not (?:a|my) decision|never said)\b")
CLAUSE = re.compile(r"[.;,!?\n]+|\bbut\b", re.I)
CAND_FIELDS = ("kind", "statement", "quote", "title", "entity", "target", "tier", "supersedes", "approves_quote",
               "also_quoted", "decision_kind")
REC_FIELDS = ("type", "kind", "title", "statement", "source_quote", "tier", "entity", "supersedes",
              "approves_quote", "also_quoted", "scope")


def _digest(obj: Dict) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def candidate_hash(cand: Dict) -> str:
    return _digest({k: cand.get(k) for k in CAND_FIELDS})


def record_hash(rec: records.Record) -> str:
    return _digest({k: rec.meta.get(k) for k in REC_FIELDS})


def current_session(cfg: Config) -> str:
    """Session of the latest authenticated captured turn: the session the operator is typing in."""
    for rec in reversed(turns.read(cfg)):
        if rec.get("principal") and provenance.turn_ok(cfg, rec):
            return str(rec.get("session") or "")
    return ""


def present(cfg: Config, item_id: str, h: str) -> None:
    """Record that `item_id`, with content hash `h`, was shown to the operator now."""
    if item_id and h:
        provenance.shown(cfg, item_id, h, iso(cfg.now()), current_session(cfg))


def present_outcome(cfg: Config, out: Dict) -> None:
    """decide / remember / promote results the agent relays: proposed records and held candidates."""
    rid = str(out.get("record") or "").rsplit("/", 1)[-1][:-3] if out.get("record") else ""
    dup = [m.group(1) for r in out.get("reasons") or [] for m in [re.match(r"V5: duplicate of (\S+)", str(r))] if m]
    rid = rid or (dup[0] if dup else "")  # live run 2026-09-29: the cue pass had already proposed it
    rec = records.find(cfg, rid) if rid else None
    if rec is not None and rec.status in ("proposed",):
        present(cfg, rec.id, record_hash(rec))


def _mentions(text: str, item_id: str) -> bool:
    return bool(item_id) and bool(re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(item_id), text or "", re.I))


def intent(text: str, item_id: str, action: str) -> str:
    """'' when every clause naming `item_id` says `action`; else why not."""
    want = "confirm" if action in ("confirm", "promote") else "deny"
    ids = BRAIN_ID  # ids carry slug words ("do-not-use-redis")
    clauses = [ids.sub(" ", c) for c in CLAUSE.split(text or "") if c and _mentions(c, item_id)]
    if not clauses:
        return "the operator's words do not name %s" % item_id
    bare = ids.sub(" ", text or "")
    line_aff, line_deny, line_rej = bool(AFFIRM.search(bare)), bool(DENY.search(bare)), bool(REJECT.search(bare))
    for c in clauses:
        aff, deny, rej = bool(AFFIRM.search(c)), bool(DENY.search(c)), bool(REJECT.search(c))
        if not aff and not deny:  # "approve D-a, D-b": the verb is elsewhere in the line; only if unambiguous
            aff, deny, rej = line_aff, line_deny, line_rej
        if want == "confirm" and (deny or not aff):
            return "the operator's words about %s are not a plain approval" % item_id
        if want == "deny" and (aff or not rej):  # "don't confirm it yet" is not a rejection either
            return "the operator's words about %s do not reject or retract it" % item_id
    return ""


def _when(cfg: Config, line: lookup.JLine) -> Tuple[str, str]:
    """(time, session id) of an authenticated line."""
    if line.kind == "turn":
        rec = turns.get(cfg, int(line.index)) or {}
        return str(rec.get("at") or ""), str(rec.get("session") or "")
    sess = provenance.session_of(cfg, line.path) or {}
    return provenance.line_at(cfg, line), str(sess.get("sid") or "")


def _after(a: str, b: str) -> bool:
    try:
        return parse_iso(a) > parse_iso(b)
    except (ValueError, TypeError):
        return False


def find(cfg: Config, item_id: str, quote: str, action: str, h: str) -> Tuple[Optional[lookup.JLine], str]:
    """The operator's fresh, authenticated, id-bound words for `action` on `item_id` -> (line, '') or (None, why)."""
    if not _mentions(quote, item_id):
        return None, ("the quote must be the operator's words naming %s exactly (for example \"%s %s\")"
                      % (item_id, "confirm" if action in ("confirm", "promote") else action, item_id))
    shown = provenance.last_shown(cfg, item_id)
    if not shown:
        return None, "%s has not been shown to the operator: run review, show it with its id, and ask" % item_id
    if shown.get("h") != h:
        return None, "%s changed since it was shown to the operator: show it again and ask" % item_id
    whys: List[Tuple[int, str]] = [(9, "no authenticated operator line contains the quote")]
    for line in lookup.search(cfg, quote):
        if not (line.principal and lookup.trusted(cfg, line)):
            continue
        at, sid = _when(cfg, line)
        if provenance.used(cfg, line.ref, item_id):
            whys.append((0, "that operator line was already used for %s (replay)" % item_id))
        elif not _after(at, str(shown.get("at") or "")):
            whys.append((1, "the operator's words predate the latest time %s was shown (%s); show it and ask again"
                         % (item_id, shown.get("at"))))
        elif shown.get("sid") and sid and sid != shown.get("sid"):
            whys.append((2, "the operator's words are from another session than the one %s was shown in" % item_id))
        else:
            why = intent(line.text, item_id, action)
            if not why:
                return line, ""
            whys.append((3, why))
    return None, min(whys)[1]


def consume(cfg: Config, line: lookup.JLine, item_id: str) -> None:
    provenance.consume(cfg, line.ref, item_id)


def present_all(cfg: Config, items: List[Dict]) -> None:
    """`review`: every listed item is now shown (with its id) to the operator."""
    from . import inbox
    cands = {c["id"]: c for c in inbox.pending(cfg)}
    for it in items:
        iid = str(it.get("id") or "")
        if iid in cands:
            present(cfg, iid, candidate_hash(cands[iid]))
            continue
        rec = records.find(cfg, iid)
        if rec is not None:
            present(cfg, rec.id, record_hash(rec))
