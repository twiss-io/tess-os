from decimal import Decimal, ROUND_HALF_UP


def round_currency(amount, cents=2):
    quantum = Decimal('1').scaleb(-cents)
    # Route through str(amount) first — Decimal(float) reproduces the
    # float's exact binary value (e.g. Decimal(2.675) == 2.67499999...),
    # which silently reintroduces the same rounding-boundary bug this fix
    # exists to close.
    return float(Decimal(str(amount)).quantize(quantum, rounding=ROUND_HALF_UP))
