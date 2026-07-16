"""Integration tests for MFI branch management."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import PlanName
from tests.factories import create_mfi_with_key

BRANCHES_URL = "/api/v1/branches"


def _auth(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def test_create_and_list_branches(
    api_client: TestClient, db_session: Session
) -> None:
    """A created branch is returned and listed."""
    _, key = create_mfi_with_key(db_session, plan_name=PlanName.GROWTH)

    resp = api_client.post(
        BRANCHES_URL, json={"name": "Mvog-Ada"}, headers=_auth(key)
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Mvog-Ada"

    listing = api_client.get(BRANCHES_URL, headers=_auth(key))
    assert [b["name"] for b in listing.json()] == ["Mvog-Ada"]


def test_create_rejects_duplicate_name(
    api_client: TestClient, db_session: Session
) -> None:
    """Two branches with the same name are rejected (400)."""
    _, key = create_mfi_with_key(db_session, plan_name=PlanName.GROWTH)
    api_client.post(
        BRANCHES_URL, json={"name": "Mvog-Ada"}, headers=_auth(key)
    )
    resp = api_client.post(
        BRANCHES_URL, json={"name": "Mvog-Ada"}, headers=_auth(key)
    )
    assert resp.status_code == 400


def test_enforces_plan_branch_limit(
    api_client: TestClient, db_session: Session
) -> None:
    """Branch creation stops at the plan's max_branches."""
    account, key = create_mfi_with_key(db_session)  # STARTER
    limit = account.plan.max_branches
    for i in range(limit):
        resp = api_client.post(
            BRANCHES_URL, json={"name": f"Branch {i}"}, headers=_auth(key)
        )
        assert resp.status_code == 201

    over = api_client.post(
        BRANCHES_URL, json={"name": "Extra"}, headers=_auth(key)
    )
    assert over.status_code == 400
