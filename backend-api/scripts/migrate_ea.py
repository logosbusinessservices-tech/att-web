"""Dev-only additive migration for Executive Assistant mode (SQLite, preserves data).

The only schema change is a brand-new `delegated_tasks` table; `create_all` adds
it without touching existing tables/data. The EA itself is just a Person with
role='assistant', so no column changes are needed. In prod use Alembic.

Usage:
    backend-api/.venv/Scripts/python.exe -m scripts.migrate_ea
"""

from sqlalchemy import inspect

from app.db.database import engine
from app.db.init_db import init_db


def main():
    before = set(inspect(engine).get_table_names())
    init_db()  # create_all: creates only missing tables (e.g. delegated_tasks)
    after = set(inspect(engine).get_table_names())
    new = sorted(after - before)
    if new:
        print("Migration complete. New table(s): " + ", ".join(new))
    else:
        print("Migration complete. No new tables (delegated_tasks already present).")


if __name__ == "__main__":
    main()
