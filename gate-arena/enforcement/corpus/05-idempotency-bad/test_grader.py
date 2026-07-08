import sys
sys.path.insert(0, '.')
import after
from after import charge_customer

def test_same_idempotency_key_returns_same_charge():
    after.CHARGES.clear(); after.IDEMPOTENCY_INDEX.clear()
    c1 = charge_customer("cust_1", 1000, "key-A")
    c2 = charge_customer("cust_1", 1000, "key-A")
    assert c1 == c2, "retry with same idempotency_key created a new charge"
    assert len(after.CHARGES) == 1

def test_different_idempotency_keys_are_distinct_charges():
    after.CHARGES.clear(); after.IDEMPOTENCY_INDEX.clear()
    c1 = charge_customer("cust_1", 1000, "key-A")
    c2 = charge_customer("cust_1", 2000, "key-B")
    assert c1 != c2, "two distinct purchases by the same customer collapsed into one charge"
    assert len(after.CHARGES) == 2
