"""Verifier guards beyond V1-V9 (fix round 1; see docs/brain/LEARNING.md).

V10 statement fidelity: a record's title and statement may only say what the
principal's words say. Every content word of the title/statement must appear
in the quote or the cited line, and every negation in the quote must survive
into the statement. Anything else (a paraphrase, or an invented statement
paired with a real quote) goes to review and is never auto-accepted.

V11 context: a principal line is not always the principal deciding. Reported
speech ("Sam said: ..."), a pasted block (client notes, an email), a
statement taken back in the same or the next principal message ("scratch
that"), and a content-free approval ("Yes, go ahead.") go to review.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

from .textutil import normalize, sentences

_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
STOP = set("""
a an the to of for in on at by with from into onto as and or but so then than that this these those it its
we i you our us my me your he she they them their be is are was were been being will shall would should can
could do does did done have has had going go gonna lets let let's please just also all any some there here
which what who whom whose when where how about up out over via per we'll we're i'll i'm i've we've it's
decision decided decide decides final ok okay yes use using used uses
""".split())
NEGATION = {"not", "no", "never", "stop", "dont", "don't", "wont", "won't", "cannot", "cant", "can't",
            "without", "avoid", "instead", "except", "nor", "drop", "isn't", "aren't", "doesn't", "didn't"}
FILLER = STOP - {"go", "use", "using", "used", "uses", "let's", "lets", "let"} | {
    "sure", "fine", "sounds", "good", "great", "alright", "right", "ahead", "approved", "yep", "yeah", "cool",
    "thanks", "thank", "perfect", "do", "it", "that", "this"}
_REPORTED = re.compile(
    r"\b([A-Za-z][\w'-]*)\s+(?:said|says|wrote|writes|told|tells|asked|asks|mentioned|suggested|replied|"
    r"emailed|texted|messaged)\b")
_THIRD_DECIDED = re.compile(
    r"\b(they|he|she|client|clients|team|[A-Z][a-z]+)(?:'ve|'s| have| has| had)?\s+(?:decided|agreed|chose|picked)\b")
_QUOTED = re.compile(r"[\"“][^\"”]*\S\s+\S+\s+\S[^\"”]*[\"”]")  # a quoted utterance: 3+ words
_PASTE_INTRO = re.compile(
    r"(?i)\bhere(?:'s| is| are)\b.{0,60}\b(notes?|e-?mails?|transcript|minutes|messages?|thread|summary|chat|"
    r"memo|doc(?:ument)?)\b")
_TAKEBACK = re.compile(
    r"(?i)\b(just kidding|jk|scratch that|never ?mind|ignore that|disregard that|forget that|undo that|"
    r"not decided|haven't decided|have not decided|not sure yet|take that back)\b")


def _stem(w: str) -> str:
    w = w.replace("'", "") if w not in NEGATION else w
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def words(text: str) -> List[str]:
    return _WORD.findall(normalize(text).lower().replace("’", "'"))


def content_words(text: str) -> Set[str]:
    return {_stem(w) for w in words(text) if w not in STOP}


def fidelity(cand: Dict, source_text: str) -> Optional[str]:
    """V10 reason, or None when title and statement are the principal's words."""
    src = content_words(source_text)
    missing: List[str] = []
    for field in ("title", "statement"):
        missing += sorted(content_words(cand.get(field) or "") - src)
    if missing:
        return ("V10: not in the principal's words: %s (write the statement in their words, or the operator "
                "approves the rewrite in brain-review)" % ", ".join(sorted(set(missing))[:8]))
    stated = set(words(cand.get("statement") or "")) | set(words(cand.get("title") or ""))
    lost = sorted(n for n in NEGATION & set(words(cand.get("quote") or "")) if n not in stated)
    if lost and (cand.get("statement") or cand.get("title")):
        return "V10: the statement drops the quote's negation (%s)" % ", ".join(lost)
    return None


def _sentence_with(text: str, quote: str) -> int:
    sents = sentences(text)
    q = normalize(quote).lower()
    for i, s in enumerate(sents):
        ns = normalize(s).lower()
        if q and (q in ns or ns in q):
            return i
    return -1


def _reported(sentence: str) -> bool:
    for rx in (_REPORTED, _THIRD_DECIDED):
        for m in rx.finditer(sentence):
            if m.group(1).lower() not in ("i", "we"):
                return True
    return bool(_QUOTED.search(sentence))


def _pasted(text: str, quote: str) -> bool:
    lines = [l for l in (text or "").splitlines() if l.strip()]
    if len(lines) > 3 or _PASTE_INTRO.search(text or ""):
        return True
    return any(l.lstrip().startswith(">") and normalize(quote).lower() in normalize(l).lower() for l in lines)


def context(kind: str, quote: str, text: str, following: str, approval: bool = False) -> Optional[str]:
    """V11 reason, or None. `text` is the whole principal message; `following`
    is the next principal message in the same session ('' if none yet)."""
    sents = sentences(text)
    i = _sentence_with(text, quote)
    sentence = sents[i] if i >= 0 else quote
    if kind in ("decision", "preference") and _reported(sentence):
        return "V11: reported speech or a quotation, not the principal deciding"
    if _pasted(text, quote):
        return "V11: part of a pasted block (notes, email, transcript); the operator confirms it in review"
    rest = " ".join(sents[i + 1:]) if i >= 0 else ""
    nxt = " ".join(sentences(following)[:2])
    if _TAKEBACK.search(rest) or _TAKEBACK.search(nxt):
        return "V11: taken back in the same or the next message"
    if kind == "decision" and not approval and len([w for w in words(sentence) if w not in FILLER]) < 3:
        return "V11: content-free approval; the operator says what was approved in review"
    return None


def takes_back(text: str) -> bool:
    """Does this principal message open by taking the previous statement back?"""
    return bool(_TAKEBACK.search(" ".join(sentences(text)[:2])))
