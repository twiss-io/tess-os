CHARGES = {}


def charge_customer(customer_id, amount_cents, idempotency_key):
    charge_id = f"ch_{len(CHARGES) + 1}"
    CHARGES[charge_id] = {"customer_id": customer_id, "amount_cents": amount_cents}
    return charge_id
