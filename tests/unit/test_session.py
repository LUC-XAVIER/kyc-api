"""Unit tests for the ``get_db`` request-scoped transaction boundary.

These guard the persistence contract the integration harness can't: in
production a per-request session must COMMIT on success and ROLL BACK on
error, then close. (The test client overrides ``get_db`` with a shared
savepoint session, so it never exercises this path — the very reason a
missing commit slipped through once.)
"""

from unittest.mock import MagicMock

import pytest

from app.db import session as session_module


@pytest.fixture
def fake_session(monkeypatch) -> MagicMock:
    """Patch ``SessionLocal`` so ``get_db`` yields a mock session."""
    db = MagicMock(name="Session")
    monkeypatch.setattr(session_module, "SessionLocal", lambda: db)
    return db


def test_get_db_commits_and_closes_on_success(fake_session) -> None:
    """A normally-finishing request commits, then closes."""
    gen = session_module.get_db()
    yielded = next(gen)
    assert yielded is fake_session

    with pytest.raises(StopIteration):
        next(gen)  # drive the generator past ``yield`` (handler returned)

    fake_session.commit.assert_called_once()
    fake_session.rollback.assert_not_called()
    fake_session.close.assert_called_once()


def test_get_db_rolls_back_and_closes_on_error(fake_session) -> None:
    """A handler exception rolls back (no commit) and still closes."""
    gen = session_module.get_db()
    next(gen)

    with pytest.raises(ValueError):
        gen.throw(ValueError("handler blew up"))

    fake_session.rollback.assert_called_once()
    fake_session.commit.assert_not_called()
    fake_session.close.assert_called_once()
