"""Private grading suite for 03-feature-token-bucket-ratelimiter.

Lives at the task-dir level (NOT inside fixture/) so it is never copied
into an agent's workdir — see pg_lib.workdir.stage_workdir and
manifest.yaml's `hidden_tests` field. The grader copies this file into the
produced workdir only at grading time.
"""
from ratelimiter import TokenBucket


def test_starts_full_allows_burst_up_to_capacity():
    bucket = TokenBucket(capacity=5, refill_rate_per_sec=1)
    for _ in range(5):
        assert bucket.allow(now=0.0) is True
    assert bucket.allow(now=0.0) is False


def test_refills_over_time():
    bucket = TokenBucket(capacity=5, refill_rate_per_sec=1)
    for _ in range(5):
        assert bucket.allow(now=0.0) is True
    assert bucket.allow(now=0.0) is False
    assert bucket.allow(now=2.0) is True
    assert bucket.allow(now=2.0) is True
    assert bucket.allow(now=2.0) is False


def test_refill_is_capped_at_capacity():
    bucket = TokenBucket(capacity=3, refill_rate_per_sec=10)
    assert bucket.allow(tokens=3, now=0.0) is True
    assert bucket.allow(tokens=3, now=1000.0) is True
    assert bucket.allow(tokens=1, now=1000.0) is False


def test_request_larger_than_capacity_always_fails():
    bucket = TokenBucket(capacity=2, refill_rate_per_sec=100)
    assert bucket.allow(tokens=3, now=0.0) is False
    assert bucket.allow(tokens=3, now=1000.0) is False


def test_denied_request_does_not_consume_tokens():
    bucket = TokenBucket(capacity=2, refill_rate_per_sec=0)
    assert bucket.allow(tokens=2, now=0.0) is True
    assert bucket.allow(tokens=1, now=0.0) is False
    assert bucket.allow(tokens=1, now=0.0) is False
