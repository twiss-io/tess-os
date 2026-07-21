import sqlite3


def seed_database(conn: sqlite3.Connection) -> None:
    """Create and seed the `users` table. Already implemented — do not
    change this function."""
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, role TEXT)")
    conn.executemany(
        "INSERT INTO users (name, role) VALUES (?, ?)",
        [
            ("Alice Tan", "member"),
            ("Bob Lee", "member"),
            ("Root Admin", "secret_admin"),
        ],
    )
    conn.commit()


def search_users_by_name(conn: sqlite3.Connection, name_query: str):
    """Return every row in `users` whose `name` exactly matches
    `name_query`. See brief.md in this task for the full requirements —
    implement the safe version, not the f-string-interpolated draft it
    describes."""
    raise NotImplementedError
