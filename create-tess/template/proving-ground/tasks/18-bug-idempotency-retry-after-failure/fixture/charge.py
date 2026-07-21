def process(key, amount, charge_fn, ledger):
    """Charge `amount` under idempotency `key`, remembering charged keys in
    `ledger`.

    BUG: this records the key as charged BEFORE calling charge_fn. If
    charge_fn raises (a transient failure), the key is already stored, so a
    later retry with the same key returns the cached "charged" result
    without ever actually charging. See brief.md for the required behavior,
    including rule 3 (a failed attempt must stay retryable).
    """
    if key in ledger:
        return ledger[key]
    result = {"status": "charged", "amount": amount}
    ledger[key] = result  # BUG: recorded before we know the charge succeeded
    charge_fn(amount)
    return result
