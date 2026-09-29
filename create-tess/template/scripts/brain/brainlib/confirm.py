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

v1.0.0 (release integration, item b): every presentation also carries a SHORT
id ("D-0929-pricing") and a ready-to-say phrase ('Reply "confirm D-0929-pricing"
to accept'). The short id is the shortest form that names exactly one live
record or inbox candidate; it is stored, MAC'd, in the presentation row, and a
quote naming it counts only while it is still that item's unique short id.
Every other rule above (authenticated words, same content, freshness, no
replay) applies unchanged.
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


SHORT_ID = re.compile(r"(?<![\w-])[A-Z]-\d{4}-[\w-]+", re.I)


def _short_forms(item_id: str) -> List[str]:
    """Short spellings of a full id, shortest first; the full id itself last.
    D-20260929-1412-use-postgres -> D-0929-use, D-0929-use-postgres, D-0929-1412-use-postgres, ..."""
    m = re.fullmatch(r"([A-Za-z])-(\d{8})-(\d{4})-(.+)", item_id or "")
    if not m:
        return [item_id] if item_id else []
    pre, day, hhmm, rest = m.group(1).upper(), m.group(2)[4:], m.group(3), m.group(4).split("-")
    forms = ["%s-%s-%s" % (pre, day, "-".join(rest[:k])) for k in range(1, len(rest) + 1)]
    forms.append("%s-%s-%s-%s" % (pre, day, hhmm, "-".join(rest)))
    return forms + [item_id]


def _live_ids(cfg: Config) -> List[str]:
    from . import inbox
    return [c["id"] for c in inbox.pending(cfg)] + [r.id for r in records.all_records(cfg)]


def short_id(cfg: Config, item_id: str, live: Optional[List[str]] = None) -> str:
    """The shortest spelling of `item_id` that no other live record or candidate could also mean."""
    others = [o for o in (live if live is not None else _live_ids(cfg)) if o.lower() != item_id.lower()]
    taken = {f.lower() for o in others for f in _short_forms(o)}
    for form in _short_forms(item_id):
        if form.lower() not in taken:
            return form
    return item_id


def reply_phrase(short: str) -> str:
    return 'Reply "confirm %s" to accept, or "reject %s" to drop it' % (short, short)


def current_session(cfg: Config) -> str:
    """Session of the latest authenticated captured turn: the session the operator is typing in."""
    for rec in reversed(turns.read(cfg)):
        if rec.get("principal") and provenance.turn_ok(cfg, rec):
            return str(rec.get("session") or "")
    return ""


def present(cfg: Config, item_id: str, h: str, live: Optional[List[str]] = None) -> str:
    """Record that `item_id`, with content hash `h`, was shown to the operator now, with its short
    id. Returns the short id ('' when nothing was recorded)."""
    if not (item_id and h):
        return ""
    short = short_id(cfg, item_id, live)
    provenance.shown(cfg, item_id, h, iso(cfg.now()), current_session(cfg),
                     short if short != item_id else "")
    return short


def present_outcome(cfg: Config, out: Dict) -> None:
    """decide / remember / promote results the agent relays: proposed records and held candidates."""
    rid = str(out.get("record") or "").rsplit("/", 1)[-1][:-3] if out.get("record") else ""
    dup = [m.group(1) for r in out.get("reasons") or [] for m in [re.match(r"V5: duplicate of (\S+)", str(r))] if m]
    rid = rid or (dup[0] if dup else "")  # live run 2026-09-29: the cue pass had already proposed it
    rec = records.find(cfg, rid) if rid else None
    if rec is not None and rec.status in ("proposed",):
        short = present(cfg, rec.id, record_hash(rec))
        out["short_id"], out["reply"] = short, reply_phrase(short)


def _mentions(text: str, item_id: str) -> bool:
    return bool(item_id) and bool(re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(item_id), text or "", re.I))


def _strip_ids(text: str) -> str:
    # ids carry slug words ("do-not-use-redis"), full or short
    return SHORT_ID.sub(" ", BRAIN_ID.sub(" ", text or ""))


def intent(text: str, item_id: str, action: str, alias: str = "") -> str:
    """'' when every clause naming `item_id` (or its short id `alias`) says `action`; else why not."""
    want = "confirm" if action in ("confirm", "promote") else "deny"
    names = [n for n in (item_id, alias) if n]
    clauses = [_strip_ids(c) for c in CLAUSE.split(text or "") if c and any(_mentions(c, n) for n in names)]
    if not clauses:
        return "the operator's words do not name %s" % item_id
    bare = _strip_ids(text or "")
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
    shown = provenance.last_shown(cfg, item_id)
    alias = str((shown or {}).get("short") or "")
    if alias and short_id(cfg, item_id) != alias:
        alias = ""  # no longer this item's unique short id: only the full id counts
    if not (_mentions(quote, item_id) or (alias and _mentions(quote, alias))):
        say = alias or item_id
        return None, ("the quote must be the operator's words naming %s exactly (for example \"%s %s\")"
                      % (say, "confirm" if action in ("confirm", "promote") else action, say))
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
            if not (_mentions(line.text, item_id) or (alias and _mentions(line.text, alias))):
                whys.append((4, "that operator line does not name %s" % (alias or item_id)))
                continue
            why = intent(line.text, item_id, action, alias)
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
    live = _live_ids(cfg)
    for it in items:
        iid = str(it.get("id") or "")
        short = ""
        if iid in cands:
            short = present(cfg, iid, candidate_hash(cands[iid]), live)
        else:
            rec = records.find(cfg, iid)
            if rec is not None:
                short = present(cfg, rec.id, record_hash(rec), live)
        if short:
            it["short_id"], it["reply"] = short, reply_phrase(short)
