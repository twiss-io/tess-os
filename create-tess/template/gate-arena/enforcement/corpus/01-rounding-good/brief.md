# Bug report: `round_currency` rounds invoice line items incorrectly

`round_currency(amount, cents=2)` is used to round invoice line items
before display/charging. QA reports: `round_currency(2.675)` returns
`2.67`, but the finance team's rounding convention is HALF-UP (0.5 always
rounds away from zero) — `2.675` should round to `2.68`. Same class of bug
at `round_currency(2.005)` (should be `2.01`, not `2.00`).

**Fix `round_currency` so it rounds HALF-UP, not banker's-rounding, and is
not vulnerable to binary float representation error at the boundary.**

Acceptance: `round_currency(2.675) == 2.68`, `round_currency(2.005) ==
2.01`, `round_currency(1.005) == 1.01`, `round_currency(-2.005) == -2.01`.
