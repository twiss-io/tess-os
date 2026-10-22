"""Operator confirmation by id: the only path that approves, rejects or retracts.

Codex review finding 2 (2026-09-29): promote/confirm accepted any quote found
anywhere in the principal's history, so an old unrelated "yes" confirmed a new
material proposal. A confirmation now has to be:

1. the operator's AUTHENTICATED words (lookup.trusted: an attested journal line
   or a MAC-checked captured turn), never a repo-written file;
2. a narrow directive naming the exact id: the WHOLE message is "confirm D-..."
   / "yes, confirm D-..." / "accept D-..." (or "reject D-..." with an optional
   plain reason), optionally wrapped in one pair of quotes; never a question,
   quote, condition, hypothetical or negation (GPT-6 review round 2, R7). A
   multi-line message counts only when every non-empty line is itself such a
   directive, each for a different id (round 3): a condition on another line
   ("If legal approves:\nconfirm D-..."), a code fence, a blockquote or a list
   item never confirms;
3. about the content that was SHOWN: every listing (review, decide/remember
   outcomes) records a presentation in the external ledger (extstate.py) of (id, content hash, time, session),
   and the item must be unchanged since;
4. fresh: said after the latest presentation, in the session it was shown in
   when both are known, and each (line, id) pair is used once (no replays),
   recorded in the external ledger before the change is made (claims.py).

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



# Words that never make a useful short id on their own ("D-0929-we", "D-0929-the"): pronouns, articles,
# auxiliaries, prepositions, conjunctions and filler verbs. v1.0.0 item c.
STOPWORDS = frozenset("""
a an the this that these those it its i me my mine we us our ours you your yours he him his she her hers they
them their theirs one ones
am is are was were be been being do does did done have has had having will would shall should can could may
might must let lets use uses used using go going get gets got make makes made need needs want wants going
to of in on at by for from with without into onto over under about as than then so and or but nor not no yes
if because while also just only very really all any some each every more most other such own same too
""".split())


def _meaningful(words: List[str]) -> List[str]:
    return [w for w in words if w.lower() not in STOPWORDS and not w.isdigit() and len(w) > 1]


def _short_forms(item_id: str) -> List[str]:
    """Short spellings of a full id, most readable first; the full id itself last.

    D-20260929-1412-we-use-postgres-for-pricing -> D-0929-postgres, D-0929-pricing, D-0929-postgres-pricing,
    D-0929-we, D-0929-we-use, ..., D-0929-1412-we-use-postgres-for-pricing, the full id.
    Single meaningful words come first (stopwords and pronouns skipped), then growing meaningful
    phrases, then the literal slug prefixes, then the time-qualified slug. short_id() picks the first
    form no other live item could also mean, so uniqueness rules are unchanged."""
    m = re.fullmatch(r"([A-Za-z])-(\d{8})-(\d{4})-(.+)", item_id or "")
    if not m:
        return [item_id] if item_id else []
    pre, day, hhmm, rest = m.group(1).upper(), m.group(2)[4:], m.group(3), m.group(4).split("-")
    key = _meaningful(rest)
    tails = [[w] for w in key] + [key[:k] for k in range(2, len(key) + 1)] + \
        [rest[:k] for k in range(1, len(rest) + 1)]
    forms: List[str] = []
    for tail in tails:
        form = "%s-%s-%s" % (pre, day, "-".join(tail))
        if form not in forms:
            forms.append(form)
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


# GPT-6 review round 2, R7: "Should I confirm D-...?" and "Confirm D-... only after legal approval" were read as
# approvals because an approval verb and the id appeared in the same clause. A confirmation is now a narrow
# directive: the whole message is exactly `[yes,] confirm|accept|approve <id>` (optional trailing "please" and
# full stop). A rejection is `[no,] reject|retract|drop|withdraw <id>`, optionally followed by a plain reason
# after a comma, colon, dash or full stop. Anything else (a question, a quote, a condition, a hypothetical, a
# negation, two ids) is not a directive. Round 3: "If legal approves:\nconfirm D-..." passed because ONE line
# of it was a directive; now every non-empty line must be (messages()).
_ID = r"(?P<id>[A-Za-z]-[A-Za-z0-9][\w-]*)"
CONFIRM_LINE = re.compile(r"(?i)^(?:(?:yes|ok|okay)\s*,?\s+)?(?:confirm|accept|approve)\s+%s(?:\s*,?\s*please)?\s*\.?$"
                          % _ID)
DENY_LINE = re.compile(r"(?i)^(?:no\s*,?\s+)?(?:reject|retract|drop|withdraw)\s+%s"
                       r"(?:\s*(?:[,:.;]|\s[-\u2013\u2014])\s*(?P<why>.*))?\s*\.?$" % _ID)
HEDGE = re.compile(r"(?i)[?\"`\u201c\u201d]|\b(if|only|after|unless|when|once|pending|until|should|would|could|"
                   r"might|maybe|perhaps|wait|hold|later|yet|confirm|accept|approve|keep)\b")


# v1.0.0 item c (friendly confirms): users copy the phrase shown in 'Reply "confirm D-0929-pricing" ...'
# together with its quotes. A message that is EXACTLY one directive wrapped in one pair of matching quotes
# (straight or curly, optional full stop after the closing quote) is that directive. A quote inside a longer
# sentence ('He said "confirm D-..."'), nested or mismatched quotes, and multi-line messages are never unwrapped.
_WRAPPED = re.compile(r'^(?:"(?P<a>[^"\u201c\u201d]+)"|\u201c(?P<b>[^"\u201c\u201d]+)\u201d'
                      r"|'(?P<c>[^'\u2018\u2019\"\u201c\u201d]+)'|\u2018(?P<d>[^'\u2018\u2019\"\u201c\u201d]+)\u2019)"
                      r"\s*\.?$")


def unwrap(message: str) -> str:
    """The directive inside a whole message that is exactly one quoted phrase; else the message unchanged."""
    t = (message or "").strip()
    m = _WRAPPED.match(t)
    if not m:
        return message
    inner = next(g for g in m.groups() if g is not None).strip()
    return inner if (CONFIRM_LINE.match(inner) or DENY_LINE.match(inner)) else message


def directive(line: str) -> Tuple[str, str]:
    """('confirm' | 'deny', id as typed) when one line is a directive, else ('', '')."""
    t = (line or "").strip()
    m = CONFIRM_LINE.match(t)
    if m:
        return "confirm", m.group("id")
    m = DENY_LINE.match(t)
    if m and not HEDGE.search(m.group("why") or ""):
        return "deny", m.group("id")
    return "", ""


def directives(text: str) -> List[Tuple[str, str]]:
    """The directives of a whole message: [] unless ALL of it is directives. One line (trimmed, optionally
    wrapped in one pair of quotes) must be one directive; several lines must each be one, for distinct ids,
    with nothing else (no condition line, code fence, blockquote or list item)."""
    lines = [l.strip() for l in (text or "").strip().splitlines() if l.strip()]
    if len(lines) == 1:
        lines = [unwrap(lines[0]).strip()]
    hits = [directive(l) for l in lines]
    if not hits or not all(verb for verb, _ in hits) or len({i.lower() for _, i in hits}) != len(hits):
        return []
    return hits


def intent(text: str, item_id: str, action: str, alias: str = "") -> str:
    """'' when the operator's message is a directive to `action` `item_id` (or its shown short id `alias`)."""
    want = "confirm" if action in ("confirm", "promote") else "deny"
    names = {n.lower() for n in (item_id, alias) if n}
    if not any(_mentions(text, n) for n in names):
        return "the operator's words do not name %s" % item_id
    mine = [(verb, i) for verb, i in directives(text) if i.lower() in names]
    if len(mine) != 1 or mine[0][0] != want:
        return ('the operator\'s whole message about %s is not a plain "%s %s" (a question, condition, quote, '
                'code block, list or negation never counts)'
                % (item_id, "confirm" if want == "confirm" else "reject", alias or item_id))
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


def find(cfg: Config, item_id: str, quote: str, action: str, h: str,
         except_eid: str = "") -> Tuple[Optional[lookup.JLine], str]:
    """The operator's fresh, authenticated, id-bound words for `action` on `item_id` -> (line, '') or (None, why).
    `except_eid`: the queued claim being applied (claims.settle); its own consumption is not a replay."""
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
    if shown.get("eid") and provenance.used(cfg, "shown:%s" % shown["eid"], item_id, except_eid):
        return None, "%s was already answered since it was last shown (replay): show it again and ask" % item_id
    whys: List[Tuple[int, str]] = [(9, "no authenticated operator line contains the quote")]
    for line in lookup.search(cfg, quote):
        if not (line.principal and lookup.trusted(cfg, line)):
            continue
        at, sid = _when(cfg, line)
        if provenance.used(cfg, line.ref, item_id, except_eid):
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
