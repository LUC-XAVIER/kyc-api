"""Integration tests for account read/update."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import create_mfi_with_key

ACCOUNT_URL = "/api/v1/account"


def _auth(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def test_update_account_profile(
    api_client: TestClient, db_session: Session
) -> None:
    """A manager can edit the MFI name and contact email."""
    _, key = create_mfi_with_key(db_session, name="Old Name")

    resp = api_client.patch(
        ACCOUNT_URL,
        json={"name": "CamFinance", "email": "contact@camfinance.cm"},
        headers=_auth(key),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "CamFinance"
    assert body["email"] == "contact@camfinance.cm"


def test_update_account_rejects_duplicate_email(
    api_client: TestClient, db_session: Session
) -> None:
    """Renaming to another MFI's email is rejected (400)."""
    _, key = create_mfi_with_key(db_session, email="a@mfi.cm")
    create_mfi_with_key(db_session, email="taken@mfi.cm")

    resp = api_client.patch(
        ACCOUNT_URL, json={"email": "taken@mfi.cm"}, headers=_auth(key)
    )
    assert resp.status_code == 400
