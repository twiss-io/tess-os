"""V12 switches: a later choice in the same session (fix round 3).

The most common way people change their mind is to name the new option and
say nothing about the old one ("let's use Postgres" ... "actually, go with
SQLite"). The old option is then not taken back in words (V11 sees nothing),
yet recording it as ACCEPTED writes wrong knowledge into the brain.

So a decision is held for review (never accepted) when anything later in the
same session, from the same principal, could be a switch:

1. another decision ("let's go with SQLite", "Decision: ..."), whatever it is
   about: the verifier cannot tell topics apart, so it does not try;
2. a switch marker ("actually", "instead", "rather", "scrap that", "change of
   plan", "switch to", "on second thought", "go back to", ...) outside a
   question, from any principal ("maybe SQLite instead" counts);
3. a "No, ..." opener naming a new choice ("No, use SQLite.", "No, SQLite.");
4. a question offering an alternative ("what about SQLite instead?") followed
   by an approval ("Yes, do that.").

This deliberately prefers false negatives: two unrelated decisions in one
session leave the earlier one in review, and the operator confirms it.
A record already accepted goes back to proposed when the switch arrives in a
later sync (held()).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

from . import cues, lookup, records
from .config import Config
from .textutil import contains, sentences

SWITCH = re.compile(
    r"(?i)\b(actually|instead|rather|scrap|scratch|strike that|change of plans?|changed? (?:my|our) minds?|"
    r"on second thoughts?|second thoughts|switch(?:ing|ed)?|alternatively|go(?:ing)? back to|revert(?:ing)? to|"
    r"let'?s not|never ?mind|nvm|forget (?:that|it|about)|not that one|the other one|swap(?:ping)?)\b")
CHOICE = re.compile(
    r"(?i)\b(let'?s|we'?ll|we will|we'?re going|i'?ll|go with|going with|go for|use|using|pick|choose|"
    r"stick with|opt for|move to|do|take|keep)\b")
NO_OPENER = re.compile(r"(?i)^\s*(?:no|nope|nah)[,.!:;-]+\s*(.*)$")
ALT_QUESTION = re.compile(
    r"(?i)\b(instead|rather|what about|how about|what if|switch|alternative|or should we|better)\b")
AFFIRM = re.compile(
    r"(?i)^\s*(?:(?:yes|yeah|yep|ok(?:ay)?|sure|right|fine|alright|agreed|sounds good|great|cool)\b[\s,.!-]*)+$"
    r"|^\s*(?:(?:yes|yeah|yep|ok(?:ay)?|sure|fine|alright|agreed|sounds good)\b[\s,.!-]*)*"
    r"(?:let'?s |we'?ll |please )?(?:do|go with|go for|use|take|pick|switch to|make) (?:that|it|this|those|them)\b"
    r"|^\s*(?:yes|yeah|yep|ok(?:ay)?|sure)?[\s,.!-]*go ahead\b")
REASON = "V12: a later choice or switch in the same session (%r); the operator confirms which one stands"


def _question(s: str) -> bool:
    return s.rstrip().endswith("?")


def switch_in(target: str, later: List[str]) -> Optional[str]:
    """The first sentence in `later` that could replace the decision `target`, else None.

    `later` holds the same principal's sentences after the decision, in order."""
    alternative_asked = False
    for s in (x.strip() for x in later):
        if not s or contains(s, target):
            continue
        if _question(s):
            alternative_asked = alternative_asked or bool(ALT_QUESTION.search(s))
            continue
        if alternative_asked and AFFIRM.search(s):
            return s
        if SWITCH.search(s):  # "Maybe SQLite instead." floats an alternative too
            return s
        if cues.is_hypothetical(s):
            continue
        hit = cues.classify(s)
        if hit is not None and hit.kind == "decision":
            return s
        m = NO_OPENER.match(s)
        if m and (CHOICE.search(m.group(1)) or 0 < len(_words(m.group(1))) <= 3):
            return s
    return None


def switch_from_others(later: List[str]) -> Optional[str]:
    """Another principal's later sentence counts only with an explicit switch marker."""
    for s in (x.strip() for x in later):
        if s and not _question(s) and SWITCH.search(s):
            return s
    return None


def _words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9][\w'-]*", text or "")


def _sentence_index(text: str, quote: str) -> int:
    for i, s in enumerate(sentences(text)):
        if contains(s, quote) or contains(quote, s):
            return i
    return -1


def after(cfg: Config, line: lookup.JLine, quote: str):
    """(same speaker's later sentences, other principals' later sentences) in this session."""
    sents = sentences(line.text)
    i = _sentence_index(line.text, quote)
    mine: List[str] = sents[i + 1:] if i >= 0 else []
    others: List[str] = []
    if line.kind == "turn":
        return mine, others
    later = sorted((l for l in lookup.lines_for(cfg, line.path) if l.kind == "msg" and l.principal
                    and l.order > line.order), key=lambda l: l.order)
    for l in later:
        (mine if l.speaker == line.speaker else others).extend(sentences(l.text))
    return mine, others


def check(cfg: Config, line: lookup.JLine, quote: str) -> Optional[str]:
    """V12 reason for a decision candidate at `line`, or None."""
    mine, others = after(cfg, line, quote)
    s = switch_in(quote, mine) or switch_from_others(others)
    return REASON % s[:80] if s else None


def held(cfg: Config, paths: Set[str]) -> List[Dict]:
    """Re-check accepted, unconfirmed decisions of the sessions that got new principal lines."""
    out: List[Dict] = []
    for rec in records.all_records(cfg):
        ref = str(rec.meta.get("source_ref") or "")
        if (rec.kind != "decision" or rec.status != "accepted" or rec.meta.get("confirmed") is not False
                or ref.partition("#")[0] not in paths):
            continue
        line = lookup.resolve(cfg, ref)
        quote = str(rec.meta.get("source_quote") or "")
        why = check(cfg, line, quote) if line is not None and quote else None
        if why:
            records.update_fields(rec, {"status": "proposed"})
            out.append({"record": rec.id, "status": "proposed", "reason": why})
    return out


TOPIC_STOP = set("""
let lets let's we'll will go going with use using pick choose ship switch to decision decided final the a an for
of on in at by and or it its this that we i our ok okay yes actually instead rather go stick opt move do take keep
""".split())


def topic(text: str) -> Set[str]:
    return {w.lower().rstrip(".,:;!") for w in _words(text)
            if w.lower() not in TOPIC_STOP and len(w) > 2}
