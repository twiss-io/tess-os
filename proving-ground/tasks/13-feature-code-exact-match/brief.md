# Validate a 4-digit code (codes.py)

Implement `is_valid_code(s)` in `codes.py`.

It must return `True` **only** when `s` is exactly four ASCII digit
characters (`0`-`9`) and **nothing else**, and `False` otherwise.

"Nothing else" means, specifically:
- Exactly four characters long — not three, not five.
- Every character is one of `0123456789`.
- No leading or trailing whitespace, no trailing newline, no other
  characters of any kind.

Examples:

```
is_valid_code("1234")   -> True
is_valid_code("0007")   -> True
is_valid_code("123")    -> False   # too short
is_valid_code("12a4")   -> False   # not all digits
```

Constraints:
- Keep the signature `is_valid_code(s)` returning a `bool`.
- Standard library only.
