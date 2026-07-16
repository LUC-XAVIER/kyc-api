"""Integration tests for self-service manager onboarding."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

BASE = "/api/v1/onboarding"
LOGIN_URL = "/api/v1/auth/login"


def _start(
    api_client: TestClient, email: str = "new@mfi.cm", plan: str = "GROWTH"
):
    return api_client.post(
        f"{BASE}/start", json={"email": email, "plan": plan}
    )


def _token_from(resp) -> str:
    return resp.json()["signup_link"].split("token=")[1]


def test_start_returns_a_dev_signup_link(
    api_client: TestClient, db_session: Session
) -> None:
    """Starting signup returns 202 with a usable dev link (email off)."""
    resp = _start(api_client)
    assert resp.status_code == 202
    assert "token=" in resp.json()["signup_link"]


def test_start_rejects_unknown_plan(
    api_client: TestClient, db_session: Session
) -> None:
    """An unknown plan is a 400."""
    assert _start(api_client, plan="BOGUS").status_code == 400


def test_invite_returns_prefill_email_and_plan(
    api_client: TestClient, db_session: Session
) -> None:
    """The token resolves to the email + plan that pre-fill the form."""
    token = _token_from(_start(api_client, email="pref@mfi.cm"))
    resp = api_client.get(f"{BASE}/invite/{token}")
    assert resp.status_code == 200
    assert resp.json() == {"email": "pref@mfi.cm", "plan": "GROWTH"}


def test_invite_invalid_token_is_404(
    api_client: TestClient, db_session: Session
) -> None:
    """An unknown token is a 404."""
    assert api_client.get(f"{BASE}/invite/nope").status_code == 404


def test_complete_creates_account_then_manager_logs_in(
    api_client: TestClient, db_session: Session
) -> None:
    """Completing signup creates the MFI + manager, who can then log in."""
    token = _token_from(_start(api_client, email="boss@mfi.cm"))

    complete = api_client.post(
        f"{BASE}/complete",
        json={
            "token": token,
            "full_name": "Eric Ngono",
            "mfi_name": "CamFinance",
            "pin": "778899",
            "phone": "699000111",
        },
    )
    assert complete.status_code == 201
    assert complete.json()["email"] == "boss@mfi.cm"

    login = api_client.post(
        LOGIN_URL, json={"identifier": "boss@mfi.cm", "pin": "778899"}
    )
    assert login.status_code == 200
    assert login.json()["role"] == "MANAGER"


def test_complete_rejects_a_reused_token(
    api_client: TestClient, db_session: Session
) -> None:
    """A token can only complete signup once."""
    token = _token_from(_start(api_client, email="once@mfi.cm"))
    body = {
        "token": token, "full_name": "A", "mfi_name": "M", "pin": "112233",
    }
    assert api_client.post(f"{BASE}/complete", json=body).status_code == 201
    assert api_client.post(f"{BASE}/complete", json=body).status_code == 400


def test_complete_rejects_short_pin(
    api_client: TestClient, db_session: Session
) -> None:
    """A PIN shorter than 6 chars fails validation (422)."""
    token = _token_from(_start(api_client, email="short@mfi.cm"))
    resp = api_client.post(
        f"{BASE}/complete",
        json={
            "token": token, "full_name": "A", "mfi_name": "M", "pin": "12",
        },
    )
    assert resp.status_code == 422
