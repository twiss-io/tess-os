# Fix currency rounding in money.py

`money.py` contains `round_currency(amount, ndigits=2)`. It is supposed to
round a monetary amount to `ndigits` decimal places using the rule banks
and invoices use for money:

- **Round half away from zero.** When the value is exactly halfway between
  two representable amounts, round to the one with the larger magnitude.
  So `0.5 -> 1`, `2.5 -> 3`, `0.125 -> 0.13` (at 2 dp), and for negatives
  `-0.5 -> -1`, `-2.5 -> -3`.
- Non-halfway values round to the nearest representable amount as usual.
- `ndigits` is the number of decimal places to keep (default 2). It can be
  0 (round to a whole number) or more.

There is a `test_money.py` in this directory. You can run
`python -m pytest test_money.py`.

**Your task:** make `round_currency` correct per the rule above.

Constraints:
- Do not modify `test_money.py`.
- Keep the signature `round_currency(amount, ndigits=2)`.
- Standard library only.
