"""Integration tests for manager API-key management."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import KEY_PREFIX, create_access_token
from app.models.enums import AgentRole
from tests.factories import create_agent, create_mfi_with_key

KEYS_URL = "/api/v1/api-keys"
ACCOUNT_URL = "/api/v1/account"


def _auth(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def test_created_key_can_authenticate(
    api_client: TestClient, db_session: Session
) -> None:
    """A minted key is returned once and immediately usable."""
    _, key = create_mfi_with_key(db_session)

    resp = api_client.post(KEYS_URL, headers=_auth(key))

    assert resp.status_code == 201
    minted = resp.json()["full_key"]
    assert minted.startswith(KEY_PREFIX)
    assert api_client.get(
        ACCOUNT_URL, headers=_auth(minted)
    ).status_code == 200


def test_list_hides_secrets(
    api_client: TestClient, db_session: Session
) -> None:
    """Listing shows the factory key plus the new one, never a secret."""
    _, key = create_mfi_with_key(db_session)
    api_client.post(KEYS_URL, headers=_auth(key))

    listing = api_client.get(KEYS_URL, headers=_auth(key))

    assert listing.status_code == 200
    keys = listing.json()
    assert len(keys) == 2
    assert all("full_key" not in k and "hashed_key" not in k for k in keys)


def test_revoke_disables_the_key(
    api_client: TestClient, db_session: Session
) -> None:
    """A revoked key is marked inactive and can no longer authenticate."""
    _, key = create_mfi_with_key(db_session)
    created = api_client.post(KEYS_URL, headers=_auth(key)).json()

    revoked = api_client.delete(
        f"{KEYS_URL}/{created['id']}", headers=_auth(key)
    )
    assert revoked.status_code == 200
    assert revoked.json()["is_active"] is False
    assert api_client.get(
        ACCOUNT_URL, headers=_auth(created["full_key"])
    ).status_code == 401


def test_revoke_unknown_is_404(
    api_client: TestClient, db_session: Session
) -> None:
    """Revoking a non-existent key is a 404."""
    _, key = create_mfi_with_key(db_session)
    resp = api_client.delete(
        f"{KEYS_URL}/{uuid.uuid4()}", headers=_auth(key)
    )
    assert resp.status_code == 404


def test_plain_agent_is_forbidden(
    api_client: TestClient, db_session: Session
) -> None:
    """A non-manager agent cannot manage API keys (403)."""
    account, _ = create_mfi_with_key(db_session)
    agent = create_agent(db_session, account, role=AgentRole.AGENT)
    token = create_access_token(subject=str(agent.id), role="AGENT")
    headers = {"Authorization": f"Bearer {token}"}

    assert api_client.get(KEYS_URL, headers=headers).status_code == 403
    assert api_client.post(KEYS_URL, headers=headers).status_code == 403
