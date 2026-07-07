from money import round_currency


def test_rounds_down_when_below_half():
    assert round_currency(3.14159, 2) == 3.14


def test_rounds_up_when_above_half():
    assert round_currency(2.71828, 2) == 2.72


def test_whole_number_stays_whole():
    assert round_currency(10.0, 2) == 10.0


def test_default_ndigits_is_two():
    assert round_currency(1.239) == 1.24
