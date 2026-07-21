"""Unit-test the graders for the three feature-vs-spec tasks (03, 04, 10)
against hand-crafted fixtures: the shipped stub must FAIL (it raises
NotImplementedError), a correct implementation must PASS, and a plausible
but wrong implementation must FAIL.
"""
from __future__ import annotations

from pg_lib.grading import grade_task

RATELIMITER_CORRECT = """
class TokenBucket:
    def __init__(self, capacity, refill_rate_per_sec):
        self.capacity = capacity
        self.refill_rate_per_sec = refill_rate_per_sec
        self.tokens = capacity
        self.last_update = None

    def allow(self, tokens=1, now=None):
        if self.last_update is not None:
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate_per_sec)
        self.last_update = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
"""

RATELIMITER_WRONG_NO_CAP = """
class TokenBucket:
    def __init__(self, capacity, refill_rate_per_sec):
        self.capacity = capacity
        self.refill_rate_per_sec = refill_rate_per_sec
        self.tokens = capacity
        self.last_update = 0.0

    def allow(self, tokens=1, now=None):
        elapsed = now - self.last_update
        self.tokens = self.tokens + elapsed * self.refill_rate_per_sec  # BUG: never capped
        self.last_update = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
"""


def test_03_shipped_stub_fails_grading(stage_task):
    manifest, workdir = stage_task("03-feature-token-bucket-ratelimiter")
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_03_correct_implementation_passes_grading(stage_task):
    manifest, workdir = stage_task("03-feature-token-bucket-ratelimiter")
    (workdir / "ratelimiter.py").write_text(RATELIMITER_CORRECT)
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason


def test_03_uncapped_refill_fails_grading(stage_task):
    manifest, workdir = stage_task("03-feature-token-bucket-ratelimiter")
    (workdir / "ratelimiter.py").write_text(RATELIMITER_WRONG_NO_CAP)
    result = grade_task(manifest, workdir)
    assert result.passed is False


DEDUPE_CORRECT = """
def dedupe_rows(rows, key_fields):
    seen = set()
    out = []
    for row in rows:
        key = tuple(row.get(f) for f in key_fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(row))
    return out
"""

DEDUPE_WRONG_KEEPS_LAST = """
def dedupe_rows(rows, key_fields):
    by_key = {}
    for row in rows:
        key = tuple(row.get(f) for f in key_fields)
        by_key[key] = dict(row)  # BUG: keeps the LAST occurrence, spec wants the first
    return list(by_key.values())
"""


def test_04_shipped_stub_fails_grading(stage_task):
    manifest, workdir = stage_task("04-feature-csv-dedupe")
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_04_correct_implementation_passes_grading(stage_task):
    manifest, workdir = stage_task("04-feature-csv-dedupe")
    (workdir / "dedupe.py").write_text(DEDUPE_CORRECT)
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason


def test_04_keeps_last_instead_of_first_fails_grading(stage_task):
    manifest, workdir = stage_task("04-feature-csv-dedupe")
    (workdir / "dedupe.py").write_text(DEDUPE_WRONG_KEEPS_LAST)
    result = grade_task(manifest, workdir)
    assert result.passed is False


PAGINATION_CORRECT = """
import math

def paginate_response(items, page, page_size):
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    total = len(items)
    start = page * page_size
    end = start + page_size
    page_items = items[start:end]
    total_pages = math.ceil(total / page_size) if total else 0
    return {
        "items": page_items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": end < total,
        "has_prev": page > 0,
    }
"""

PAGINATION_WRONG_NO_VALIDATION = """
import math

def paginate_response(items, page, page_size):
    total = len(items)
    start = page * page_size
    end = start + page_size
    page_items = items[start:end]
    total_pages = math.ceil(total / page_size) if total and page_size > 0 else 0
    return {
        "items": page_items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": end < total,
        "has_prev": page > 0,
    }
"""


def test_10_shipped_stub_fails_grading(stage_task):
    manifest, workdir = stage_task("10-feature-pagination-contract")
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_10_correct_implementation_passes_grading(stage_task):
    manifest, workdir = stage_task("10-feature-pagination-contract")
    (workdir / "pagination_contract.py").write_text(PAGINATION_CORRECT)
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason


def test_10_missing_validation_fails_on_held_out_case(stage_task):
    manifest, workdir = stage_task("10-feature-pagination-contract")
    (workdir / "pagination_contract.py").write_text(PAGINATION_WRONG_NO_VALIDATION)
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_10_editing_contract_json_fails_even_with_a_correct_implementation(stage_task):
    manifest, workdir = stage_task("10-feature-pagination-contract")
    (workdir / "pagination_contract.py").write_text(PAGINATION_CORRECT)
    (workdir / "contract.json").write_text("{}")
    result = grade_task(manifest, workdir)
    assert result.passed is False
    assert "protected" in result.reason.lower()
