"""Integration tests for POST /kyc/verify and quota enforcement."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import VerificationStatus
from tests.factories import create_mfi_with_key

VERIFY_URL = "/api/v1/kyc/verify"


def _auth(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def test_verify_succeeds_and_consumes_quota(
    api_client: TestClient, db_session: Session
) -> None:
    """A verification under quota returns 201 and increments usage."""
    account, key = create_mfi_with_key(db_session, usage=0)

    resp = api_client.post(
        VERIFY_URL,
        json={"client_id": "CLIENT-001"},
        headers=_auth(key),
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == VerificationStatus.VERIFIED.value
    assert body["client_id"] == "CLIENT-001"
    assert body["quota_remaining"] == 199
    assert body["quota_warning"] is False
    assert account.current_period_usage == 1


def test_verify_sets_warning_near_limit(
    api_client: TestClient, db_session: Session
) -> None:
    """Crossing 80% usage flips the quota_warning flag on."""
    # Starter quota is 200; 159 -> after this call 160 == 80%.
    _, key = create_mfi_with_key(db_session, usage=159)

    resp = api_client.post(
        VERIFY_URL,
        json={"client_id": "CLIENT-002"},
        headers=_auth(key),
    )

    assert resp.status_code == 201
    assert resp.json()["quota_warning"] is True


def test_verify_blocked_when_quota_exhausted(
    api_client: TestClient, db_session: Session
) -> None:
    """At the limit the request is blocked with 402 and is not recorded."""
    account, key = create_mfi_with_key(db_session, usage=200)

    resp = api_client.post(
        VERIFY_URL,
        json={"client_id": "CLIENT-003"},
        headers=_auth(key),
    )

    assert resp.status_code == 402
    assert resp.json()["error"]["code"] == "QUOTA_EXCEEDED"
    assert account.current_period_usage == 200  # unchanged


def test_verify_requires_authentication(api_client: TestClient) -> None:
    """No API key -> 401 before any quota logic runs."""
    resp = api_client.post(VERIFY_URL, json={"client_id": "CLIENT-004"})
    assert resp.status_code == 401
