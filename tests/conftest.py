"""Shared pytest fixtures."""

import base64
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import settings
from app.db.session import engine, get_db
from app.main import create_app

# Fixed so the suite never depends on a developer's .env or a CI secret.
# Safe to hardcode precisely because it is not a real key: test rows are
# rolled back, and anything it sealed is worthless outside the suite.
_TEST_KEY = base64.urlsafe_b64encode(
    b"kyc-test-key-32-bytes-exactly!!!"
).decode()


@pytest.fixture(autouse=True, scope="session")
def _test_encryption_key() -> Generator[None, None, None]:
    """Seal PII columns with a known key for the whole test session."""
    original = settings.encryption_key
    settings.encryption_key = _TEST_KEY
    crypto._cipher.cache_clear()
    yield
    settings.encryption_key = original
    crypto._cipher.cache_clear()


@pytest.fixture(autouse=True)
def _email_dev_mode() -> Generator[None, None, None]:
    """Never send real email in tests — run onboarding/reset in dev mode."""
    original = settings.email_enabled
    settings.email_enabled = False
    yield
    settings.email_enabled = original


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
