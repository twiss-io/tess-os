from calc import average


def test_average_basic():
    assert average([1, 2, 3]) == 2


def test_average_single_value():
    assert average([5]) == 5


def test_average_negative_numbers():
    assert average([-2, 2]) == 0


def test_average_empty_returns_zero():
    assert average([]) == 0.0
