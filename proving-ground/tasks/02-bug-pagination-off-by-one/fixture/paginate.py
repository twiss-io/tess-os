def paginate(items, page, page_size):
    """Return the `page`-th (zero-indexed) slice of `items`, `page_size` long.

    BUG: `end` is one short, so every page is missing its last item, and
    every page after the first also starts one item early.
    """
    start = page * page_size
    end = start + page_size - 1
    return items[start:end]
