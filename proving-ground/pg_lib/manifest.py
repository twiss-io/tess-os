"""Load + validate `tasks/<id>/manifest.yaml`.

Deliberately dependency-free beyond PyYAML (already a repo requirement —
see `requirements-dev.txt`): no `jsonschema` package. This mirrors the house
style `tessctl validate` already established for the framework's own
contracts (`core/contracts/README.md`: "a dependency-free validator") — a
hand-rolled required-fields + type + enum checker, not a second validation
philosophy invented for this subsystem.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

from pg_lib.types import Manifest

VALID_CATEGORIES = {"bug", "feature", "research", "trap"}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}

REQUIRED_STRING_FIELDS = (
    "id",
    "title",
    "category",
    "difficulty",
    "brief",
    "fixture_dir",
    "grader",
    "description",
    "pass_criteria",
)


class ManifestError(ValueError):
    """Raised when a task manifest fails structural or referential validation."""


def load_manifest(task_dir: Path) -> Manifest:
    """Parse and fully validate one task's manifest.yaml.

    Raises `ManifestError` (never returns a half-valid Manifest) so callers
    can treat "manifest loaded" as "manifest is trustworthy" — the same
    fail-closed posture the framework's own `tessctl validate` takes on a
    schema-miss.
    """
    manifest_path = task_dir / "manifest.yaml"
    if not manifest_path.is_file():
        raise ManifestError(f"{task_dir.name}: manifest.yaml not found at {manifest_path}")

    try:
        with manifest_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise ManifestError(f"{task_dir.name}: manifest.yaml is not valid YAML — {exc}") from exc

    if not isinstance(data, dict):
        raise ManifestError(f"{task_dir.name}: manifest.yaml must parse to a mapping, got {type(data).__name__}")

    errors = _collect_errors(data, task_dir)
    if errors:
        joined = "; ".join(errors)
        raise ManifestError(f"{task_dir.name}: {joined}")

    return _build_manifest(data, task_dir)


def _collect_errors(data: Dict[str, Any], task_dir: Path) -> List[str]:
    errors: List[str] = []
    errors += _check_required_fields(data)
    if errors:
        # Referential/enum checks below assume the required fields exist —
        # bail out early rather than raising confusing KeyErrors.
        return errors
    errors += _check_id_matches_dirname(data, task_dir)
    errors += _check_enums(data)
    errors += _check_time_budget(data)
    errors += _check_referenced_paths(data, task_dir)
    errors += _check_answer_key_not_in_fixture(data, task_dir)
    errors += _check_hidden_tests_not_in_fixture(data, task_dir)
    return errors


def _check_required_fields(data: Dict[str, Any]) -> List[str]:
    errors = []
    for field_name in REQUIRED_STRING_FIELDS:
        value = data.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"missing or empty required string field '{field_name}'")
    return errors


def _check_id_matches_dirname(data: Dict[str, Any], task_dir: Path) -> List[str]:
    if data["id"] != task_dir.name:
        return [f"manifest 'id' ({data['id']!r}) must match its directory name ({task_dir.name!r})"]
    return []


def _check_enums(data: Dict[str, Any]) -> List[str]:
    errors = []
    if data["category"] not in VALID_CATEGORIES:
        errors.append(f"'category' must be one of {sorted(VALID_CATEGORIES)}, got {data['category']!r}")
    if data["difficulty"] not in VALID_DIFFICULTIES:
        errors.append(f"'difficulty' must be one of {sorted(VALID_DIFFICULTIES)}, got {data['difficulty']!r}")
    return errors


def _check_time_budget(data: Dict[str, Any]) -> List[str]:
    budget = data.get("time_budget_minutes")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
        return [f"'time_budget_minutes' must be a positive integer, got {budget!r}"]
    return []


def _check_referenced_paths(data: Dict[str, Any], task_dir: Path) -> List[str]:
    errors = []
    brief_path = task_dir / data["brief"]
    if not brief_path.is_file():
        errors.append(f"'brief' file not found: {brief_path}")
    elif not brief_path.read_text(encoding="utf-8").strip():
        errors.append(f"'brief' file is empty: {brief_path}")

    fixture_path = task_dir / data["fixture_dir"]
    if not fixture_path.is_dir():
        errors.append(f"'fixture_dir' not found or not a directory: {fixture_path}")
    elif not any(fixture_path.iterdir()):
        errors.append(f"'fixture_dir' is empty: {fixture_path}")

    grader_path = task_dir / data["grader"]
    if not grader_path.is_file():
        errors.append(f"'grader' file not found: {grader_path}")

    return errors


def _check_answer_key_not_in_fixture(data: Dict[str, Any], task_dir: Path) -> List[str]:
    answer_key = data.get("answer_key")
    if not answer_key:
        return []
    answer_key_path = task_dir / answer_key
    if not answer_key_path.is_file():
        return [f"'answer_key' file not found: {answer_key_path}"]
    fixture_path = task_dir / data["fixture_dir"]
    if _is_within(answer_key_path, fixture_path):
        return [f"'answer_key' ({answer_key}) must NOT live inside fixture_dir — it would leak to the agent"]
    return []


def _check_hidden_tests_not_in_fixture(data: Dict[str, Any], task_dir: Path) -> List[str]:
    hidden_tests = data.get("hidden_tests") or []
    fixture_path = task_dir / data["fixture_dir"]
    errors = []
    for name in hidden_tests:
        hidden_path = task_dir / name
        if not hidden_path.is_file():
            errors.append(f"'hidden_tests' entry not found: {hidden_path}")
        elif _is_within(hidden_path, fixture_path):
            errors.append(f"'hidden_tests' entry ({name}) must NOT live inside fixture_dir — it would leak to the agent")
    return errors


def _is_within(path: Path, ancestor: Path) -> bool:
    try:
        path.resolve().relative_to(ancestor.resolve())
        return True
    except ValueError:
        return False


def _build_manifest(data: Dict[str, Any], task_dir: Path) -> Manifest:
    return Manifest(
        task_dir=task_dir,
        id=data["id"],
        title=data["title"],
        category=data["category"],
        difficulty=data["difficulty"],
        time_budget_minutes=int(data["time_budget_minutes"]),
        tags=list(data.get("tags") or []),
        brief=data["brief"],
        fixture_dir=data["fixture_dir"],
        grader=data["grader"],
        grader_entrypoint=str(data.get("grader_entrypoint") or "grade"),
        description=data["description"],
        pass_criteria=data["pass_criteria"],
        planted_trap=bool(data.get("planted_trap", False)),
        protected_paths=list(data.get("protected_paths") or []),
        hidden_tests=list(data.get("hidden_tests") or []),
        answer_key=data.get("answer_key"),
    )
