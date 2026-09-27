"""Dev-only additive migration for the self-sign-up feature (SQLite, preserves data).

Adds the new account-lifecycle + avatar columns if missing, so an existing dev
database keeps its data instead of being recreated. In prod use Alembic.

Usage:
    backend-api/.venv/Scripts/python.exe -m scripts.migrate_signup
"""

from sqlalchemy import text

from app.db.database import engine

ADDITIONS = {
    "persons": [
        ("status", "VARCHAR NOT NULL DEFAULT 'active'"),
        ("activated_at", "DATETIME"),
        ("avatar_path", "VARCHAR"),
    ],
}


def _columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}


def main():
    added = 0
    with engine.begin() as conn:
        for table, cols in ADDITIONS.items():
            existing = _columns(conn, table)
            for name, ddl in cols:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    print(f"  + {table}.{name}")
                    added += 1
        # Backfill: existing accounts with a password are considered activated.
        conn.execute(text(
            "UPDATE persons SET activated_at = created_at "
            "WHERE activated_at IS NULL AND password_hash IS NOT NULL"
        ))
    print(f"Migration complete: {added} column(s) added.")


if __name__ == "__main__":
    main()
