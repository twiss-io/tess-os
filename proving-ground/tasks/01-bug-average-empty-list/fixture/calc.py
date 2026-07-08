def average(values):
    """Return the arithmetic mean of `values`.

    BUG: raises ZeroDivisionError when `values` is empty. Should return 0.0.
    """
    return sum(values) / len(values)
