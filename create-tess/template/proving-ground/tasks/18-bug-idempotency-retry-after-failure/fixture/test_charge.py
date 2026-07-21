from charge import process


def test_first_charge_calls_charge_fn_once():
    calls = []
    ledger = {}
    result = process("k1", 100, lambda a: calls.append(a), ledger)
    assert result == {"status": "charged", "amount": 100}
    assert calls == [100]


def test_repeat_same_key_does_not_double_charge():
    calls = []
    ledger = {}
    first = process("k1", 100, lambda a: calls.append(a), ledger)
    second = process("k1", 100, lambda a: calls.append(a), ledger)
    assert calls == [100]
    assert second == first


def test_distinct_keys_each_charge():
    calls = []
    ledger = {}
    process("k1", 100, lambda a: calls.append(a), ledger)
    process("k2", 50, lambda a: calls.append(a), ledger)
    assert calls == [100, 50]
