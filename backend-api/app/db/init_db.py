"""Create all tables. Idempotent — safe to run repeatedly.

Dev (SQLite): run this directly to bootstrap attendance.db.
    backend-api/.venv/Scripts/python.exe -m app.db.init_db

Prod (Postgres + pgvector): run schema.sql / migrations there instead; this is
still safe but pgvector column types are managed separately.
"""

from app.db import models  # noqa: F401 — ensures models are registered
from app.db.database import Base, engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database initialized (tables created if missing).")
