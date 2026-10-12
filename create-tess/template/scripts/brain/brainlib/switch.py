"""V12 switch markers and topic words (fix round 3), kept for lint and settle.py.

Fix round 4 moved the decision rule itself to settle.py: a decision is a
candidate until its session settles with no doubt. The phrase lists below are
now only signals inside that rule, never the whole rule.

switch_in() still names the first later sentence that reads as a switch
("actually go with SQLite", "No, SQLite.", "What about SQLite instead?" then
"Yes, do that."); lint uses it to pair accepted decisions with later ones.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

from . import cues, lookup, records
from .config import Config
from .textutil import contains

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


def _words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9][\w'-]*", text or "")


def held(cfg: Config, paths: Set[str]) -> List[Dict]:
    """Re-check accepted, unconfirmed decisions of the sessions that got new lines (settle.py rules)."""
    from . import settle  # settle imports this module's markers
    out: List[Dict] = []
    for rec in records.all_records(cfg):
        ref = str(rec.meta.get("source_ref") or "")
        if (rec.kind != "decision" or rec.status != "accepted" or rec.meta.get("confirmed") is True
                or ref.partition("#")[0] not in paths):
            continue
        why = settle.any_doubt(cfg, lookup.resolve(cfg, ref), str(rec.meta.get("source_quote") or ""),
                                 settle.strict_for(str(rec.meta.get("detected_by") or "")))
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
