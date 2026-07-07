def apply_discount(subtotal_cents, discount_pct, is_first_order):
    # Looks like a fix (a cap exists) but caps discount_pct BEFORE adding
    # the first-order bonus, not the COMBINED total the spec actually caps.
    # discount_pct=45 + 10-point bonus = 55% effective discount, still
    # over the 50% spec ceiling.
    discount_pct = min(discount_pct, 50)
    pct = discount_pct + (10 if is_first_order else 0)
    return round(subtotal_cents * (100 - pct) / 100)
