from paginate import paginate

ITEMS = list(range(10))  # [0, 1, ..., 9]


def test_first_page():
    assert paginate(ITEMS, page=0, page_size=3) == [0, 1, 2]


def test_second_page():
    assert paginate(ITEMS, page=1, page_size=3) == [3, 4, 5]


def test_third_page():
    assert paginate(ITEMS, page=2, page_size=3) == [6, 7, 8]


def test_last_partial_page():
    assert paginate(ITEMS, page=3, page_size=3) == [9]


def test_page_beyond_range_is_empty():
    assert paginate(ITEMS, page=4, page_size=3) == []
