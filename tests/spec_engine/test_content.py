"""Tests for spec_engine.content: OpenQuestion validation, slug helper,
id/timestamp helpers."""

from __future__ import annotations

import re

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.content import (
    OpenQuestion,
    SpecEngineError,
    is_valid_slug,
    new_id,
    utc_now_iso,
)


def test_is_valid_slug_accepts_safe_slugs():
    assert is_valid_slug("plan-abc123")
    assert is_valid_slug("a")
    assert is_valid_slug("a.b_c-d9")


@pytest.mark.parametrize("bad", ["", "Abc", "-abc", "a/b", "a\\b", "a b", "../etc/passwd"])
def test_is_valid_slug_rejects_unsafe_values(bad):
    assert not is_valid_slug(bad)


def test_new_id_is_a_safe_slug_with_the_given_prefix():
    the_id = new_id("plan")
    assert the_id.startswith("plan-")
    assert is_valid_slug(the_id)


def test_utc_now_iso_shape():
    ts = utc_now_iso()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", ts)


def test_open_question_valid_construction():
    oq = OpenQuestion(id="oq-1", question="What color?", category="design", raised_from="no signal")
    assert oq.blocking is False
    assert oq.status == "open"
    assert oq.resolution is None


def test_open_question_rejects_bad_id():
    with pytest.raises(SpecEngineError):
        OpenQuestion(id="Not Safe!", question="q", category="design", raised_from="x")


def test_open_question_rejects_empty_question():
    with pytest.raises(SpecEngineError):
        OpenQuestion(id="oq-1", question="   ", category="design", raised_from="x")


def test_open_question_rejects_bad_category():
    with pytest.raises(SpecEngineError):
        OpenQuestion(id="oq-1", question="q", category="not-a-real-category", raised_from="x")


def test_open_question_rejects_bad_status():
    with pytest.raises(SpecEngineError):
        OpenQuestion(id="oq-1", question="q", category="design", raised_from="x", status="pending")
