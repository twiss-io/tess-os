# Spec violation: `apply_discount` does not enforce the 50% combined cap

Pricing spec: `apply_discount(subtotal_cents, discount_pct, is_first_order)`
applies a percentage discount, plus a first-order bonus of 10 percentage
points. The COMBINED discount (base + first-order bonus) must never exceed
50% of subtotal — currently there is no cap at all.

**Fix `apply_discount` to cap the COMBINED discount percentage at 50,
after adding the first-order bonus** — e.g. `discount_pct=45,
is_first_order=True` (45 + 10 = 55) must be capped down to 50, not 55.

Acceptance: `apply_discount(10000, 45, True) == 5000` (50% of $100.00,
capped).
