# Apply a percentage discount (discount.py)

Implement `apply_discount(price_cents, discount_percent)` in `discount.py`.

- `price_cents` is a non-negative integer number of cents.
- `discount_percent` is the percentage to take off. It may be an `int` or a
  `float`.

Return the discounted price, subject to **all** of these rules:

1. The discounted price is `price_cents` reduced by `discount_percent`
   percent.
2. **Round the result DOWN to the nearest whole cent** (floor). Never round
   up and never round-half — always toward zero-remainder. For example a
   result of `666.65` cents becomes `666`, not `667`.
3. **Return an `int`** — a whole number of cents, not a float.
4. If `discount_percent` is **less than 0 or greater than 100**, raise
   `ValueError`. A discount of exactly `0` returns the price unchanged; a
   discount of exactly `100` returns `0`.

Examples:

```
apply_discount(1000, 10)  -> 900
apply_discount(2000, 25)  -> 1500
```

Constraints:
- Keep the signature `apply_discount(price_cents, discount_percent)`.
- Standard library only.
