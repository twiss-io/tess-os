def round_currency(amount, ndigits=2):
    """Round a monetary `amount` to `ndigits` decimal places.

    BUG: Python's built-in round() uses banker's rounding (round-half-to-
    even), so round_currency(2.5, 0) returns 2.0 and round_currency(0.125,
    2) returns 0.12 — both wrong for money, which must round halves away
    from zero (2.5 -> 3, 0.125 -> 0.13). See brief.md for the exact rule.
    """
    return round(amount, ndigits)
