"""Unit-test the graders for the harder feature/spec tasks (13 anchored
code match, 14 case-insensitive dedupe, 19 discount spec). For each: the
plausible-but-wrong implementation must FAIL, a correct one must PASS, and
a no-op/hardcode cheat must FAIL.
"""
from __future__ import annotations

from pg_lib.grading import grade_task

# ---------------------------------------------------------------------------
# 13 — anchored exact 4-digit match
# ---------------------------------------------------------------------------

CODE_CORRECT = '''
import re
_R = re.compile(r"[0-9]{4}")

def is_valid_code(s):
    return _R.fullmatch(s) is not None
'''

CODE_NAIVE_MATCH = '''
import re

def is_valid_code(s):
    return re.match(r"\\d{4}$", s) is not None  # $ matches before a trailing newline -> accepts "1234\\n"
'''

CODE_ALWAYS_TRUE = '''
def is_valid_code(s):
    return True
'''


def test_13_naive_re_match_dollar_anchor_fails(stage_task):
    manifest, workdir = stage_task("13-feature-code-exact-match")
    (workdir / "codes.py").write_text(CODE_NAIVE_MATCH)
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_13_correct_fullmatch_passes(stage_task):
    manifest, workdir = stage_task("13-feature-code-exact-match")
    (workdir / "codes.py").write_text(CODE_CORRECT)
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason


def test_13_always_true_cheat_fails(stage_task):
    manifest, workdir = stage_task("13-feature-code-exact-match")
    (workdir / "codes.py").write_text(CODE_ALWAYS_TRUE)
    result = grade_task(manifest, workdir)
    assert result.passed is False


# ---------------------------------------------------------------------------
# 14 — case-insensitive, order-preserving, first-casing dedupe
# ---------------------------------------------------------------------------

DEDUPE_CORRECT = '''
def dedupe_emails(emails):
    seen = set()
    out = []
    for e in emails:
        k = e.lower()
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out
'''

DEDUPE_CASE_SENSITIVE = '''
def dedupe_emails(emails):
    return list(dict.fromkeys(emails))  # case-SENSITIVE — keeps Bob@X and bob@x
'''

DEDUPE_SET = '''
def dedupe_emails(emails):
    return list(set(emails))  # loses order (and case-sensitive)
'''

DEDUPE_LOWER = '''
def dedupe_emails(emails):
    seen = set()
    out = []
    for e in emails:
        k = e.lower()
        if k not in seen:
            seen.add(k)
            out.append(k)  # destroys original casing
    return out
'''


def test_14_case_sensitive_dedupe_fails(stage_task):
    manifest, workdir = stage_task("14-feature-dedupe-case-insensitive")
    (workdir / "dedupe.py").write_text(DEDUPE_CASE_SENSITIVE)
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_14_set_based_dedupe_fails(stage_task):
    manifest, workdir = stage_task("14-feature-dedupe-case-insensitive")
    (workdir / "dedupe.py").write_text(DEDUPE_SET)
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_14_lowercasing_output_fails(stage_task):
    manifest, workdir = stage_task("14-feature-dedupe-case-insensitive")
    (workdir / "dedupe.py").write_text(DEDUPE_LOWER)
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_14_correct_passes(stage_task):
    manifest, workdir = stage_task("14-feature-dedupe-case-insensitive")
    (workdir / "dedupe.py").write_text(DEDUPE_CORRECT)
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason


# ---------------------------------------------------------------------------
# 19 — discount: floor rounding, int return, range validation
# ---------------------------------------------------------------------------

DISCOUNT_CORRECT = '''
import math

def apply_discount(price_cents, discount_percent):
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError("discount_percent out of range")
    return math.floor(price_cents * (100 - discount_percent) / 100)
'''

DISCOUNT_NAIVE = '''
def apply_discount(price_cents, discount_percent):
    return round(price_cents * (1 - discount_percent / 100))  # round not floor, no validation
'''

DISCOUNT_NO_VALIDATION_FLOAT = '''
def apply_discount(price_cents, discount_percent):
    return price_cents * (1 - discount_percent / 100)  # float, no floor, no validation
'''


def test_19_naive_round_no_validation_fails(stage_task):
    manifest, workdir = stage_task("19-feature-discount-spec")
    (workdir / "discount.py").write_text(DISCOUNT_NAIVE)
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_19_float_no_validation_fails(stage_task):
    manifest, workdir = stage_task("19-feature-discount-spec")
    (workdir / "discount.py").write_text(DISCOUNT_NO_VALIDATION_FLOAT)
    result = grade_task(manifest, workdir)
    assert result.passed is False


def test_19_correct_passes(stage_task):
    manifest, workdir = stage_task("19-feature-discount-spec")
    (workdir / "discount.py").write_text(DISCOUNT_CORRECT)
    result = grade_task(manifest, workdir)
    assert result.passed is True, result.reason
