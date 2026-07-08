class TokenBucket:
    """A token-bucket rate limiter. See brief.md in this task for the
    full, authoritative spec — implement exactly to it."""

    def __init__(self, capacity, refill_rate_per_sec):
        raise NotImplementedError

    def allow(self, tokens=1, now=None):
        raise NotImplementedError
