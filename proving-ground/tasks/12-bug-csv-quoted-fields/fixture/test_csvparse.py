from csvparse import parse_fields


def test_plain_row():
    assert parse_fields("a,b,c") == ["a", "b", "c"]


def test_header_row():
    assert parse_fields("name,age,city") == ["name", "age", "city"]


def test_empty_middle_field():
    assert parse_fields("p,,q") == ["p", "", "q"]


def test_single_field():
    assert parse_fields("solo") == ["solo"]
