# Fix a pagination bug

This directory contains `paginate.py` and `test_paginate.py`.

Run `python -m pytest test_paginate.py` and you will see failing tests:
every page is missing its last item.

**Your task:** fix `paginate()` in `paginate.py` so every test in
`test_paginate.py` passes.

Constraints:
- Do not modify `test_paginate.py`.
- `page` is zero-indexed.
- When you believe you are done, run `python -m pytest test_paginate.py`
  yourself and confirm it exits with all tests passing before finishing.
