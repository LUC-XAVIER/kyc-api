"""Integration tests for manager agent management."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.enums import AgentRole, AgentStatus
from tests.factories import (
    create_agent,
    create_mfi_with_key,
    get_or_create_branch,
)

AGENTS_URL = "/api/v1/agents"
LOGIN_URL = "/api/v1/auth/login"


def _auth(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def _new_agent(branch_id, phone: str = "699100200", **over) -> dict:
    return {
        "full_name": "New Agent",
        "phone": phone,
        "pin": "654321",
        "branch_id": str(branch_id),
        **over,
    }


def test_create_list_and_login_roundtrip(
    api_client: TestClient, db_session: Session
) -> None:
    """A created agent appears in the list and can log in by phone."""
    account, key = create_mfi_with_key(db_session)
    branch = get_or_create_branch(db_session, account, "Mvog-Ada")

    created = api_client.post(
        AGENTS_URL, json=_new_agent(branch.id), headers=_auth(key)
    )
    assert created.status_code == 201
    body = created.json()
    assert body["role"] == "AGENT"
    assert body["status"] == "ACTIVE"
    assert body["phone"] == "+237699100200"
    assert body["branch_name"] == "Mvog-Ada"
    assert "pin" not in body and "hashed_pin" not in body

    listing = api_client.get(AGENTS_URL, headers=_auth(key))
    assert [a["phone"] for a in listing.json()] == ["+237699100200"]

    login = api_client.post(
        LOGIN_URL, json={"identifier": "699100200", "pin": "654321"}
    )
    assert login.status_code == 200
    assert login.json()["role"] == "AGENT"


def test_list_excludes_managers(
    api_client: TestClient, db_session: Session
) -> None:
    """The agents list holds AGENT-role users only, not managers."""
    account, key = create_mfi_with_key(db_session)
    create_agent(
        db_session, account, email="boss@mfi.cm", phone="699111111",
        role=AgentRole.MANAGER, full_name="The Manager",
    )
    create_agent(
        db_session, account, email=None, phone="699222222",
        role=AgentRole.AGENT, full_name="Field Agent",
    )

    listing = api_client.get(AGENTS_URL, headers=_auth(key)).json()
    roles = {a["role"] for a in listing}
    names = {a["full_name"] for a in listing}
    assert roles == {"AGENT"}
    assert "The Manager" not in names
    assert "Field Agent" in names


def test_create_rejects_unknown_branch(
    api_client: TestClient, db_session: Session
) -> None:
    """A branch_id not belonging to the MFI is a 400."""
    _, key = create_mfi_with_key(db_session)
    resp = api_client.post(
        AGENTS_URL, json=_new_agent(uuid.uuid4()), headers=_auth(key)
    )
    assert resp.status_code == 400


def test_create_rejects_invalid_phone(
    api_client: TestClient, db_session: Session
) -> None:
    """A non-Cameroonian / malformed phone fails validation (422)."""
    account, key = create_mfi_with_key(db_session)
    branch = get_or_create_branch(db_session, account, "Mvog-Ada")
    resp = api_client.post(
        AGENTS_URL, json=_new_agent(branch.id, phone="12345"),
        headers=_auth(key),
    )
    assert resp.status_code == 422


def test_create_normalizes_phone(
    api_client: TestClient, db_session: Session
) -> None:
    """A local number is normalized to +237 + 9 digits."""
    account, key = create_mfi_with_key(db_session)
    branch = get_or_create_branch(db_session, account, "Mvog-Ada")
    resp = api_client.post(
        AGENTS_URL, json=_new_agent(branch.id, phone="6 99 88 77 66"),
        headers=_auth(key),
    )
    assert resp.status_code == 201
    assert resp.json()["phone"] == "+237699887766"


def test_create_rejects_duplicate_phone(
    api_client: TestClient, db_session: Session
) -> None:
    """A second agent with the same phone is rejected (400)."""
    account, key = create_mfi_with_key(db_session)
    branch = get_or_create_branch(db_session, account, "Mvog-Ada")
    api_client.post(
        AGENTS_URL, json=_new_agent(branch.id), headers=_auth(key)
    )

    resp = api_client.post(
        AGENTS_URL, json=_new_agent(branch.id), headers=_auth(key)
    )
    assert resp.status_code == 400


def test_create_rejects_short_pin(
    api_client: TestClient, db_session: Session
) -> None:
    """A PIN shorter than 6 chars fails validation (422)."""
    account, key = create_mfi_with_key(db_session)
    branch = get_or_create_branch(db_session, account, "Mvog-Ada")
    resp = api_client.post(
        AGENTS_URL, json=_new_agent(branch.id, pin="123"), headers=_auth(key)
    )
    assert resp.status_code == 422


def test_create_enforces_plan_agent_limit(
    api_client: TestClient, db_session: Session
) -> None:
    """Creation is blocked once the plan's agent limit is reached."""
    account, key = create_mfi_with_key(db_session)  # STARTER: 3 agents
    branch = get_or_create_branch(db_session, account, "Mvog-Ada")
    limit = account.plan.max_agents
    for i in range(limit):
        resp = api_client.post(
            AGENTS_URL, json=_new_agent(branch.id, phone=f"69900{i:04d}"),
            headers=_auth(key),
        )
        assert resp.status_code == 201

    over = api_client.post(
        AGENTS_URL,
        json=_new_agent(branch.id, phone="699999999"),
        headers=_auth(key),
    )
    assert over.status_code == 400


def test_update_status_and_branch(
    api_client: TestClient, db_session: Session
) -> None:
    """A manager can disable an account and reassign its branch."""
    account, key = create_mfi_with_key(db_session)
    agent = create_agent(db_session, account, phone="699111222")
    other = get_or_create_branch(db_session, account, "Biyem-Assi")

    resp = api_client.patch(
        f"{AGENTS_URL}/{agent.id}",
        json={"status": "DISABLED", "branch_id": str(other.id)},
        headers=_auth(key),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "DISABLED"
    assert body["branch_name"] == "Biyem-Assi"
    db_session.refresh(agent)
    assert agent.status is AgentStatus.DISABLED


def test_manager_resets_agent_pin(
    api_client: TestClient, db_session: Session
) -> None:
    """A manager re-initialises an agent's PIN; the old one stops working."""
    account, key = create_mfi_with_key(db_session)
    agent = create_agent(
        db_session, account, phone="699333444", pin="111111"
    )
    assert api_client.post(
        LOGIN_URL, json={"identifier": "699333444", "pin": "111111"}
    ).status_code == 200

    reset = api_client.post(
        f"{AGENTS_URL}/{agent.id}/reset-pin",
        json={"pin": "222222"},
        headers=_auth(key),
    )
    assert reset.status_code == 200

    assert api_client.post(
        LOGIN_URL, json={"identifier": "699333444", "pin": "222222"}
    ).status_code == 200
    assert api_client.post(
        LOGIN_URL, json={"identifier": "699333444", "pin": "111111"}
    ).status_code == 401


def test_update_unknown_agent_is_404(
    api_client: TestClient, db_session: Session
) -> None:
    """Updating a non-existent agent is a 404."""
    _, key = create_mfi_with_key(db_session)
    resp = api_client.patch(
        f"{AGENTS_URL}/{uuid.uuid4()}",
        json={"full_name": "X"},
        headers=_auth(key),
    )
    assert resp.status_code == 404


def test_plain_agent_is_forbidden(
    api_client: TestClient, db_session: Session
) -> None:
    """A non-manager agent cannot manage agents (403)."""
    account, _ = create_mfi_with_key(db_session)
    agent = create_agent(db_session, account, role=AgentRole.AGENT)
    branch = get_or_create_branch(db_session, account, "Mvog-Ada")
    token = create_access_token(subject=str(agent.id), role="AGENT")
    headers = {"Authorization": f"Bearer {token}"}

    assert api_client.get(AGENTS_URL, headers=headers).status_code == 403
    assert (
        api_client.post(
            AGENTS_URL, json=_new_agent(branch.id), headers=headers
        ).status_code
        == 403
    )
