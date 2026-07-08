import sys
sys.path.insert(0, '.')
from after import apply_discount

def test_combined_discount_capped_at_50_pct():
    result = apply_discount(10000, 45, True)
    assert result == 5000, f"got {result}, expected 5000 (50% cap, not 45%+10%=55%)"
