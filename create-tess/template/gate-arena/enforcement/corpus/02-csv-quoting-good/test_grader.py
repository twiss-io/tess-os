import sys
sys.path.insert(0, '.')
from after import parse_row

def test_quoted_field_with_embedded_comma():
    result = parse_row('a,"b,c",d')
    assert result == ['a', 'b,c', 'd'], f"got {result}"
