"""The mechanical verifier, V1-V9 (spec section 10.5). A candidate that fails
any rule is rejected; nothing is promoted on an LLM's say-so.

V1 exact quote in the cited principal line(s)   V2 principal speaker (decides)
V3 approvals: assistant proposal + principal yes V4 numbers/URLs/emails sourced
V5 duplicates -> noop; supersedes target valid   V6 external context -> review
V7 redaction scan clean                          V8 no hypotheticals/questions
V9 target register inside the speaker's scope
V10 statement fidelity and V11 context (guards.py) send to review. V12
(settle.py): a routine decision is a candidate until its session settles with
no doubt, or the operator confirms it; it is never accepted from wording alone.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from . import cues, frontmatter, guards, lookup, records, redact, settle
from .config import Config
from .textutil import contains, glob_match, normalize, sentences, statement_hash

JUDGED = ("decision", "preference", "correction")
EXTERNAL = "V6: session used external context; never auto-promoted"
_TOKENS = re.compile(r"https?://\S+|[\w.+-]+@[\w-]+\.[\w.-]+|\d+(?:[.,:/-]\d+)*")


class Result:
    def __init__(self):
        self.status = "pass"  # pass | fail | pending | noop | review | waiting
        self.reasons: List[str] = []
        self.line: Optional[lookup.JLine] = None

    def fail(self, reason: str) -> "Result":
        self.status, self.reasons = "fail", self.reasons + [reason]
        return self


def _locate(cfg: Config, cand: Dict, res: Result) -> Optional[lookup.JLine]:
    quote = cand.get("quote") or ""
    line = lookup.resolve(cfg, cand.get("source_ref") or "")
    if line is not None and contains(line.text, quote) and (line.kind != "turn" or line.principal):
        if line.kind != "turn":
            return line
    hits = lookup.search(cfg, quote)
    journal_hits = [h for h in hits if h.kind != "turn"]
    if journal_hits:
        return journal_hits[0]
    if hits:
        res.status = "pending"
        res.reasons.append("V1: quote found only in the current turn (turns.jsonl); re-checked at next sync")
        return hits[0]
    return None


def _v4(cand: Dict, source_text: str) -> List[str]:
    missing = []
    src = normalize(source_text)
    for field in ("title", "statement"):
        for tok in _TOKENS.findall(cand.get(field) or ""):
            if normalize(tok).rstrip(".,") not in src:
                missing.append(tok)
    return sorted(set(missing))


def _sentence_ctx(text: str, quote: str):
    sents = sentences(text)
    for i, s in enumerate(sents):
        if contains(s, quote) or contains(quote, s):
            return s, (sents[i + 1] if i + 1 < len(sents) else "")
    return quote, ""


def _v3(cfg: Config, cand: Dict, line: lookup.JLine) -> Optional[str]:
    proposal = cand.get("approves_quote") or ""
    session = lookup.lines_for(cfg, line.path) if line.kind != "turn" else []
    replies = sorted((l for l in session if l.kind == "reply" and contains(l.text, proposal)
                      and l.order < line.order), key=lambda l: l.order)
    if not replies:
        return "V3: approves_quote is not verbatim in an earlier assistant reply of this session"
    later = sorted((l for l in session if l.kind == "msg" and l.principal and l.order > replies[-1].order),
                   key=lambda l: l.order)
    after = later[:2]
    if line.label not in [l.label for l in after]:
        return "V3: the approval is not within the next 2 principal turns after the proposal"
    return None


def _external(cfg: Config, line: lookup.JLine) -> str:
    """V6 reason or '': the session used web/MCP/search, or it is a hand-written note."""
    if line.kind == "turn":
        return ""
    rel = line.path[len("brain/"):] if line.path.startswith("brain/") else line.path
    for p in (cfg.brain / rel, cfg.state / rel):
        if p.is_file():
            meta = frontmatter.read(p)[0]
            if meta.get("external_context"):
                return EXTERNAL
            if meta.get("runtime") == "note":
                return "V6: hand-written journal note, not a runtime transcript; the operator confirms it in review"
    return ""


def _duplicate(cfg: Config, cand: Dict, ref: str = "") -> Optional[str]:
    """Same statement, same quote, or an overlapping quote from the same source line."""
    h = statement_hash(cand.get("statement") or "")
    q = normalize(cand.get("quote") or "")
    for r in records.all_records(cfg):
        if r.kind != cand.get("kind") or r.status not in records.ACTIVE:
            continue
        other = r.meta.get("title") if r.kind == "decision" else r.meta.get("statement")
        rq = normalize(str(r.meta.get("source_quote") or ""))
        same_line = bool(ref) and str(r.meta.get("source_ref") or "") == ref and bool(q) and (q in rq or rq in q)
        if statement_hash(str(r.meta.get("statement") or other or "")) == h or rq == q or same_line:
            return r.id
    return None


def _v2(cfg: Config, cand: Dict, line: lookup.JLine) -> Optional[str]:
    speaker = line.speaker if line.principal else None
    p = cfg.principal(speaker) if speaker else None
    if not p or not p.get("decides", True):
        return "V2: source speaker %r is not a deciding principal" % (line.speaker,)
    if cand.get("speaker") and cand["speaker"] != speaker:
        return "V2: candidate speaker %r does not match the source line (%r)" % (cand["speaker"], speaker)
    return None


def _also_quoted(cfg: Config, cand: Dict) -> Optional[str]:
    for q in cand.get("also_quoted") or []:
        if not [h for h in lookup.search(cfg, q) if h.principal]:
            return "V1: also_quoted %r is not a principal's words in the journal or current turn" % q
    return None


def _v8(cand: Dict, line: lookup.JLine) -> Optional[str]:
    quote = cand.get("quote") or ""
    sentence, following = _sentence_ctx(line.text, quote)
    if cues.is_hypothetical(sentence, following) or quote.strip().endswith("?"):
        return "V8: hypothetical"
    return None


def _rules(cfg: Config, cand: Dict, line: lookup.JLine) -> Optional[str]:
    """V1 length, V2, V3, V4, V8, V9 and supersedes (V5) in order; the first failure wins."""
    kind, quote = cand.get("kind") or "", cand.get("quote") or ""
    if len(normalize(quote)) < 12 and not cand.get("approves_quote"):
        return "V1: quote shorter than 12 characters"
    err = _v2(cfg, cand, line) if kind in JUDGED else None
    err = err or _also_quoted(cfg, cand)
    err = err or (_v3(cfg, cand, line) if cand.get("approves_quote") else None)
    if err:
        return err
    source = " ".join([line.text, quote, cand.get("approves_quote") or ""] + list(cand.get("also_quoted") or []))
    missing = _v4(cand, source)
    if missing:
        return "V4: not in the source: %s" % ", ".join(missing)
    err = _v8(cand, line) if kind in ("decision", "preference") else None
    err = err or (_v9(cfg, line.speaker, cand.get("target") or "") if kind in JUDGED else None)
    sup = cand.get("supersedes") or ""
    if not err and sup:
        old = records.find(cfg, sup)
        if old is None or old.meta.get("superseded_by"):
            err = "V5: supersedes target %s missing or already superseded" % sup
    return err


def check(cfg: Config, cand: Dict) -> Result:
    res = Result()
    blob = " ".join(str(cand.get(k) or "") for k in ("quote", "statement", "title", "approves_quote"))
    found = redact.scan(blob + " " + " ".join(cand.get("also_quoted") or []))
    if found:
        return res.fail("V7: secret-shaped content (%s)" % ", ".join(found))
    line = _locate(cfg, cand, res)
    if line is None:
        return res.fail("V1: quote not found verbatim in any journal line or current turn")
    res.line = line
    err = _rules(cfg, cand, line)
    if err:
        return res.fail(err)
    dup = _duplicate(cfg, cand, line.ref if line.kind != "turn" else "")
    if dup and not cand.get("supersedes"):
        res.status = "noop"
        res.reasons.append("V5: duplicate of %s" % dup)
        return res
    held = _guard(cfg, cand, line) if res.status in ("pass", "pending") else None
    if held:
        res.status = "review"
        res.reasons.append(held)
        return res
    why = "" if res.status != "pass" or cand.get("operator_approved") else (
        EXTERNAL if cand.get("external_context") else _external(cfg, line))
    if why:
        res.status = "review"
        res.reasons.append(why)
    elif res.status == "pass":
        _settle(cfg, cand, line, res)
    return res


def settle_check(cfg: Config, cand: Dict, line: lookup.JLine) -> Result:
    """V12 alone, for a record re-checked after its quote reached the journal (promote.recheck_pending)."""
    res = Result()
    res.line = line
    _settle(cfg, cand, line, res)
    return res


def _settle(cfg: Config, cand: Dict, line: lookup.JLine, res: Result) -> None:
    """V12: a routine decision is accepted only when confirmed, or settled with no doubt (settle.py)."""
    if cand.get("kind") != "decision" or cand.get("operator_approved") or cand.get("tier") == "material":
        return
    strict = settle.strict_for(cand.get("detected_by") or "")
    decision = " ".join(x for x in (cand.get("quote"), cand.get("approves_quote")) if x)
    doubt, confirmed_ref, last_at = settle.assess(cfg, line, cand.get("quote") or "", strict, decision)
    if doubt:
        res.status = "review"
        res.reasons.append(doubt)
    elif confirmed_ref:
        cand["confirmed_ref"] = confirmed_ref
    elif strict and not cfg.auto_accept:
        res.status = "review"
        res.reasons.append("V12: learn.auto_accept is off; the operator confirms every decision in review")
    elif strict and not settle.settled(cfg, last_at):
        res.status = "waiting"
        res.reasons.append("V12: waiting for the session to settle (%s min quiet after %s); then accepted only if "
                           "no later turn raises doubt" % (int(cfg.settle_minutes), last_at or "the current turn"))


def _v9(cfg: Config, speaker: Optional[str], target: str) -> Optional[str]:
    p = cfg.principal(speaker or "") or {}
    rel = target[len("brain/"):] if target.startswith("brain/") else target
    scopes = p.get("scope") or ["**"]
    if not any(glob_match(g, rel) for g in scopes):
        return "V9: target %r is outside %s's scope %s" % (rel, speaker, scopes)
    return None


def _following(cfg: Config, line: lookup.JLine) -> str:
    """The next principal message after `line` in the same session ('' if none yet)."""
    if line.kind == "turn":
        return ""
    later = sorted((l for l in lookup.lines_for(cfg, line.path) if l.kind == "msg" and l.principal
                    and l.order > line.order), key=lambda l: l.order)
    return later[0].text if later else ""


def _guard(cfg: Config, cand: Dict, line: lookup.JLine) -> Optional[str]:
    """V10 (statement fidelity) then V11 (context); skipped once the operator approved it."""
    kind = cand.get("kind") or ""
    if cand.get("operator_approved") or kind == "skill":
        return None
    source = " ".join([line.text, cand.get("quote") or "", cand.get("approves_quote") or ""]
                      + list(cand.get("also_quoted") or []))
    why = guards.fidelity(cand, source)
    if why or kind not in JUDGED:
        return why
    why = guards.context(kind, cand.get("quote") or "", line.text, _following(cfg, line),
                         approval=bool(cand.get("approves_quote")))
    return why
