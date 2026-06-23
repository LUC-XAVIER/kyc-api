"""Database engine and session management.

Exposes a configured SQLAlchemy engine, a session factory, and a
``get_db`` FastAPI dependency that yields a request-scoped session.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False
)


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped database session.

    Yields:
        An open :class:`~sqlalchemy.orm.Session` that is closed when the
        dependent request finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
