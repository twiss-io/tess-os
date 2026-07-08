"""Unit tests for manifest loading/validation and the --dry-run path.

These are the tests behind the mission's acceptance bar: "python
run.py --dry-run validates all 10 task manifests + the matrix wiring."
"""
from __future__ import annotations

import textwrap

from pg_lib.dry_run import validate_everything
from pg_lib.manifest import ManifestError, load_manifest
from pg_lib.paths import PROVING_GROUND_ROOT, TASKS_ROOT
from pg_lib.task_registry import load_all_manifests, resolve_task_ids

MODEL_IDS = {"weak": "haiku", "strong": "opus"}


def test_all_ten_shipped_tasks_load_with_zero_errors():
    manifests, errors = load_all_manifests(TASKS_ROOT)
    assert errors == []
    assert len(manifests) >= 10


def test_dry_run_validates_everything_with_zero_problems():
    problems = validate_everything(TASKS_ROOT, PROVING_GROUND_ROOT.parent, MODEL_IDS)
    assert problems == []


def test_resolve_task_ids_all_expands_to_every_task():
    ids = resolve_task_ids(TASKS_ROOT, ["all"])
    assert len(ids) >= 10
    assert "01-bug-average-empty-list" in ids


def test_resolve_task_ids_rejects_unknown_id():
    try:
        resolve_task_ids(TASKS_ROOT, ["not-a-real-task"])
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "unknown task id" in str(exc)


def test_manifest_id_must_match_directory_name(tmp_path):
    task_dir = tmp_path / "01-bug-average-empty-list"
    task_dir.mkdir()
    (task_dir / "manifest.yaml").write_text(
        textwrap.dedent(
            """
            id: "wrong-id"
            title: "x"
            category: bug
            difficulty: easy
            time_budget_minutes: 5
            brief: brief.md
            fixture_dir: fixture
            grader: grader.py
            description: "x"
            pass_criteria: "x"
            """
        )
    )
    (task_dir / "brief.md").write_text("hello")
    (task_dir / "fixture").mkdir()
    (task_dir / "fixture" / "placeholder.txt").write_text("x")
    (task_dir / "grader.py").write_text("def grade(workdir):\n    pass\n")

    try:
        load_manifest(task_dir)
        assert False, "expected ManifestError"
    except ManifestError as exc:
        assert "must match its directory name" in str(exc)


def test_manifest_rejects_invalid_category(tmp_path):
    task_dir = tmp_path / "some-task"
    task_dir.mkdir()
    (task_dir / "manifest.yaml").write_text(
        textwrap.dedent(
            """
            id: "some-task"
            title: "x"
            category: not-a-real-category
            difficulty: easy
            time_budget_minutes: 5
            brief: brief.md
            fixture_dir: fixture
            grader: grader.py
            description: "x"
            pass_criteria: "x"
            """
        )
    )
    (task_dir / "brief.md").write_text("hello")
    (task_dir / "fixture").mkdir()
    (task_dir / "fixture" / "placeholder.txt").write_text("x")
    (task_dir / "grader.py").write_text("def grade(workdir):\n    pass\n")

    try:
        load_manifest(task_dir)
        assert False, "expected ManifestError"
    except ManifestError as exc:
        assert "category" in str(exc)


def test_manifest_rejects_answer_key_inside_fixture_dir(tmp_path):
    task_dir = tmp_path / "some-task"
    task_dir.mkdir()
    (task_dir / "manifest.yaml").write_text(
        textwrap.dedent(
            """
            id: "some-task"
            title: "x"
            category: research
            difficulty: easy
            time_budget_minutes: 5
            brief: brief.md
            fixture_dir: fixture
            grader: grader.py
            description: "x"
            pass_criteria: "x"
            answer_key: fixture/answer_key.json
            """
        )
    )
    (task_dir / "brief.md").write_text("hello")
    (task_dir / "fixture").mkdir()
    (task_dir / "fixture" / "answer_key.json").write_text("{}")
    (task_dir / "grader.py").write_text("def grade(workdir):\n    pass\n")

    try:
        load_manifest(task_dir)
        assert False, "expected ManifestError"
    except ManifestError as exc:
        assert "must NOT live inside fixture_dir" in str(exc)
