# Compute billing facts from transactions.csv

`transactions.csv` in this directory has a header row and then one
transaction per line:

```
txn_id,timestamp,status,amount_cents
```

- `timestamp` is ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`).
- `status` is one of `captured`, `refunded`, or `failed`.
- `amount_cents` is an integer number of cents (refunds are negative).

Do the following **in order** — each step depends on the previous one:

1. **Find the busiest month.** Group transactions by calendar month
   (`YYYY-MM`, from the `timestamp`). The busiest month is the one with the
   **most transaction rows** (count them — every row, regardless of
   status). There is no tie.
2. **Restrict to that month.** For every step below, use only the rows
   whose month equals the busiest month from step 1.
3. **Captured revenue only.** Within the busiest month, consider only rows
   with `status == "captured"`. Ignore `refunded` and `failed` rows
   entirely — they do not count toward revenue or the average.
4. Report, in `answer.json` (written in this directory, not inside any
   subfolder), exactly these keys:

```json
{
  "busiest_month": "YYYY-MM",
  "captured_count": 0,
  "gross_revenue_cents": 0,
  "avg_captured_cents": 0.0
}
```

Field definitions:
- `busiest_month` — the `YYYY-MM` string from step 1.
- `captured_count` — number of `captured` rows in the busiest month.
- `gross_revenue_cents` — sum of `amount_cents` over those `captured` rows.
- `avg_captured_cents` — `gross_revenue_cents / captured_count`, rounded to
  1 decimal place.

Notes:
- Every value must be computed from the file — do not guess.
- The month with the highest total revenue is **not** necessarily the
  month with the most transactions. Follow the steps as written.
- Do not modify `transactions.csv`.
