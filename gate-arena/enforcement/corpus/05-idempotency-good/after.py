CHARGES = {}
IDEMPOTENCY_INDEX = {}


def charge_customer(customer_id, amount_cents, idempotency_key):
    if idempotency_key in IDEMPOTENCY_INDEX:
        return IDEMPOTENCY_INDEX[idempotency_key]
    charge_id = f"ch_{len(CHARGES) + 1}"
    CHARGES[charge_id] = {"customer_id": customer_id, "amount_cents": amount_cents}
    IDEMPOTENCY_INDEX[idempotency_key] = charge_id
    return charge_id
