"""Shared dataclasses for the proving-ground harness.

Kept in their own module (rather than inside `manifest.py` or `grading.py`)
so every other module can import them without a circular-import risk.

`from __future__ import annotations` is load-bearing here, not decorative:
it defers evaluation of type annotations to strings, which is what lets us
use `list[str]` / `Optional[X]`-style hints while staying importable on
Python 3.9 (this repo's declared floor — see `pyproject.toml` and the CI
matrix in `.github/workflows/ci.yml`) without ever calling
`typing.get_type_hints()` at runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class GradeResult:
    """The one and only return shape every grader in this harness produces.

    `passed` is the sole deterministic signal `run.py` and `grade.py` act on.
    `reason` must be a short, human-readable, model-independent explanation
    (it is printed verbatim in reports and logs — never leave it blank).
    `detail` is free-form structured evidence (e.g. pytest output, a diff of
    expected vs. actual answers) for a human auditing a surprising result.
    """

    passed: bool
    reason: str
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"passed": self.passed, "reason": self.reason, "detail": self.detail}


@dataclass
class Manifest:
    """A parsed, already-validated `tasks/<id>/manifest.yaml`.

    Field meanings are documented in `tasks/README.md` (the manifest
    contract) — this dataclass intentionally carries no logic beyond path
    helpers so it stays a plain, inspectable record.
    """

    task_dir: Path
    id: str
    title: str
    category: str
    difficulty: str
    time_budget_minutes: int
    tags: List[str]
    brief: str
    fixture_dir: str
    grader: str
    grader_entrypoint: str
    description: str
    pass_criteria: str
    planted_trap: bool
    protected_paths: List[str]
    hidden_tests: List[str]
    answer_key: Optional[str]

    @property
    def brief_path(self) -> Path:
        return self.task_dir / self.brief

    @property
    def fixture_path(self) -> Path:
        return self.task_dir / self.fixture_dir

    @property
    def grader_path(self) -> Path:
        return self.task_dir / self.grader

    @property
    def answer_key_path(self) -> Optional[Path]:
        return (self.task_dir / self.answer_key) if self.answer_key else None

    def hidden_test_paths(self) -> List[Path]:
        return [self.task_dir / name for name in self.hidden_tests]
