"""V12 settle rule: a distilled decision is a CANDIDATE, never accepted from wording alone.

Fix round 4. Listing switch phrases could not close "the abandoned option is
recorded as ACCEPTED": "No wait, SQLite.", "Make it SQLite.", or the assistant
asking "Want me to switch to SQLite?" and the operator saying "Yes please."
all slipped through. So the rule is inverted. Everything after the decision
in its session (the rest of its message, every later principal turn, every
assistant reply) is read, and the decision is auto-accepted only when NONE of
it could be about the decision:

* a later principal sentence raises doubt unless it is a plain acknowledgement
  ("Thanks.", "Great."), a restatement using only the decision's own words, or
  a sentence with no choice signal at all: no negation or hesitation ("no",
  "wait", "hmm"), no switch or take-back marker, no choice verb ("use", "make
  it", "go with"), no comparison ("overkill", "simpler"), no alternative
  question, no named option the decision did not name (SQLite, MongoDB, v2),
  no subject word of the decision, not a fragment of three words or fewer,
  and not itself a decision or correction;
* an assistant reply that offers an alternative (a question or suggestion
  that switches, compares, names a choice verb, a new option or the
  decision's subject) makes the operator's next turn doubt, whatever it says:
  an alternative the operator agrees to supersedes the earlier choice;
* an assistant question that restates exactly the decision, answered with a
  plain "yes", is an explicit confirmation (accepted, confirmed: true).

brain-decide (the operator asked to record this exact decision) is read with
the same rule minus the signals that are not tied to the decision, so
unrelated later work does not hold it, and it does not wait to settle.

With no doubt, auto-accept still waits until the session has been quiet for
`learn.settle_minutes` (default 30), so a switch in the very next turn is seen
first. `learn.auto_accept: "off"` sends every unconfirmed decision to review.
Doubt never drops anything: the candidate waits in brain-review.
"""
from __future__ import annotations

import re
from typing import List, Optional, Set, Tuple

from . import cues, lookup, takeback
from .config import Config, parse_iso
from .switch import ALT_QUESTION, CHOICE, SWITCH, TOPIC_STOP
from .textutil import clip, sentences

ACK = set("""
thanks thank you ty thx cheers ok okay k kk great cool nice perfect good awesome noted got it sounds lovely
brilliant excellent fine alright all right sure yes yep yeah yup wonderful appreciated much very so that's
thats that is looks lgtm ack roger please go ahead do it
""".split())
AFFIRM = set("""
yes yeah yep yup sure ok okay correct confirmed confirm right exactly please do it go ahead that's thats that is
absolutely definitely indeed sounds good great perfect lgtm
""".split())
HESITATE = re.compile(
    r"(?i)\b(no|not|nope|nah|never|don'?t|do not|wait|hmm+|ugh|hold on|hang on|erm|uh|um|but|though|however|"
    r"unless|except)\b|n't\b")
EVALUATE = re.compile(
    r"(?i)\b(overkill|over-?engineered|too (?:heavy|slow|big|much|many|expensive|complex|complicated|early|late)|"
    r"heavy|heavier|simpler|simple|better|worse|easier|lighter|cheaper|faster|slower|smaller|bigger|prefer|"
    r"preferable|rather|enough|should|need|needs|want|wanna|make it|make that|go for|how about|what about|what if|"
    r"maybe|perhaps|suppose|could|might|would)\b")
OFFER = re.compile(
    r"(?i)\?|\b(want me to|shall i|should i|should we|would you like|do you want|i can|i could|we could|you could|"
    r"let me know|recommend|suggest|consider|instead|rather|alternative|prefer|would be|might be|could be|"
    r"simpler|better|easier|cheaper|faster|lighter)\b")
OPTION = re.compile(
    r"\b(?:[A-Za-z]*[a-z][A-Z]\w*|[A-Z]{2,}\w*|\w*\d\w*|\w+[.:/]\w[\w.:/-]*)\b")
CAPWORD = re.compile(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-z]+\b")
COMMON_CAPS = set("""
I I'm I'll I've I'd Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May
June July August September October November December Mon Tue Wed Thu Fri Sat Sun OK Ok
""".split())
COMMON_LOWER = {w.lower() for w in COMMON_CAPS}
HESITATION_WORDS = set("no nope nah wait hmm hmmm ugh actually oh hang hold on cancel forget scrap ignore disregard".split())
FILLER = set("is are was be been it's its please also then now here there can you your".split())
COMPARE = re.compile(
    r"(?i)\b(overkill|simpler|better|worse|easier|lighter|heavier|cheaper|faster|slower|instead|rather|prefer|"
    r"alternative|swap|replace|migrate|move (?:it |the \w+ )?to)\b")
MAKE_IT = re.compile(r"(?i)\bmake (?:it|that|this)\b")
OFFER_CHOICE = re.compile(r"(?i)\b(go with|going with|go for|use|using|pick|choose|stick with|opt for|switch)\b")
RESTATE_VOCAB = set("""
want me to shall should would you like do confirm confirming lock set up setup go ahead proceed record note so
we're were going with use using keep stick just check is it that's right correct then the a an for of on in ok
okay yes let lets let's we'll will i i'll our we it this that
""".split())
_WORD = re.compile(r"[A-Za-z0-9][\w'.:/-]*")


def _words(text: str) -> List[str]:
    return [w.lower().rstrip(".,:;!?'\"") for w in _WORD.findall(text or "")]


def _content(text: str) -> Set[str]:
    return {w for w in _words(text)
            if w and w not in TOPIC_STOP and w not in RESTATE_VOCAB and w not in FILLER and w not in ACK and len(w) > 1}


def _options(text: str) -> Set[str]:
    """Named options in a sentence: SQLite, MongoDB, AWS, v2, postgres:16, next.js, a mid-sentence Name."""
    found = {m.group(0).lower() for m in OPTION.finditer(text or "")}
    found |= {m.group(0).lower() for m in CAPWORD.finditer(text or "") if m.group(0) not in COMMON_CAPS}
    return {f.rstrip(".:/") for f in found if f not in COMMON_LOWER}


def _only(text: str, vocab: Set[str]) -> bool:
    ws = [w for w in _words(text) if w]
    return bool(ws) and all(w in vocab for w in ws)


class Tail:
    """The decision's session after the decision: [(kind, speaker, ref, text)] in order."""

    def __init__(self, cfg: Config, line: lookup.JLine, quote: str):
        self.items: List[Tuple[str, str, str, str]] = []
        sents = sentences(line.text)
        idx = next((i for i, s in enumerate(sents) if quote and (quote.lower() in s.lower()
                                                                 or s.lower() in quote.lower())), -1)
        rest = " ".join(sents[idx + 1:]) if idx >= 0 else ""
        if rest:
            self.items.append(("msg", line.speaker or "", line.ref, rest))
        self.last_at = ""
        if line.kind == "turn":
            return
        for l in sorted((l for l in lookup.lines_for(cfg, line.path) if l.order > line.order),
                        key=lambda l: l.order):
            if l.kind == "reply" or l.principal:
                self.items.append((l.kind, l.speaker or "", l.ref, l.text))
        self.last_at = str(lookup.session_meta(cfg, line.path).get("updated_at") or "")


def sentence_doubt(decision: str, s: str, strict: bool = True) -> Optional[str]:
    """Why a later principal sentence could be about the decision, else None (clear).

    strict (auto-accept): any choice signal at all. Not strict (the operator asked to record this exact
    decision with brain-decide): only signals tied to the decision (its subject, a switch or take-back,
    a comparison, an alternative question, a bare "no"/"wait" or fragment naming another option,
    another choice naming another option), so unrelated later work does not hold it."""
    s = s.strip()
    if not s or _only(s, ACK):
        return None
    dec_words, dec_opts = _content(decision), _options(decision) | _content(decision)
    content = _content(s)
    if content and content <= dec_words and not (HESITATE.search(s) or EVALUATE.search(s) or SWITCH.search(s)):
        return None  # a restatement in the decision's own words ("Great, Postgres it is.")
    opts = _options(s)
    new_opts = sorted(o for o in opts if o not in dec_opts)
    if strict:
        checks = (
            (s.rstrip().endswith("?") and ALT_QUESTION.search(s), "asks about an alternative"),
            (SWITCH.search(s) or takeback.MARKER.search(s), "switch or take-back marker"),
            (HESITATE.search(s), "negation or hesitation"),
            (EVALUATE.search(s), "comparison or preference"),
            (CHOICE.search(s), "a choice verb"),
            (new_opts, "names another option (%s)" % ", ".join(new_opts[:3])),
            (content & dec_words, "mentions the decision's subject"),
            (len(_words(s)) <= 3, "a bare fragment"),
            ((cues.classify(s) or _NoHit).kind in ("decision", "correction"), "another decision or correction"),
        )
    else:  # tied to this decision only
        checks = (
            (s.rstrip().endswith("?") and ALT_QUESTION.search(s), "asks about an alternative"),
            (SWITCH.search(s) or takeback.MARKER.search(s), "switch or take-back marker"),
            (COMPARE.search(s) or MAKE_IT.search(s), "comparison"),
            (content & dec_words, "mentions the decision's subject"),
            (len(_words(s)) <= 3 and new_opts, "a bare fragment naming another option"),
            (takeback.OPENER.search(s) and not (content - opts - HESITATION_WORDS), "a bare 'no'/'wait' naming an option"),
            (new_opts and (OFFER_CHOICE.search(s) or (cues.classify(s) or _NoHit).kind == "decision"),
             "another choice naming another option"),
        )
    for hit, why in checks:
        if hit:
            return why
    return None


class _NoHit:
    kind = ""


def _offer(decision: str, reply: str, strict: bool = True) -> Tuple[bool, bool]:
    """(offers an alternative, asks to confirm exactly the decision) for one assistant reply."""
    alt = restate = False
    dec_topic = _content(decision)
    dec_opts = _options(decision) | dec_topic
    for s in sentences(reply):
        if not OFFER.search(s):
            continue
        content = _content(s)
        exact = (s.rstrip().endswith("?") and bool(dec_topic) and dec_topic <= content | _options(s)
                 and content <= dec_topic and not SWITCH.search(s) and not COMPARE.search(s))
        if exact:
            restate = True
            continue
        new = [o for o in _options(s) if o not in dec_opts]
        if content & dec_topic or (new and (SWITCH.search(s) or COMPARE.search(s) or OFFER_CHOICE.search(s))):
            alt = True
        elif strict and (SWITCH.search(s) or COMPARE.search(s) or OFFER_CHOICE.search(s) or new):
            alt = True
    return alt, restate and not alt


def assess(cfg: Config, line: lookup.JLine, quote: str, strict: bool = True,
           decision: str = "") -> Tuple[Optional[str], str, str]:
    """-> (V12 doubt reason or None, ref of an explicit confirmation or '', session's last activity).

    `quote` locates the decision in its line; `decision` (default: the quote) is what it is about,
    e.g. the quote plus the assistant proposal an approval approves."""
    tail = Tail(cfg, line, quote)
    quote = decision or quote
    offered = restated = False
    confirmed = ""
    for kind, _speaker, ref, text in tail.items:
        if kind == "reply":
            offered, restated = _offer(quote, text, strict)
            continue
        for i, s in enumerate(sentences(text)):
            if offered:
                return ("V12: the operator answered an assistant offer of an alternative (%r); an alternative the "
                        "operator agrees to supersedes the earlier choice" % clip(s, 60)), "", tail.last_at
            if restated and i == 0 and _only(s, AFFIRM):
                confirmed = ref
                continue
            why = sentence_doubt(quote, s, strict)
            if why:
                return ("V12: a later turn in the same session could change it (%r: %s); the operator confirms "
                        "which choice stands" % (clip(s, 60), why)), "", tail.last_at
        offered = restated = False
    return None, confirmed, tail.last_at


def settled(cfg: Config, last_at: str) -> bool:
    """The session has been quiet for learn.settle_minutes (a current-turn line never is)."""
    if not last_at:
        return False
    try:
        quiet = (cfg.now() - parse_iso(last_at)).total_seconds() / 60.0
    except (ValueError, TypeError):
        return False
    return quiet >= cfg.settle_minutes


def any_doubt(cfg: Config, line: Optional[lookup.JLine], quote: str, strict: bool = True) -> Optional[str]:
    return assess(cfg, line, quote, strict)[0] if line is not None and quote else None


def strict_for(detected_by: str) -> bool:
    """Auto-accept reads every signal; an explicit brain-decide / remember request only same-topic ones."""
    return str(detected_by or "") not in ("decide", "operator")
