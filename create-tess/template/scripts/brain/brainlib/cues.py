"""Deterministic cue pass (spec section 10.4): explicit first-person decisions,
preferences, corrections and open loops, on PRINCIPAL lines only.

The candidate statement is the principal's sentence verbatim and the quote
is a substring of it, so the risk is misclassification, never fabrication.
The verifier's V8 guard and `confirmed: false` review handle misclassification.
"""
from __future__ import annotations

import re
from typing import List, Optional

from .textutil import sentences

_I = re.I
PATTERNS = {
    "decision": [
        re.compile(r"^(ok(ay)?[,.]?\s+)?(let'?s|we'?ll|we will|go) (go with|use|pick|choose|ship|switch to)\b", _I),
        re.compile(r"^(decision|final|decided)\s*:", _I),
        re.compile(r"\b(i|we)(?:'ve| have)? decided (to|on)\b", _I),
        re.compile(r"^(yes|approved)[,.:]?\s+(go|ship|deploy|merge|publish)\b", _I),
    ],
    "correction": [
        re.compile(r"^(no|nope)[,.!]\s", _I),
        re.compile(r"\bthat'?s (wrong|not right|incorrect)\b", _I),
        re.compile(r"^actually,", _I),
        re.compile(r"\bi said\b", _I),
        re.compile(r"\bstop (doing|using)\b", _I),
    ],
    "preference": [
        re.compile(r"\bfrom now on\b", _I),
        re.compile(r"\b(always|never) (answer|reply|use|write|call|send|format)\b", _I),
        re.compile(r"\bi prefer\b", _I),
        re.compile(r"\bi (want|like) (you|it) to\b", _I),
    ],
    "open_loop": [
        re.compile(r"\bremind me\b", _I),
        re.compile(r"\bfollow up\b", _I),
        re.compile(r"\bwaiting (for|on)\b", _I),
        re.compile(r"\bby (mon|tues|wednes|thurs|fri|satur|sun)day\b", _I),
    ],
}
KIND_ORDER = ("decision", "correction", "preference", "open_loop")
_LABEL = re.compile(r"^(decision|final|decided)\s*:\s*", _I)
CURRENCY = re.compile(
    r"(?:(?:S|US|A|NZ|HK)?\$|€|£|¥|₹)\s?\d[\d,]*(?:\.\d+)?"
    r"|\b\d[\d,]*(?:\.\d+)?\s?(?:SGD|USD|EUR|GBP|AUD|MYR|JPY|dollars?|k\b)", _I)
HYPOTHETICAL = re.compile(
    r"\b(what if|if|would|could|might|maybe|perhaps|suppose|supposing|hypothetically|let'?s say|"
    r"in theory|thinking out loud|just brainstorming)\b", _I)
DECISION_VERB = re.compile(
    r"\b(go with|use|pick|choose|ship|switch|decided?|approve|adopt|drop|keep|move|deploy|merge|publish|"
    r"always|never|prefer|want|like|remind)\b", _I)


class Hit:
    __slots__ = ("kind", "sentence", "quote", "material", "pos")

    def __init__(self, kind: str, sentence: str, quote: str, material: bool, pos: int):
        self.kind, self.sentence, self.quote, self.material, self.pos = kind, sentence, quote, material, pos


def classify(sentence: str) -> Optional[Hit]:
    for kind in KIND_ORDER:
        for rx in PATTERNS[kind]:
            m = rx.search(sentence)
            if m:
                return Hit(kind, sentence, quote_of(sentence), bool(CURRENCY.search(sentence)), m.start())
    return None


def quote_of(sentence: str) -> str:
    """The quote: the sentence minus a leading 'Decision:' label and final full stop."""
    q = _LABEL.sub("", sentence.strip())
    return q.rstrip(" .!") if len(q.rstrip(" .!")) >= 12 else sentence.strip()


def scan_text(text: str) -> List[Hit]:
    """Cue hits for one principal message (never on questions)."""
    out = []
    for s in sentences(text or ""):
        if "<REDACTED:" in s:
            continue
        hit = classify(s)
        if hit is not None:
            out.append(hit)
    return out


def is_hypothetical(sentence: str, following: str = "") -> bool:
    """V8: a question, or a hypothetical marker before the decision verb."""
    s = sentence.strip()
    if s.endswith("?"):
        return True
    if re.search(r"\b(thinking out loud|just brainstorming|hypothetically)\b", following or "", _I):
        return True
    verb = DECISION_VERB.search(s)
    head = s[: verb.start()] if verb else s
    return bool(HYPOTHETICAL.search(head))


def mentions(text: str, name: str) -> bool:
    name = (name or "").strip()
    if len(name) < 3:
        return False
    return re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(name), text or "", _I) is not None


def has_currency(text: str) -> bool:
    return bool(CURRENCY.search(text or ""))
