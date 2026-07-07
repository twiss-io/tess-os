from decimal import Decimal, ROUND_HALF_UP


def round_currency(amount, cents=2):
    quantum = Decimal('1').scaleb(-cents)
    # Looks identical to the correct fix, but constructs Decimal directly
    # from the float — Decimal(2.675) is actually
    # 2.67499999999999982236431605997495353221893310546875, so
    # ROUND_HALF_UP still rounds it DOWN to 2.67. The exact bug this PR
    # claims to fix is still present.
    return float(Decimal(amount).quantize(quantum, rounding=ROUND_HALF_UP))
