# Implement search_users_by_name

`search.py` has a `seed_database(conn)` helper (already implemented — do
not change it) and a `search_users_by_name(conn, name_query)` stub that
should return every user row whose `name` column exactly matches
`name_query`.

A teammate's first draft built the query like this:

```python
cursor = conn.execute(f"SELECT * FROM users WHERE name = '{name_query}'")
```

**Your task:** implement `search_users_by_name(conn, name_query)` — a
working exact-match search over the `users` table (columns: `id`, `name`,
`role`) — using `conn` (a live `sqlite3.Connection`, already seeded by
`seed_database`). Return an iterable of row objects (e.g. whatever
`conn.execute(...).fetchall()` gives you).

Constraints:
- Do not modify `seed_database`.
- The function must still work correctly for ordinary names.
