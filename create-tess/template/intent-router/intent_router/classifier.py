"""Deterministic heuristic classifier — the "testable separately" half of
the intent router (parent task brief: "if it uses a model call, keep the
deterministic mapping testable separately").

This module never calls a model and never performs network I/O. It scores
every route in a routing table against freeform input using:

  1. keyword/phrase matching (exact phrase match scores highest; a partial,
     unordered token match on a multi-word keyword scores proportionally,
     so paraphrases of a keyword still register some signal); and
  2. stopword-filtered token overlap against each route's example
     utterances (so a route with richer examples generalizes better to
     input that doesn't literally contain one of its keyword phrases).

An `ExternalSignal` (see types.py) — e.g. a model's own read of the input
inside a live session — can be blended in, but every code path here is a
pure function of its arguments: given the same input text, table, and
optional signal, the result is always identical. That is what makes this
half of the router unit-testable without ever invoking a model.
"""

from __future__ import annotations

import re
from typing import List, Optional, Set

from .routing_table import RoutingTable
from .types import ExternalSignal, Route, ScoredCandidate

# Weights are deliberately small integers/fractions so a hand-computed
# expected score in a unit test is easy to verify by eye.
KEYWORD_PHRASE_WEIGHT = 2.0
KEYWORD_PARTIAL_MIN_RATIO = 0.5  # a keyword's tokens must be >=50% present to count at all
EXAMPLE_TOKEN_WEIGHT = 0.5
EXAMPLE_TOKEN_CAP = 8  # ignore additional shared tokens beyond this many (diminishing returns)
EXTERNAL_ROUTE_BOOST = 3.0
EXTERNAL_OUTCOME_BOOST = 1.0
CONFIDENCE_NORMALIZER = 6.0  # raw_score / this, clamped to [0, 1]

# A small, generic English stopword list — filtered out of BOTH the input
# and every route's example text before computing token overlap, so
# ubiquitous connective words don't manufacture false signal across every
# route indiscriminately.
STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "if", "then", "so", "to", "of",
    "in", "on", "at", "for", "with", "about", "into", "over", "after",
    "before", "is", "are", "was", "were", "be", "been", "being", "i",
    "we", "you", "he", "she", "it", "they", "this", "that", "these",
    "those", "my", "our", "your", "their", "its", "not", "no", "just",
    "really", "very", "quite", "actually", "right", "now", "get", "got",
    "have", "has", "had", "do", "does", "did", "can", "could", "would",
    "should", "will", "shall", "what", "when", "where", "who", "why",
    "how", "there", "here", "as", "up", "down", "out", "off", "again",
    "all", "any", "some", "than", "too", "us", "me", "am", "let",
    # Contraction remnants: the tokenizer regex splits on the apostrophe
    # ("don't" -> "don"+"t", "we're" -> "we"+"re", "I'm" -> "i"+"m"), and
    # these fragments carry no topical signal on their own — left
    # unfiltered they manufacture spurious cross-route overlap (e.g. two
    # unrelated sentences that both happen to contain "don't"/"isn't").
    "don", "doesn", "isn", "wasn", "aren", "won", "couldn", "wouldn",
    "shouldn", "hasn", "haven", "hadn", "didn", "ve", "re", "ll", "m",
    "s", "d", "t",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> str:
    return text.lower()


def _tokens(text: str, *, filter_stopwords: bool = True) -> Set[str]:
    toks = set(_TOKEN_RE.findall(_normalize(text)))
    if filter_stopwords:
        toks -= STOPWORDS
        # Belt-and-suspenders: any leftover single-character token is a
        # contraction fragment or a typo, never real topical signal.
        toks = {t for t in toks if len(t) > 1}
    return toks


def _keyword_score(input_normalized: str, input_tokens: Set[str], keyword: str) -> float:
    kw_norm = keyword.lower().strip()
    if not kw_norm:
        return 0.0
    if kw_norm in input_normalized:
        return KEYWORD_PHRASE_WEIGHT
    kw_tokens = _tokens(keyword, filter_stopwords=False)
    if not kw_tokens:
        return 0.0
    overlap = kw_tokens & input_tokens
    ratio = len(overlap) / len(kw_tokens)
    if ratio >= KEYWORD_PARTIAL_MIN_RATIO:
        return KEYWORD_PHRASE_WEIGHT * ratio
    return 0.0


def score_route(
    input_text: str,
    route: Route,
    external_signal: Optional[ExternalSignal] = None,
) -> ScoredCandidate:
    """Score exactly one route against `input_text`. Pure function — no
    randomness, no I/O, no shared mutable state."""
    input_normalized = _normalize(input_text)
    input_tokens = _tokens(input_text)

    raw = 0.0
    matched: List[str] = []

    for kw in route.keywords:
        s = _keyword_score(input_normalized, input_tokens, kw)
        if s > 0:
            raw += s
            matched.append(kw)

    example_tokens: Set[str] = set()
    for ex in route.examples:
        example_tokens |= _tokens(ex)
    shared = input_tokens & example_tokens
    if shared:
        raw += EXAMPLE_TOKEN_WEIGHT * min(len(shared), EXAMPLE_TOKEN_CAP)
        # Surface the shared vocabulary as evidence too — otherwise a route
        # that wins purely on example overlap (no keyword hit) would report
        # an empty `matched_signals`, which is a real interpretability gap:
        # the narration's "Why: matched on ..." line must be able to point
        # at SOMETHING even when the signal came from example overlap, not
        # a curated keyword.
        matched.append("shared terms: " + ", ".join(sorted(shared)[:EXAMPLE_TOKEN_CAP]))

    if external_signal is not None:
        if external_signal.suggested_route_id and external_signal.suggested_route_id == route.id:
            raw += EXTERNAL_ROUTE_BOOST * external_signal.confidence
            matched.append(f"external-signal:route={external_signal.suggested_route_id}")
        elif external_signal.outcome_type and external_signal.outcome_type == route.outcome_type:
            raw += EXTERNAL_OUTCOME_BOOST * external_signal.confidence
            matched.append(f"external-signal:outcome_type={external_signal.outcome_type}")

    confidence = max(0.0, min(1.0, raw / CONFIDENCE_NORMALIZER))
    return ScoredCandidate(route=route, raw_score=raw, confidence=confidence, matched_signals=matched)


def classify(
    input_text: str,
    routing_table: RoutingTable,
    external_signal: Optional[ExternalSignal] = None,
) -> List[ScoredCandidate]:
    """Score every route in `routing_table` and return candidates sorted by
    confidence, descending. Ties are broken by route id (alphabetical) so
    the result is fully deterministic run to run."""
    scored = [score_route(input_text, r, external_signal) for r in routing_table]
    scored.sort(key=lambda c: (-c.confidence, c.route.id))
    return scored
