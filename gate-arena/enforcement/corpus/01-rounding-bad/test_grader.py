import sys
sys.path.insert(0, '.')
from after import round_currency

def test_half_up_boundary_675():
    assert round_currency(2.675) == 2.68, f"got {round_currency(2.675)}"

def test_half_up_boundary_005():
    assert round_currency(2.005) == 2.01, f"got {round_currency(2.005)}"
    assert round_currency(1.005) == 1.01, f"got {round_currency(1.005)}"

def test_negative_half_up():
    assert round_currency(-2.005) == -2.01, f"got {round_currency(-2.005)}"
