"""Tests for spec_engine.spec_lint — advisory quality checks, never
blocking."""

from __future__ import annotations

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.gate_approval import sign_local_approval
from spec_engine.content import OpenQuestion
from spec_engine.intake import harvest_intake
from spec_engine.plan_builder import build_plan
from spec_engine.spec_builder import build_spec
from spec_engine.spec_lint import LintFinding, has_blocking_errors, lint


def _spec(text="An app that tracks invoices.", source="fragment"):
    plan = build_plan(harvest_intake(text, source))
    approval = sign_local_approval(plan, approved_by="Xavier")
    return build_spec(plan, approval)


def test_lint_finding_rejects_bad_severity():
    import pytest

    with pytest.raises(ValueError):
        LintFinding(severity="catastrophic", code="x", message="x")


def test_lint_flags_empty_how_it_looks_as_warning():
    spec = _spec("A backend batch job that runs at midnight and emails a report to the finance team.")
    findings = lint(spec)
    codes = {f.code for f in findings}
    assert "empty-how-it-looks" in codes


def test_lint_flags_no_acceptance_criteria_as_warning():
    spec = _spec("A vague app idea with nothing concrete stated.")
    findings = lint(spec)
    codes = {f.code for f in findings}
    assert "no-acceptance-criteria" in codes


def test_lint_flags_unresolved_blocking_open_question_as_error():
    spec = _spec("An app that tracks invoices and should be able to send reminders.")
    blocking_q = OpenQuestion(
        id="oq-block", question="Which payment gateway?", category="technical", raised_from="test", blocking=True,
    )
    spec.open_questions.append(blocking_q)
    findings = lint(spec)
    assert has_blocking_errors(findings)
    codes = {f.code for f in findings}
    assert "unresolved-blocking-open-question" in codes


def test_lint_never_raises_on_a_thin_spec():
    spec = _spec("x")
    findings = lint(spec)
    assert isinstance(findings, list)


def test_lint_is_deterministic():
    spec = _spec("An app that tracks invoices.")
    assert lint(spec) == lint(spec)
