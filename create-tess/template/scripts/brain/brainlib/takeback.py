"""V11 take-backs, conditionals and content-free statements (fix round 2).

A principal sentence that looks like a decision is not a decision when the
principal takes it back, in the same message or the next one. The phrase list
alone missed most real take-backs ("Actually no.", "Wait, no.", "I changed my
mind.", "not Heroku after all"), so a later sentence counts as a take-back of
an earlier statement when:

1. it negates, cancels or forgets a word of that statement ("not Heroku",
   "forget Heroku", "cancel the Heroku plan"), or
2. it carries a take-back marker ("changed my mind", "on second thought",
   "hold off", "that's not a decision", ...) and names a word of the
   statement, or
3. it is a bare take-back (a marker or a "No"/"Wait" opener with nothing else
   of substance) directly after the statement, or at the start of the next
   principal message.

A later sentence with its own substance ("No, that's wrong: the timezone is
SGT") is a correction of something else and leaves the statement alone. When
in doubt the statement goes to review (status proposed); it is never dropped.
"""
from __future__ import annotations

import re
from typing import Optional, Set

from .textutil import sentences

MARKER = re.compile(
    r"(?i)\b(just kidding|jk|scratch that|strike that|belay that|never ?mind|nvm|"
    r"(?:ignore|disregard|forget|undo|cancel|scrap|drop) (?:that|this|it|my (?:last|previous)\b|the last\b)|"
    r"not decided|(?:haven't|have not|hasn't|not) (?:yet )?decided|not sure yet|take (?:that|it) back|"
    r"taking (?:that|it) back|changed? (?:my|our) minds?|change of plans?|on second thoughts?|second thoughts|"
    r"let me (?:re-?think|reconsider|think (?:about|on|it over))|re-?think(?:ing)? (?:that|this|it)|"
    r"reconsider(?:ing)?|hold off|hold on|hang on|not so fast|after all|"
    r"(?:that|this|it)(?:'s| is| was)? not (?:a |my |our )?(?:decision|final|decided)|"
    r"(?:that|this|it) (?:wasn't|isn't) (?:a |my |our )?(?:decision|final)|not a decision|"
    r"just (?:brainstorming|thinking|musing|spitballing|an idea)|thinking out loud|"
    r"(?:don't|do not) do (?:that|it|this)|(?:don't|do not) (?:go with|use) (?:that|it|this))\b")
OPENER = re.compile(r"(?i)^\s*(?:(?:actually|hmm+|ok(?:ay)?|oh)[,.!\s]+)?"
                    r"(?:no|nope|nah|wait|hmm+|hang on|hold on|cancel|forget|scrap|ignore|disregard)\b")
NEGATED = re.compile(r"(?i)\b(?:not|no|never|don't|do not|forget|forgot|cancel|scrap|ditch|skip|ignore|"
                     r"instead of|rather than)\s+((?:[\w'-]+[\s,]+){0,2}[\w'-]+)")
VOCAB = set("""
actually wait hmm hang hold on off changed change mind minds cancel scrap drop second thought thoughts rethink
reconsider forget ignore disregard undo last message previous earlier decision decisions final brainstorm
brainstorming thinking thought loud idea ideas bad wrong mistake kidding scratch strike belay never mind nvm
take back taking after all sure yet decided don't dont no nope nah not really fast plan plans oh just musing
spitballing do doing done again jk scratch
""".split())
CONDITIONAL = re.compile(
    r"(?i)(?:\b(?:if|unless|provided|providing|assuming|as long as|depending on|in case|subject to|pending)\b"
    r"|\bor not\b|\bmaybe\b)")


def _substance(text: str) -> Set[str]:
    from .guards import NEGATION, _stem, content_words  # local: guards imports this module
    vocab = VOCAB | {_stem(w) for w in VOCAB} | NEGATION | {_stem(w) for w in NEGATION}
    return {w for w in content_words(text) if w not in vocab and w.rstrip("s") not in vocab}


def _negated(sentence: str) -> Set[str]:
    out: Set[str] = set()
    for m in NEGATED.finditer(sentence):
        out |= _substance(m.group(1))
    return out


def retracts(target: str, later: str, adjacent: bool) -> bool:
    """Does the sentence `later` take back the statement `target`?

    `adjacent` is True when `later` directly follows the statement (the next
    sentence of the same message, or the opening of the next message)."""
    tgt = _substance(target)
    marker, opener = MARKER.search(later), OPENER.search(later)
    if tgt & _negated(later):
        return True
    if not (marker or opener):
        return False
    rest = _substance(later)
    if not rest:
        return adjacent
    return bool(marker and rest & tgt)


def taken_back(target: str, rest_of_message: str, next_message: str) -> bool:
    """The same-message sentences after `target`, then the next message's first two sentences."""
    for i, s in enumerate(sentences(rest_of_message)):
        if retracts(target, s, adjacent=(i == 0)):
            return True
    return any(retracts(target, s, adjacent=True) for s in sentences(next_message)[:2])


def conditional(sentence: str) -> Optional[str]:
    """A decision that depends on something not yet known is held for review."""
    m = CONDITIONAL.search(sentence or "")
    if m:
        return "V11: conditional (%r); the operator confirms it in review" % m.group(0).strip()
    return None


def content_free(sentence: str) -> bool:
    """A preference or correction with nothing beyond its cue words ("No, don't do that.")."""
    cue = {"prefer", "always", "never", "from", "now", "like", "want", "stop", "said", "incorrect", "right",
           "wrong", "that", "that's", "thats", "correct", "answer", "reply", "write", "format", "send", "call"}
    return not {w for w in _substance(sentence) if w not in cue}
