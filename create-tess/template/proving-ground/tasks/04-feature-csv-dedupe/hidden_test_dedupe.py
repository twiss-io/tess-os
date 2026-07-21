"""Private grading suite for 04-feature-csv-dedupe. Not shipped in fixture/."""
from dedupe import dedupe_rows


def test_keeps_first_occurrence_in_order():
    rows = [
        {"email": "a@x.com", "region": "sg", "name": "Ann v1"},
        {"email": "b@x.com", "region": "sg", "name": "Bo"},
        {"email": "a@x.com", "region": "sg", "name": "Ann v2 (dup, should be dropped)"},
        {"email": "a@x.com", "region": "us", "name": "Ann US (different region, keep)"},
    ]
    result = dedupe_rows(rows, key_fields=["email", "region"])
    assert result == [
        {"email": "a@x.com", "region": "sg", "name": "Ann v1"},
        {"email": "b@x.com", "region": "sg", "name": "Bo"},
        {"email": "a@x.com", "region": "us", "name": "Ann US (different region, keep)"},
    ]


def test_single_key_field():
    rows = [
        {"sku": "A1", "qty": 3},
        {"sku": "A1", "qty": 5},
        {"sku": "B2", "qty": 1},
    ]
    result = dedupe_rows(rows, key_fields=["sku"])
    assert result == [{"sku": "A1", "qty": 3}, {"sku": "B2", "qty": 1}]


def test_empty_input_returns_empty():
    assert dedupe_rows([], key_fields=["id"]) == []


def test_missing_key_field_treated_as_none_not_an_exception():
    rows = [
        {"id": 1},
        {"id": 1, "extra": "ignored"},  # same composite key (missing 'region' both times) -> dup
        {"id": 2, "region": "sg"},
    ]
    result = dedupe_rows(rows, key_fields=["id", "region"])
    assert result == [{"id": 1}, {"id": 2, "region": "sg"}]


def test_does_not_mutate_input():
    rows = [{"id": 1}, {"id": 1}]
    original_len = len(rows)
    dedupe_rows(rows, key_fields=["id"])
    assert len(rows) == original_len
    assert rows == [{"id": 1}, {"id": 1}]
