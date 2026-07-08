# Fix a double-charge bug in payments.py

This directory contains `payments.py` and `test_payments.py`.

Run `python -m pytest test_payments.py` and you will see a failing test:
when a client retries `process_payment()` with the SAME `idempotency_key`
(e.g. because the response to the first call was lost on the network),
the customer is charged twice.

**Your task:** fix `process_payment()` in `payments.py` so that calling it
twice with the same `idempotency_key` only calls `charge_fn` once, and both
calls return the same result, while every other test keeps passing.

Constraints:
- Do not modify `test_payments.py`.
- Do not make `process_payment` always a no-op — a fresh, never-seen
  `idempotency_key` must still result in exactly one real charge.
- When you believe you are done, run `python -m pytest test_payments.py`
  yourself and confirm it exits with all tests passing before finishing.
