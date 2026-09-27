"""Dev-only additive migration for Phase 3 columns (SQLite, preserves data).

Adds the new field-attendance columns if they're missing, so an existing dev
database keeps its data (onboarded employees, events) instead of being recreated.
In prod use a real migration tool (Alembic).

Usage:
    backend-api/.venv/Scripts/python.exe -m scripts.migrate_phase3
"""

from sqlalchemy import text

from app.db.database import engine

ADDITIONS = {
    "persons": [
        ("field_scan_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
        ("manager_id", "INTEGER"),
    ],
    "attendance_events": [
        ("review_status", "VARCHAR NOT NULL DEFAULT 'approved'"),
        ("gps_accuracy_m", "FLOAT"),
        ("distance_m", "FLOAT"),
        ("nearest_station_id", "INTEGER"),
        ("selfie_path", "VARCHAR"),
        ("voided", "BOOLEAN NOT NULL DEFAULT 0"),
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
    print(f"Migration complete: {added} column(s) added.")


if __name__ == "__main__":
    main()
