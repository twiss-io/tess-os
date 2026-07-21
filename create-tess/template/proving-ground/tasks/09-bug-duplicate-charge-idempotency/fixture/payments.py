def process_payment(idempotency_key, amount, charge_fn, ledger):
    """Charge `amount` via `charge_fn(amount)` and record the outcome in
    `ledger` (a plain dict the caller owns — keyed by idempotency_key).

    BUG: calls `charge_fn` every time, even when `idempotency_key` is
    already present in `ledger` from a previous, already-completed call —
    a client retry (same key, e.g. because the first response was lost on
    the network) charges the customer a second time.
    """
    charge_fn(amount)
    result = {"status": "charged", "amount": amount}
    ledger[idempotency_key] = result
    return result
