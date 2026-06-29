"""Integration tests for API-key authentication on a protected route."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import create_mfi_with_key

ACCOUNT_URL = "/api/v1/account"


def test_missing_key_is_unauthorized(api_client: TestClient) -> None:
    """No header -> 401 with our error envelope."""
    resp = api_client.get(ACCOUNT_URL)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_unknown_key_is_unauthorized(api_client: TestClient) -> None:
    """A well-formed but unknown key -> 401."""
    resp = api_client.get(
        ACCOUNT_URL, headers={"X-API-Key": "kyc_live_not-a-real-key"}
    )
    assert resp.status_code == 401


def test_valid_key_returns_account_summary(
    api_client: TestClient, db_session: Session
) -> None:
    """A valid key resolves to its MFI and returns the summary."""
    _, full_key = create_mfi_with_key(db_session, name="Test MFI")

    resp = api_client.get(ACCOUNT_URL, headers={"X-API-Key": full_key})

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Test MFI"
    assert body["plan_name"] == "STARTER"
    assert body["verification_quota"] == 200
    assert body["current_period_usage"] == 0
