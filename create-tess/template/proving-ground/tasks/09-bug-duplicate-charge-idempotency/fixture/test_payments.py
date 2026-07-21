from payments import process_payment


def test_first_charge_succeeds():
    calls = []
    ledger = {}
    result = process_payment("key-1", 100, lambda amt: calls.append(amt), ledger)
    assert result == {"status": "charged", "amount": 100}
    assert calls == [100]


def test_new_key_is_a_new_charge():
    calls = []
    ledger = {}
    process_payment("key-1", 100, lambda amt: calls.append(amt), ledger)
    process_payment("key-2", 50, lambda amt: calls.append(amt), ledger)
    assert calls == [100, 50]


def test_retry_with_same_key_does_not_double_charge():
    calls = []
    ledger = {}
    first = process_payment("key-1", 100, lambda amt: calls.append(amt), ledger)
    second = process_payment("key-1", 100, lambda amt: calls.append(amt), ledger)
    assert calls == [100]  # charge_fn must be called exactly once across both calls
    assert second == first
