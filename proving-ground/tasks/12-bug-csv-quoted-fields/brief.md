# Parse one CSV line into fields (csvparse.py)

`csvparse.py` has `parse_fields(line)` which should split ONE line of CSV
text into its list of field values, following standard CSV quoting rules
(RFC 4180 style):

- Fields are separated by commas.
- A field may be wrapped in double quotes. A quoted field can contain
  commas — a comma inside quotes is part of the value, not a separator.
- Inside a quoted field, a doubled double-quote (`""`) means one literal
  double-quote character.
- The surrounding quotes are not part of the returned value.
- An empty field is the empty string.

Examples:

```
parse_fields('a,b,c')  -> ['a', 'b', 'c']
parse_fields('p,,q')   -> ['p', '', 'q']
```

There is a `test_csvparse.py` you can run with
`python -m pytest test_csvparse.py`.

**Your task:** make `parse_fields` correct per the rules above — including
rows where a quoted field itself contains a comma.

Constraints:
- Do not modify `test_csvparse.py`.
- Keep the signature `parse_fields(line)` returning a list of strings.
- The Python standard library is available.
