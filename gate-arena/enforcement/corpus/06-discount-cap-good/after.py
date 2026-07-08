def apply_discount(subtotal_cents, discount_pct, is_first_order):
    pct = discount_pct + (10 if is_first_order else 0)
    pct = min(pct, 50)
    return round(subtotal_cents * (100 - pct) / 100)
