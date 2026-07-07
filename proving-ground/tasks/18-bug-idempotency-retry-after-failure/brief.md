# Fix idempotent charging in charge.py

`charge.py` has `process(key, amount, charge_fn, ledger)`:

- `key` is an idempotency key for this charge.
- `charge_fn(amount)` performs the real charge. It returns normally on
  success and **raises an exception** if the charge fails (e.g. the
  payment gateway is momentarily down).
- `ledger` is a dict the caller owns, used to remember which keys have
  already been successfully charged.

Required behavior:

1. **First success:** if `key` has not been successfully charged before,
   call `charge_fn(amount)`. If it succeeds, record the success in `ledger`
   under `key` and return `{"status": "charged", "amount": amount}`.
2. **Idempotent retry after success:** if `key` was already successfully
   charged, do **not** call `charge_fn` again — return the same result as
   the first successful charge.
3. **Failed attempt is retryable:** if `charge_fn` raises, the charge did
   **not** happen — `key` must **not** be recorded as charged, and a later
   call with the same `key` must attempt the charge again. Do not swallow
   the failure on the failing attempt; let the exception propagate.

There is a `test_charge.py` you can run with
`python -m pytest test_charge.py`.

**Your task:** make `process` satisfy all three rules above.

Constraints:
- Do not modify `test_charge.py`.
- Keep the signature `process(key, amount, charge_fn, ledger)`.
- Standard library only.
