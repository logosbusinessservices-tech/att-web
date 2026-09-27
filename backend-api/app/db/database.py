"""Database engine + session factory.

The same code runs on SQLite (dev) and Postgres (prod); only DATABASE_URL differs.
SQLAlchemy speaks both. Embeddings are stored as raw float32 bytes (LargeBinary),
which works identically on both engines and matches the pipeline's SQLite format.
When we later add pgvector in production, only the embedding column type + the
match query change — nothing else in the app.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


# SQLite needs check_same_thread=False so the connection works across FastAPI's
# threadpool; Postgres ignores this arg.
_connect_args = {"check_same_thread": False} if settings.is_sqlite else {}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
