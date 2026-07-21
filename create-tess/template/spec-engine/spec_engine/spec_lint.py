"""Spec-lint: standalone quality checks over a `SpecDocument`.

Epic E2 assigns this pairing explicitly: "GPT Codex writes the schema
validator + spec-lint as a standalone tool with its own test suite
(well-specified, isolated — ideal Codex work)." `spec_check.py` is the
schema-validator half; this module is the lint half — deliberately
independent of both (no shared state, pure function of a `SpecDocument`),
so either can be lifted out and run by a different agent pool without the
other.

Lint findings are advisory, never blocking — this module never raises and
never mutates a spec. It surfaces gaps a human reviewing the plan/spec
should see; it does not gatekeep spec generation (that gate is
approval.py + spec_builder.py, a completely different control for a
completely different purpose: WHO approved WHAT, not IS this any good).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .types import SpecDocument

SEVERITIES = ("error", "warning", "info")


@dataclass(frozen=True)
class LintFinding:
    severity: str
    code: str
    message: str

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"LintFinding.severity {self.severity!r} must be one of {SEVERITIES}")


def lint(spec: SpecDocument) -> List[LintFinding]:
    """Return every lint finding for `spec`, in a fixed, deterministic
    order (same input -> same output list, always)."""
    findings: List[LintFinding] = []

    if not spec.what_it_does.summary.strip():
        findings.append(
            LintFinding("error", "empty-what-it-does", "what_it_does.summary is empty — every spec must say what the app does.")
        )
    if not spec.how_it_looks.description.strip() and not spec.how_it_looks.key_screens:
        findings.append(
            LintFinding(
                "warning",
                "empty-how-it-looks",
                "how_it_looks has no description and no key_screens — should be captured as an open question if genuinely undecided.",
            )
        )
    if not spec.how_it_works.description.strip() and not spec.how_it_works.key_flows:
        findings.append(
            LintFinding(
                "warning",
                "empty-how-it-works",
                "how_it_works has no description and no key_flows — should be captured as an open question if genuinely undecided.",
            )
        )
    if not spec.data_model.entities:
        findings.append(
            LintFinding("info", "no-data-model", "data_model has no entities — fine for a stateless app, otherwise expect an open question covering it.")
        )
    if not spec.acceptance_criteria:
        findings.append(
            LintFinding("warning", "no-acceptance-criteria", "acceptance_criteria is empty — E6's gate can't verify a spec with no testable criteria.")
        )
    if not spec.non_goals:
        findings.append(
            LintFinding("info", "no-non-goals", "non_goals is empty — consider whether scope boundaries are genuinely unbounded or just unstated.")
        )

    unresolved_blocking = [q for q in spec.open_questions if q.blocking and q.status == "open"]
    for q in unresolved_blocking:
        findings.append(
            LintFinding(
                "error",
                "unresolved-blocking-open-question",
                f"Open question {q.id!r} is marked blocking and still open: {q.question}",
            )
        )

    dangling_resolved = [q for q in spec.open_questions if q.status == "resolved" and not (q.resolution or "").strip()]
    for q in dangling_resolved:
        findings.append(
            LintFinding(
                "warning",
                "resolved-without-resolution-text",
                f"Open question {q.id!r} is marked resolved but carries no resolution text.",
            )
        )

    if not spec.open_questions:
        findings.append(
            LintFinding(
                "info",
                "empty-open-questions-ledger",
                "No open questions harvested — either the intake input was unusually complete, or ambiguity harvesting under-fired here.",
            )
        )

    return findings


def has_blocking_errors(findings: List[LintFinding]) -> bool:
    """Convenience predicate — `error`-severity findings are still never a
    hard stop anywhere in this package; a caller (e.g. a future CI check
    on generated-app specs) decides for itself whether to treat these as
    blocking in ITS context."""
    return any(f.severity == "error" for f in findings)
