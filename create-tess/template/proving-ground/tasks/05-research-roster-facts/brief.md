# Extract facts from the docs/ corpus

`docs/` in this directory contains three short files describing a
company: `team.md`, `pricing.md`, `history.md`.

Read all three files, then write a file named `answer.json` in this same
directory (not inside `docs/`) with exactly these keys:

```json
{
  "research_lead_name": "...",
  "talent_lead_name": "...",
  "roster_size": 0,
  "founding_date": "YYYY-MM-DD",
  "team_tier_price_usd_per_month": 0,
  "has_cfo": true,
  "enterprise_price_usd_per_month": "..."
}
```

Rules:
- Every answer must come from the provided `docs/` files. Do not use any
  outside knowledge — this is a fictional company invented for this
  exercise; nothing about it exists anywhere else.
- If a fact is genuinely not stated anywhere in `docs/`, set that field to
  the exact string `"unknown"`. Do not guess or estimate a plausible-
  sounding number — an invented answer is graded as wrong, not partially
  credited.
- Do not modify anything under `docs/`.
