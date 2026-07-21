# Dedupe an email list (dedupe.py)

Implement `dedupe_emails(emails)` in `dedupe.py`. `emails` is a list of
email-address strings. Return a new list with duplicates removed, subject
to **all** of these rules:

1. **Case-insensitive duplicates.** Two addresses that differ only in
   letter case (e.g. `"Bob@X.com"` and `"bob@x.com"`) are the same address
   and must appear only once.
2. **Keep the first occurrence.** When the same address appears more than
   once, keep the one that appeared first, with its **original casing**
   exactly as given. Do not lowercase or otherwise alter the strings you
   keep.
3. **Preserve order.** The returned list must be in the same relative order
   as the first occurrences in the input.

Example:

```
dedupe_emails(["a@x.com", "b@x.com", "a@x.com"]) -> ["a@x.com", "b@x.com"]
```

Constraints:
- Keep the signature `dedupe_emails(emails)` returning a list.
- Standard library only.
