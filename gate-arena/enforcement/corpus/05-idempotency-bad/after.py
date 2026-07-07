CHARGES = {}
IDEMPOTENCY_INDEX = {}


def charge_customer(customer_id, amount_cents, idempotency_key):
    # Looks like a fix (adds an idempotency index) but keys it by
    # customer_id instead of idempotency_key. A genuinely NEW, different
    # purchase by the same customer (different idempotency_key, different
    # amount) is now silently treated as a duplicate of the FIRST charge
    # and never actually charged — a different, equally serious bug
    # (revenue loss / silently dropped legitimate charges).
    if customer_id in IDEMPOTENCY_INDEX:
        return IDEMPOTENCY_INDEX[customer_id]
    charge_id = f"ch_{len(CHARGES) + 1}"
    CHARGES[charge_id] = {"customer_id": customer_id, "amount_cents": amount_cents}
    IDEMPOTENCY_INDEX[customer_id] = charge_id
    return charge_id
