"""Tests for the deterministic heuristic classifier — pure functions, no
model call, hand-computable expected scores."""

from __future__ import annotations

import _paths  # noqa: F401 -- sys.path bootstrap, see _paths.py docstring

from intent_router import ExternalSignal, Route, RoutingTable
from intent_router.classifier import classify, score_route


def _route(**kwargs):
    defaults = dict(id="r", entry_command="/r", outcome_type="decide")
    defaults.update(kwargs)
    return Route(**defaults)


def test_exact_keyword_phrase_match_scores_full_weight():
    route = _route(keywords=["conversion rate"])
    candidate = score_route("our conversion rate is dropping fast", route)
    assert candidate.raw_score == 2.0
    assert candidate.matched_signals == ["conversion rate"]


def test_no_signal_scores_zero():
    route = _route(keywords=["conversion rate"], examples=["pricing is too high"])
    candidate = score_route("what should I have for lunch today", route)
    assert candidate.raw_score == 0.0
    assert candidate.confidence == 0.0
    assert candidate.matched_signals == []


def test_partial_keyword_token_match_scores_proportionally():
    # "conversion rate" tokens = {conversion, rate}; input shares only "rate"
    # -> ratio 0.5, exactly at the partial-match threshold.
    route = _route(keywords=["conversion rate"])
    candidate = score_route("the close rate on demos fell off a cliff", route)
    assert candidate.raw_score == 1.0  # 2.0 * 0.5
    assert candidate.matched_signals == ["conversion rate"]


def test_keyword_with_less_than_half_token_overlap_does_not_match():
    # "conversion rate" tokens = {conversion, rate}; input shares neither.
    route = _route(keywords=["conversion rate"])
    candidate = score_route("the weather has been lovely lately", route)
    assert candidate.raw_score == 0.0
    assert candidate.matched_signals == []


def test_example_token_overlap_scores_even_without_a_keyword_hit():
    route = _route(
        keywords=[],
        examples=["our pipeline is completely empty and deals keep stalling"],
    )
    candidate = score_route("the pipeline stalled and deals disappeared", route)
    assert candidate.raw_score > 0.0
    # shared, non-stopword tokens: pipeline, stalled/stalling (different forms
    # so NOT shared literally), deals -> at least "pipeline" and "deals"
    assert candidate.raw_score == 1.0  # 0.5 * 2 shared tokens


def test_stopwords_do_not_inflate_example_overlap():
    route = _route(keywords=[], examples=["the a and or if then so to of in on"])
    candidate = score_route("the a and or if then so to of in on", route)
    assert candidate.raw_score == 0.0


def test_confidence_is_clamped_to_one():
    route = _route(keywords=["a", "b", "c", "d", "e", "f", "g", "h"])
    candidate = score_route("a b c d e f g h", route)
    assert candidate.confidence == 1.0


def test_external_signal_route_boost_favors_named_route():
    weak_route = _route(id="weak", entry_command="/weak", outcome_type="decide", keywords=[])
    signal = ExternalSignal(suggested_route_id="weak", confidence=1.0)
    candidate = score_route("totally unrelated text with zero keyword overlap", weak_route, signal)
    assert candidate.raw_score == 3.0
    assert any("external-signal" in s for s in candidate.matched_signals)


def test_external_signal_outcome_type_boost_is_smaller_than_route_boost():
    route_matching_outcome = _route(
        id="matches-outcome", entry_command="/m", outcome_type="build", keywords=[]
    )
    signal = ExternalSignal(outcome_type="build", confidence=1.0)
    candidate = score_route("no keyword overlap here at all", route_matching_outcome, signal)
    assert candidate.raw_score == 1.0


def test_external_signal_does_not_boost_unrelated_route():
    route = _route(id="unrelated", entry_command="/u", outcome_type="scale", keywords=[])
    signal = ExternalSignal(suggested_route_id="something-else", outcome_type="build", confidence=1.0)
    candidate = score_route("no overlap", route, signal)
    assert candidate.raw_score == 0.0


def test_classify_sorts_by_confidence_descending_then_route_id():
    high = _route(id="b-high", entry_command="/b", outcome_type="decide", keywords=["match here"])
    low = _route(id="a-low", entry_command="/a", outcome_type="decide", keywords=[])
    table = RoutingTable([low, high])
    ranked = classify("there is a match here in this text", table)
    assert ranked[0].route.id == "b-high"
    assert ranked[1].route.id == "a-low"


def test_classify_ties_broken_by_route_id_alphabetically():
    r1 = _route(id="zzz", entry_command="/z", outcome_type="decide", keywords=[])
    r2 = _route(id="aaa", entry_command="/a", outcome_type="decide", keywords=[])
    table = RoutingTable([r1, r2])
    ranked = classify("no signal at all", table)
    assert ranked[0].confidence == ranked[1].confidence == 0.0
    assert ranked[0].route.id == "aaa"
    assert ranked[1].route.id == "zzz"


def test_score_route_is_a_pure_function_no_shared_state():
    route = _route(keywords=["pricing"])
    a = score_route("our pricing is wrong", route)
    b = score_route("our pricing is wrong", route)
    assert a.raw_score == b.raw_score
    assert a.matched_signals == b.matched_signals
