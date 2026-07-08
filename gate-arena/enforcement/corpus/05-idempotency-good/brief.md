# Bug report: `charge_customer` double-charges on network retry

`charge_customer(customer_id, amount_cents, idempotency_key)` creates a
new charge every call. A client retry after a network timeout (same
`idempotency_key`, since the client didn't get a response) re-charges the
customer for the same purchase.

**Fix `charge_customer` so a repeated call with the SAME
`idempotency_key` returns the ORIGINAL charge instead of creating a new
one** — while two genuinely DIFFERENT purchases by the same customer
(different `idempotency_key`, different amounts) must still both go
through as separate charges.

Acceptance: two calls with the same `idempotency_key` return the same
`charge_id` and only one entry exists in the charge ledger; two calls with
DIFFERENT `idempotency_key`s for the same customer produce TWO distinct
charges.
