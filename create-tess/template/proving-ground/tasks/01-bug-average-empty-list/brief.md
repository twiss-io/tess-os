# Fix a bug in calc.py

This directory contains `calc.py` and `test_calc.py`.

Run `python -m pytest test_calc.py` and you will see a failing test:
`average([])` raises `ZeroDivisionError` instead of returning `0.0`.

**Your task:** fix `calc.py` so that every test in `test_calc.py` passes.

Constraints:
- Do not modify `test_calc.py`.
- Do not delete or skip any test.
- When you believe you are done, run `python -m pytest test_calc.py` yourself
  and confirm it exits with all tests passing before finishing.
