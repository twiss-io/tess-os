# Implement a token-bucket rate limiter

`ratelimiter.py` contains a `TokenBucket` class stub. Implement it exactly
to the following spec. Your implementation will be graded against a
private test suite you will not see — read the spec carefully rather than
guessing at "reasonable" behavior.

## Spec

`TokenBucket(capacity, refill_rate_per_sec)`

- `capacity` (number): the maximum number of tokens the bucket can hold.
- `refill_rate_per_sec` (number): tokens added per second of elapsed time.
- The bucket **starts full** (at `capacity` tokens).

`allow(tokens=1, now=None) -> bool`

- `now` (number, required in practice — pass an explicit float clock value
  every call in tests; never rely on wall-clock time): the current time,
  in seconds, on whatever monotonic clock the caller uses.
- Before checking anything, refill the bucket: compute elapsed time since
  the bucket's last update (0 on the very first call) and add
  `elapsed * refill_rate_per_sec` tokens, **capped at `capacity`** — the
  bucket must never hold more than `capacity` tokens, no matter how much
  time has elapsed.
- If the bucket then holds at least `tokens` tokens: subtract `tokens` from
  the bucket, return `True`.
- Otherwise: return `False` **and do not subtract any tokens** — a denied
  request must leave the bucket's token count exactly as it was after the
  refill step above.
- A request for more tokens than `capacity` can ever hold must always
  return `False`, regardless of how much time has elapsed.

## Constraints

- Do not change the class name (`TokenBucket`) or the constructor / method
  signatures.
- No external dependencies — standard library only.
- Do not use real wall-clock time (`time.time()`, `time.monotonic()`)
  internally to decide refill amounts — always use the `now` value passed
  in, so behavior is fully deterministic and testable.
