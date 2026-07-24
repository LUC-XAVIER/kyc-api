"""Integration tests for authentication.

Covers both the ``X-API-Key`` gateway (machine callers) and the dashboard
staff login (email/password -> JWT) plus its role dependencies.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.security.http import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.deps import (
    get_current_agent,
    get_current_mfi,
    require_manager,
    require_platform_admin,
)
from app.core.config import settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
)
from app.models import User
from app.models.enums import AgentRole, AgentStatus, MfiStatus
from tests.factories import create_agent, create_mfi_with_key

ACCOUNT_URL = "/api/v1/account"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"


def _bearer_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    """Wrap a raw JWT as the credentials object FastAPI would inject."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


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


# --- Dashboard login (email or phone + PIN -> JWT) ----------------------


def test_manager_logs_in_by_email(
    api_client: TestClient, db_session: Session
) -> None:
    """A manager signs in with email + PIN and gets an identity token."""
    mfi, _ = create_mfi_with_key(db_session)
    agent = create_agent(
        db_session,
        mfi,
        email="manager@mfi.cm",
        pin="483920",
        role=AgentRole.MANAGER,
        full_name="Eric Ngono",
    )

    resp = api_client.post(
        LOGIN_URL,
        json={"identifier": "manager@mfi.cm", "pin": "483920"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "MANAGER"
    assert body["full_name"] == "Eric Ngono"
    assert body["agent_id"] == str(agent.id)
    assert body["mfi_account_id"] == str(mfi.id)
    claims = decode_access_token(body["access_token"])
    assert claims["sub"] == str(agent.id)
    assert claims["role"] == "MANAGER"


def test_agent_logs_in_by_phone(
    api_client: TestClient, db_session: Session
) -> None:
    """An agent signs in with their phone number + PIN."""
    mfi, _ = create_mfi_with_key(db_session)
    create_agent(db_session, mfi, phone="699112233", pin="778899")

    resp = api_client.post(
        LOGIN_URL, json={"identifier": "699112233", "pin": "778899"}
    )

    assert resp.status_code == 200
    assert resp.json()["role"] == "AGENT"


def test_login_wrong_pin_is_unauthorized(
    api_client: TestClient, db_session: Session
) -> None:
    """A wrong PIN returns the generic 401 envelope."""
    mfi, _ = create_mfi_with_key(db_session)
    create_agent(db_session, mfi, phone="699000111", pin="123456")

    resp = api_client.post(
        LOGIN_URL, json={"identifier": "699000111", "pin": "000000"}
    )

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_login_unknown_identifier_is_unauthorized(
    api_client: TestClient, db_session: Session
) -> None:
    """An unknown identifier returns the same generic 401 (no enum)."""
    resp = api_client.post(
        LOGIN_URL, json={"identifier": "nobody@mfi.cm", "pin": "123456"}
    )
    assert resp.status_code == 401


def test_login_disabled_account_is_unauthorized(
    api_client: TestClient, db_session: Session
) -> None:
    """A disabled agent cannot log in even with the right PIN."""
    mfi, _ = create_mfi_with_key(db_session)
    agent = create_agent(db_session, mfi, phone="699222333", pin="123456")
    agent.status = AgentStatus.DISABLED
    db_session.flush()

    resp = api_client.post(
        LOGIN_URL, json={"identifier": "699222333", "pin": "123456"}
    )
    assert resp.status_code == 401


# --- Login brute-force throttle ------------------------------------------


def _fail_login(api_client: TestClient, identifier: str, times: int) -> None:
    """Submit ``times`` wrong-PIN logins for ``identifier``."""
    for _ in range(times):
        api_client.post(
            LOGIN_URL, json={"identifier": identifier, "pin": "000000"}
        )


def test_failed_logins_accumulate_on_the_account(
    api_client: TestClient, db_session: Session
) -> None:
    """The counter persists in the row, not in process memory."""
    mfi, _ = create_mfi_with_key(db_session)
    agent = create_agent(db_session, mfi, phone="699100001", pin="123456")

    _fail_login(api_client, "699100001", 2)

    db_session.refresh(agent)
    assert agent.failed_login_count == 2
    assert agent.locked_until is None


def test_account_locks_at_the_attempt_threshold(
    api_client: TestClient, db_session: Session
) -> None:
    """Hitting the threshold locks the account for the cooling-off window."""
    mfi, _ = create_mfi_with_key(db_session)
    agent = create_agent(db_session, mfi, phone="699100002", pin="123456")

    _fail_login(api_client, "699100002", settings.login_max_attempts)

    db_session.refresh(agent)
    assert agent.locked_until is not None
    assert agent.locked_until > datetime.now(UTC)


def test_locked_account_rejects_even_the_correct_pin(
    api_client: TestClient, db_session: Session
) -> None:
    """The whole point: guessing stops mattering once locked."""
    mfi, _ = create_mfi_with_key(db_session)
    create_agent(db_session, mfi, phone="699100003", pin="123456")

    _fail_login(api_client, "699100003", settings.login_max_attempts)
    resp = api_client.post(
        LOGIN_URL, json={"identifier": "699100003", "pin": "123456"}
    )

    assert resp.status_code == 401
    assert "Too many failed attempts" in resp.json()["error"]["message"]


def test_lock_expires_and_login_succeeds_again(
    api_client: TestClient, db_session: Session
) -> None:
    """A lapsed lock lets the real user back in.

    Lockout is time-boxed so nobody can permanently deny an agent access
    by spamming their identifier.
    """
    mfi, _ = create_mfi_with_key(db_session)
    agent = create_agent(db_session, mfi, phone="699100004", pin="123456")

    _fail_login(api_client, "699100004", settings.login_max_attempts)
    agent.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    resp = api_client.post(
        LOGIN_URL, json={"identifier": "699100004", "pin": "123456"}
    )
    assert resp.status_code == 200


def test_successful_login_clears_the_failure_streak(
    api_client: TestClient, db_session: Session
) -> None:
    """A good login resets the streak.

    The counter tracks consecutive failures, so occasional typos spread
    over time never accumulate into a lock.
    """
    mfi, _ = create_mfi_with_key(db_session)
    agent = create_agent(db_session, mfi, phone="699100005", pin="123456")

    _fail_login(api_client, "699100005", settings.login_max_attempts - 1)
    resp = api_client.post(
        LOGIN_URL, json={"identifier": "699100005", "pin": "123456"}
    )

    assert resp.status_code == 200
    db_session.refresh(agent)
    assert agent.failed_login_count == 0


# --- Bearer-token dependencies (get_current_agent / require_manager) -----


def test_get_current_agent_resolves_a_valid_token(
    db_session: Session,
) -> None:
    """A token minted for an active agent resolves back to that agent."""
    mfi, _ = create_mfi_with_key(db_session)
    agent = create_agent(db_session, mfi, role=AgentRole.MANAGER)
    token = create_access_token(subject=str(agent.id), role="MANAGER")

    resolved = get_current_agent(credentials=_bearer(token), db=db_session)
    assert resolved.id == agent.id


def test_get_current_agent_rejects_missing_and_bad_tokens(
    db_session: Session,
) -> None:
    """No credentials, or a malformed token, both raise 401."""
    with pytest.raises(AuthenticationError):
        get_current_agent(credentials=None, db=db_session)
    with pytest.raises(AuthenticationError):
        get_current_agent(credentials=_bearer("not.a.jwt"), db=db_session)


def test_get_current_agent_rejects_disabled_account(
    db_session: Session,
) -> None:
    """A valid token for a since-disabled agent is refused."""
    mfi, _ = create_mfi_with_key(db_session)
    agent = create_agent(db_session, mfi)
    agent.status = AgentStatus.DISABLED
    db_session.flush()
    token = create_access_token(subject=str(agent.id), role="AGENT")

    with pytest.raises(AuthenticationError):
        get_current_agent(credentials=_bearer(token), db=db_session)


def test_require_manager_allows_manager_and_admin(
    db_session: Session,
) -> None:
    """Manager and admin roles pass the manager gate."""
    mfi, _ = create_mfi_with_key(db_session)
    manager = create_agent(
        db_session, mfi, email="m@mfi.cm", role=AgentRole.MANAGER
    )
    admin = create_agent(
        db_session, mfi, email="admin@mfi.cm", role=AgentRole.ADMIN
    )
    assert require_manager(agent=manager) is manager
    assert require_manager(agent=admin) is admin


def test_require_manager_forbids_plain_agent(
    db_session: Session,
) -> None:
    """A plain agent is refused with 403."""
    mfi, _ = create_mfi_with_key(db_session)
    agent = create_agent(db_session, mfi, role=AgentRole.AGENT)
    with pytest.raises(AuthorizationError):
        require_manager(agent=agent)


def _create_admin(
    db_session: Session, email: str = "admin@openxtech.cm"
) -> User:
    """Seed a tenant-less platform admin (mfi_account_id is null)."""
    admin = User(
        full_name="Admin Openxtech",
        mfi_account_id=None,
        email=email,
        hashed_pin=hash_password("123456"),
        role=AgentRole.ADMIN,
    )
    db_session.add(admin)
    db_session.flush()
    return admin


def test_require_platform_admin_allows_admin(db_session: Session) -> None:
    """A platform admin passes the admin-only gate."""
    admin = _create_admin(db_session)
    assert require_platform_admin(agent=admin) is admin


def test_require_platform_admin_forbids_manager(db_session: Session) -> None:
    """A mere MFI manager cannot reach admin-only routes."""
    mfi, _ = create_mfi_with_key(db_session)
    manager = create_agent(db_session, mfi, role=AgentRole.MANAGER)
    with pytest.raises(AuthorizationError):
        require_platform_admin(agent=manager)


def test_admin_logs_in_with_no_mfi(
    api_client: TestClient, db_session: Session
) -> None:
    """The tenant-less admin signs in; its token carries no MFI id."""
    _create_admin(db_session, email="admin@openxtech.cm")
    resp = api_client.post(
        LOGIN_URL,
        json={"identifier": "admin@openxtech.cm", "pin": "123456"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "ADMIN"
    assert body["mfi_account_id"] is None


def test_login_blocked_when_mfi_suspended(
    api_client: TestClient, db_session: Session
) -> None:
    """Suspending an MFI locks its staff out of the dashboard."""
    mfi, _ = create_mfi_with_key(db_session)
    create_agent(db_session, mfi, email="mgr@mfi.cm", pin="483920")
    mfi.status = MfiStatus.SUSPENDED
    db_session.flush()

    resp = api_client.post(
        LOGIN_URL,
        json={"identifier": "mgr@mfi.cm", "pin": "483920"},
    )
    assert resp.status_code == 401
    assert "suspended" in resp.json()["error"]["message"].lower()


def test_api_key_rejected_when_mfi_suspended(db_session: Session) -> None:
    """A suspended MFI's API key is refused at the gateway too."""
    mfi, full_key = create_mfi_with_key(db_session)
    mfi.status = MfiStatus.SUSPENDED
    db_session.flush()

    with pytest.raises(AuthenticationError):
        get_current_mfi(api_key=full_key, db=db_session)


# --- Dashboard account access (bearer) + profile ------------------------


def test_account_is_readable_via_bearer_token(
    api_client: TestClient, db_session: Session
) -> None:
    """A signed-in agent can read the subscription summary."""
    mfi, _ = create_mfi_with_key(db_session, name="CamFinance")
    agent = create_agent(db_session, mfi, email="mgr@mfi.cm")
    token = create_access_token(subject=str(agent.id), role="AGENT")

    resp = api_client.get(ACCOUNT_URL, headers=_bearer_headers(token))

    assert resp.status_code == 200
    assert resp.json()["name"] == "CamFinance"
    assert resp.json()["plan_name"] == "STARTER"


def test_me_returns_the_signed_in_profile(
    api_client: TestClient, db_session: Session
) -> None:
    """GET /auth/me echoes the token's agent identity and role."""
    mfi, _ = create_mfi_with_key(db_session, name="CamFinance")
    agent = create_agent(
        db_session, mfi, email="jeanne@mfi.cm", role=AgentRole.AGENT,
        full_name="Jeanne Mbarga", branch="Mvog-Ada",
    )
    token = create_access_token(subject=str(agent.id), role="AGENT")

    resp = api_client.get(ME_URL, headers=_bearer_headers(token))

    assert resp.status_code == 200
    body = resp.json()
    assert body["full_name"] == "Jeanne Mbarga"
    assert body["email"] == "jeanne@mfi.cm"
    assert body["role"] == "AGENT"
    assert body["branch"] == "Mvog-Ada"
    assert body["mfi_account_id"] == str(mfi.id)
    assert body["mfi_name"] == "CamFinance"


def test_me_requires_a_token(api_client: TestClient) -> None:
    """The profile endpoint is not reachable without a bearer token."""
    assert api_client.get(ME_URL).status_code == 401


# --- Manager forgot / reset PIN -----------------------------------------

FORGOT_URL = "/api/v1/auth/forgot-pin"
RESET_URL = "/api/v1/auth/reset-pin"


def _reset_token(api_client: TestClient, email: str) -> str:
    link = api_client.post(FORGOT_URL, json={"email": email}).json()[
        "reset_link"
    ]
    return link.split("token=")[1]


def test_forgot_pin_returns_a_reset_link_for_a_manager(
    api_client: TestClient, db_session: Session
) -> None:
    """A known manager gets a (dev) reset link."""
    mfi, _ = create_mfi_with_key(db_session)
    create_agent(
        db_session, mfi, email="mgr@mfi.cm", role=AgentRole.MANAGER
    )
    resp = api_client.post(FORGOT_URL, json={"email": "mgr@mfi.cm"})
    assert resp.status_code == 202
    assert "token=" in resp.json()["reset_link"]


def test_forgot_pin_is_silent_for_unknown_email(
    api_client: TestClient, db_session: Session
) -> None:
    """An unknown email returns the same ack with no link (no enum)."""
    resp = api_client.post(FORGOT_URL, json={"email": "nobody@mfi.cm"})
    assert resp.status_code == 202
    assert resp.json()["reset_link"] is None


def test_reset_pin_sets_a_new_pin(
    api_client: TestClient, db_session: Session
) -> None:
    """After reset the new PIN works and the old one stops."""
    mfi, _ = create_mfi_with_key(db_session)
    create_agent(
        db_session, mfi, email="mgr2@mfi.cm", role=AgentRole.MANAGER,
        pin="111111",
    )
    token = _reset_token(api_client, "mgr2@mfi.cm")

    assert api_client.post(
        RESET_URL, json={"token": token, "pin": "999888"}
    ).status_code == 200
    assert api_client.post(
        LOGIN_URL, json={"identifier": "mgr2@mfi.cm", "pin": "999888"}
    ).status_code == 200
    assert api_client.post(
        LOGIN_URL, json={"identifier": "mgr2@mfi.cm", "pin": "111111"}
    ).status_code == 401


def test_reset_pin_invalid_token_is_404(
    api_client: TestClient, db_session: Session
) -> None:
    """An unknown reset token is a 404."""
    resp = api_client.post(
        RESET_URL, json={"token": "nope", "pin": "123456"}
    )
    assert resp.status_code == 404


def test_reset_pin_rejects_a_reused_token(
    api_client: TestClient, db_session: Session
) -> None:
    """A reset token can only be used once."""
    mfi, _ = create_mfi_with_key(db_session)
    create_agent(
        db_session, mfi, email="mgr3@mfi.cm", role=AgentRole.MANAGER
    )
    token = _reset_token(api_client, "mgr3@mfi.cm")
    assert api_client.post(
        RESET_URL, json={"token": token, "pin": "222333"}
    ).status_code == 200
    assert api_client.post(
        RESET_URL, json={"token": token, "pin": "444555"}
    ).status_code == 400


CHANGE_PIN_URL = "/api/v1/auth/change-pin"


def test_change_pin_requires_current_pin(
    api_client: TestClient, db_session: Session
) -> None:
    """Changing the PIN needs the current one; the new one then works."""
    mfi, _ = create_mfi_with_key(db_session)
    agent = create_agent(
        db_session, mfi, email="me@mfi.cm", role=AgentRole.MANAGER,
        pin="111111",
    )
    token = create_access_token(subject=str(agent.id), role="MANAGER")
    headers = {"Authorization": f"Bearer {token}"}

    wrong = api_client.post(
        CHANGE_PIN_URL,
        json={"current_pin": "000000", "new_pin": "222222"},
        headers=headers,
    )
    # A wrong current PIN is a 400 (validation), not a 401 — a 401 would trip
    # the client's auto-logout even though the session is still valid.
    assert wrong.status_code == 400

    ok = api_client.post(
        CHANGE_PIN_URL,
        json={"current_pin": "111111", "new_pin": "222222"},
        headers=headers,
    )
    assert ok.status_code == 200
    assert api_client.post(
        LOGIN_URL, json={"identifier": "me@mfi.cm", "pin": "222222"}
    ).status_code == 200
