"""Unit tests for the matrix (4 cells: model tier x scaffold) and the
report aggregation/rendering pipeline, against small synthetic trial
records — no `claude` subprocess involved.
"""
from __future__ import annotations

import pytest

from pg_lib.matrix import build_matrix
from pg_lib.report import TABLE_MARKER, aggregate_by_cell, render_report


def test_build_matrix_produces_four_cells_for_two_tiers_two_scaffolds():
    cells = build_matrix(["weak", "strong"], ["bare", "tess-os"], {"weak": "haiku", "strong": "opus"})
    assert len(cells) == 4
    cell_ids = {c.cell_id for c in cells}
    assert cell_ids == {"weak-bare", "weak-tess-os", "strong-bare", "strong-tess-os"}


def test_build_matrix_resolves_model_id_per_tier():
    cells = build_matrix(["weak"], ["bare"], {"weak": "haiku", "strong": "opus"})
    assert cells[0].model_id == "haiku"


def test_build_matrix_rejects_unknown_tier():
    with pytest.raises(ValueError):
        build_matrix(["medium"], ["bare"], {"weak": "haiku", "strong": "opus"})


def test_build_matrix_rejects_missing_model_id():
    with pytest.raises(ValueError):
        build_matrix(["weak", "strong"], ["bare"], {"weak": "haiku"})


def _trial(cell_id, task_id, attempt, passed, cost_usd, impure_bare=False):
    return {
        "cell_id": cell_id, "task_id": task_id, "attempt": attempt, "passed": passed,
        "cost_usd": cost_usd, "impure_bare": impure_bare,
    }


def test_aggregate_counts_pass_on_first_attempt():
    trials = [_trial("weak-bare", "01-x", 1, True, 0.01)]
    aggregated = aggregate_by_cell(trials)
    cell = aggregated["weak-bare"]
    assert cell["n_tasks"] == 1
    assert cell["n_passed"] == 1
    assert cell["verified_pass_rate"] == 1.0
    assert cell["mean_attempts_to_pass"] == 1


def test_aggregate_counts_pass_on_retry_and_sums_cost_across_attempts():
    trials = [
        _trial("weak-bare", "01-x", 1, False, 0.01),
        _trial("weak-bare", "01-x", 2, True, 0.02),
    ]
    aggregated = aggregate_by_cell(trials)
    cell = aggregated["weak-bare"]
    assert cell["n_passed"] == 1
    assert cell["mean_attempts_to_pass"] == 2
    assert cell["total_cost_usd"] == pytest.approx(0.03)


def test_aggregate_task_that_never_passes_counts_as_failed_not_missing():
    trials = [
        _trial("weak-bare", "01-x", 1, False, 0.01),
        _trial("weak-bare", "01-x", 2, False, 0.01),
        _trial("weak-bare", "01-x", 3, False, 0.01),
    ]
    aggregated = aggregate_by_cell(trials)
    cell = aggregated["weak-bare"]
    assert cell["n_tasks"] == 1
    assert cell["n_passed"] == 0
    assert cell["verified_pass_rate"] == 0.0
    assert cell["mean_attempts_to_pass"] is None


def test_aggregate_separates_cells_and_flags_impure_bare():
    trials = [
        _trial("weak-bare", "01-x", 1, True, 0.01, impure_bare=True),
        _trial("weak-tess-os", "01-x", 1, True, 0.05),
    ]
    aggregated = aggregate_by_cell(trials)
    assert aggregated["weak-bare"]["any_impure_bare"] is True
    assert aggregated["weak-tess-os"]["any_impure_bare"] is False


def test_render_report_requires_table_marker():
    aggregated = aggregate_by_cell([_trial("weak-bare", "01-x", 1, True, 0.01)])
    with pytest.raises(ValueError):
        render_report("a template with no marker", aggregated)


def test_render_report_substitutes_a_real_table():
    template = f"# Report\n\n{TABLE_MARKER}\n"
    aggregated = aggregate_by_cell([_trial("weak-bare", "01-x", 1, True, 0.01)])
    rendered = render_report(template, aggregated)
    assert TABLE_MARKER not in rendered
    assert "weak-bare" in rendered
    assert "1/1" in rendered


def test_render_report_substitutes_run_metadata_placeholders():
    template = (
        "Timestamp: `<!-- filled by run metadata -->`\n"
        "Models: `<!-- weak model id / strong model id -->`\n"
        f"{TABLE_MARKER}\n"
    )
    aggregated = aggregate_by_cell([_trial("weak-bare", "01-x", 1, True, 0.01)])
    rendered = render_report(template, aggregated, meta={"timestamp_utc": "20260707T000000Z", "models": "haiku"})
    assert "20260707T000000Z" in rendered
    assert "haiku" in rendered
    assert "<!-- filled by run metadata -->" not in rendered
