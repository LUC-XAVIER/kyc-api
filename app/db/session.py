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
    """Yield a request-scoped database session and own its transaction.

    The session is the request's transaction boundary: it **commits** when
    the handler returns normally and **rolls back** if it raises, then is
    closed either way. Handlers therefore only need to ``add``/``flush``
    their work — persistence happens here — and a failing request never
    leaves partial writes behind.

    Yields:
        An open :class:`~sqlalchemy.orm.Session`.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
