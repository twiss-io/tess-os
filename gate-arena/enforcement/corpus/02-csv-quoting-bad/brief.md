# Bug report: `parse_row` breaks on quoted fields containing commas

`parse_row(line)` splits a CSV line into fields. It currently does
`line.split(',')`, which mis-parses any field that is quoted and contains
an embedded comma — e.g. `'a,"b,c",d'` (3 logical fields: `a`, `b,c`, `d`)
comes back as 4 fields instead of 3.

**Fix `parse_row` to correctly handle quoted fields with embedded
commas**, using Python's standard `csv` module rather than hand-rolled
splitting.

Acceptance: `parse_row('a,"b,c",d') == ['a', 'b,c', 'd']` (exactly 3
elements, the embedded comma preserved inside field 2).
