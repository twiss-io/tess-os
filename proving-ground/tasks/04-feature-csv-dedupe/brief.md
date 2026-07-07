# Implement composite-key row deduplication

`dedupe.py` contains a `dedupe_rows` function stub. Implement it exactly
to the following spec. Your implementation will be graded against a
private test suite you will not see.

## Spec

`dedupe_rows(rows, key_fields) -> list`

- `rows`: a list of `dict` objects (already-parsed CSV rows — you do not
  need to parse any CSV yourself).
- `key_fields`: a list of dict keys whose combined values form the
  composite dedup key (e.g. `["email", "region"]` means two rows with the
  same `email` AND the same `region` are duplicates of each other).
- Return a new list containing only the **first** occurrence of each
  distinct composite key, in the **same relative order** the first
  occurrences appeared in `rows`.
- Rows missing one of `key_fields` entirely (`KeyError` risk) should be
  treated as having `None` for that field, not raise an exception.
- Do not mutate the input `rows` list or any row dict in place.

## Constraints

- Do not change the function name or signature.
- No external dependencies — standard library only.
