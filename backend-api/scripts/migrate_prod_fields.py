"""Additive migration for the production roster fields (Phase 0).

Creates the new lookup tables (designations, employment_types) and adds the new
columns to persons/departments, preserving existing data. Works on both SQLite
(dev) and PostgreSQL (prod) by introspecting the live schema first.

Usage:
    backend-api/.venv/Scripts/python.exe -m scripts.migrate_prod_fields
"""

from sqlalchemy import text

from app.db.database import engine
from app.db.init_db import init_db

# column name -> (sqlite_ddl, postgres_ddl)
_BOOL_FALSE = ("BOOLEAN NOT NULL DEFAULT 0", "BOOLEAN NOT NULL DEFAULT FALSE")

ADDITIONS: dict[str, dict[str, tuple[str, str]]] = {
    "departments": {
        "is_other": _BOOL_FALSE,
    },
    "persons": {
        "date_of_birth": ("DATE", "DATE"),
        "designation_id": ("INTEGER", "INTEGER"),
        "designation_custom": ("VARCHAR", "VARCHAR"),
        "employment_type_id": ("INTEGER", "INTEGER"),
        "employment_type_custom": ("VARCHAR", "VARCHAR"),
        "department_custom": ("VARCHAR", "VARCHAR"),
    },
}


def _existing_columns(conn, table: str, is_sqlite: bool) -> set[str]:
    if is_sqlite:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}
    rows = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t"
        ),
        {"t": table},
    ).fetchall()
    return {r[0] for r in rows}


def main() -> None:
    # Creates any missing tables (designations, employment_types) without
    # altering existing ones.
    init_db()

    is_sqlite = engine.dialect.name == "sqlite"
    added = 0
    with engine.begin() as conn:
        for table, cols in ADDITIONS.items():
            existing = _existing_columns(conn, table, is_sqlite)
            for name, (sqlite_ddl, pg_ddl) in cols.items():
                if name in existing:
                    continue
                ddl = sqlite_ddl if is_sqlite else pg_ddl
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                print(f"  + {table}.{name}")
                added += 1
    print(f"Migration complete: {added} column(s) added.")


if __name__ == "__main__":
    main()
