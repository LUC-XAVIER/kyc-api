"""Integration tests for manager agent management."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.enums import AgentRole, AgentStatus
from tests.factories import create_agent, create_mfi_with_key

AGENTS_URL = "/api/v1/agents"
LOGIN_URL = "/api/v1/auth/login"


def _auth(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def _new_agent(email: str = "new@mfi.cm", **over) -> dict:
    return {
        "full_name": "New Agent",
        "email": email,
        "password": "welcome-1",
        "branch": "Mvog-Ada",
        **over,
    }


def test_create_list_and_login_roundtrip(
    api_client: TestClient, db_session: Session
) -> None:
    """A created agent appears in the list and can then log in."""
    _, key = create_mfi_with_key(db_session)

    created = api_client.post(
        AGENTS_URL, json=_new_agent(), headers=_auth(key)
    )
    assert created.status_code == 201
    body = created.json()
    assert body["role"] == "AGENT"
    assert body["status"] == "ACTIVE"
    assert "password" not in body

    listing = api_client.get(AGENTS_URL, headers=_auth(key))
    assert [a["email"] for a in listing.json()] == ["new@mfi.cm"]

    login = api_client.post(
        LOGIN_URL, json={"email": "new@mfi.cm", "password": "welcome-1"}
    )
    assert login.status_code == 200


def test_create_rejects_duplicate_email(
    api_client: TestClient, db_session: Session
) -> None:
    """A second agent with the same email is rejected (400)."""
    _, key = create_mfi_with_key(db_session)
    api_client.post(AGENTS_URL, json=_new_agent(), headers=_auth(key))

    resp = api_client.post(
        AGENTS_URL, json=_new_agent(), headers=_auth(key)
    )
    assert resp.status_code == 400


def test_create_rejects_admin_role(
    api_client: TestClient, db_session: Session
) -> None:
    """A manager cannot mint a platform ADMIN (400)."""
    _, key = create_mfi_with_key(db_session)
    resp = api_client.post(
        AGENTS_URL, json=_new_agent(role="ADMIN"), headers=_auth(key)
    )
    assert resp.status_code == 400


def test_create_enforces_plan_agent_limit(
    api_client: TestClient, db_session: Session
) -> None:
    """Creation is blocked once the plan's agent limit is reached."""
    account, key = create_mfi_with_key(db_session)  # STARTER: 3 agents
    limit = account.plan.max_agents
    for i in range(limit):
        resp = api_client.post(
            AGENTS_URL, json=_new_agent(email=f"a{i}@mfi.cm"),
            headers=_auth(key),
        )
        assert resp.status_code == 201

    over = api_client.post(
        AGENTS_URL, json=_new_agent(email="over@mfi.cm"), headers=_auth(key)
    )
    assert over.status_code == 400


def test_update_role_and_status(
    api_client: TestClient, db_session: Session
) -> None:
    """A manager can promote an agent and disable an account."""
    account, key = create_mfi_with_key(db_session)
    agent = create_agent(db_session, account, email="a@mfi.cm")

    resp = api_client.patch(
        f"{AGENTS_URL}/{agent.id}",
        json={"role": "MANAGER", "status": "DISABLED"},
        headers=_auth(key),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "MANAGER"
    assert body["status"] == "DISABLED"
    db_session.refresh(agent)
    assert agent.role is AgentRole.MANAGER
    assert agent.status is AgentStatus.DISABLED


def test_update_unknown_agent_is_404(
    api_client: TestClient, db_session: Session
) -> None:
    """Updating a non-existent agent is a 404."""
    _, key = create_mfi_with_key(db_session)
    resp = api_client.patch(
        f"{AGENTS_URL}/{uuid.uuid4()}",
        json={"branch": "X"},
        headers=_auth(key),
    )
    assert resp.status_code == 404


def test_plain_agent_is_forbidden(
    api_client: TestClient, db_session: Session
) -> None:
    """A non-manager agent cannot manage agents (403)."""
    account, _ = create_mfi_with_key(db_session)
    agent = create_agent(db_session, account, role=AgentRole.AGENT)
    token = create_access_token(subject=str(agent.id), role="AGENT")
    headers = {"Authorization": f"Bearer {token}"}

    assert api_client.get(AGENTS_URL, headers=headers).status_code == 403
    assert (
        api_client.post(
            AGENTS_URL, json=_new_agent(), headers=headers
        ).status_code
        == 403
    )
