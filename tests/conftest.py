"""Shared pytest fixtures."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import engine, get_db
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient bound to a fresh app instance (no DB override)."""
    return TestClient(create_app())


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Yield a session whose writes are rolled back after the test.

    The session joins an outer transaction and commits onto SAVEPOINTs
    (``create_savepoint``), so even endpoint code that calls ``commit()``
    is undone when the outer transaction is rolled back. Requires a running
    database.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def api_client(db_session: Session) -> Generator[TestClient, None, None]:
    """A TestClient whose ``get_db`` resolves to the rolled-back session."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
