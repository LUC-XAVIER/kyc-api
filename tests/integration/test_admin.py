"""Integration tests for the platform-admin (cross-tenant) routes."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models import User, Verification
from app.models.enums import (
    AgentRole,
    MfiStatus,
    SubmissionMethod,
    VerificationStatus,
)
from tests.factories import create_agent, create_mfi_with_key

STATS_URL = "/api/v1/admin/stats"
MFIS_URL = "/api/v1/admin/mfis"


def _admin_headers(db: Session, email: str = "admin@openxtech.cm") -> dict:
    """Seed a tenant-less admin and return its bearer headers."""
    admin = User(
        full_name="Admin Openxtech",
        mfi_account_id=None,
        email=email,
        hashed_pin=hash_password("123456"),
        role=AgentRole.ADMIN,
    )
    db.add(admin)
    db.flush()
    token = create_access_token(subject=str(admin.id), role="ADMIN")
    return {"Authorization": f"Bearer {token}"}


def _seed_verification(
    db: Session, mfi_id, status: VerificationStatus
) -> None:
    db.add(
        Verification(
            client_id="C",
            mfi_account_id=mfi_id,
            submission_method=SubmissionMethod.API,
            status=status,
            confidence_score=0.8,
            created_at=datetime.now(UTC),
        )
    )
    db.flush()


def test_admin_stats_counts_the_platform(
    api_client: TestClient, db_session: Session
) -> None:
    """Overview totals reflect every MFI and verification."""
    headers = _admin_headers(db_session)
    mfi_a, _ = create_mfi_with_key(db_session, name="MFI A", email="a@x.cm")
    mfi_b, _ = create_mfi_with_key(db_session, name="MFI B", email="b@x.cm")
    create_agent(db_session, mfi_a, email="mgr@a.cm", role=AgentRole.MANAGER)
    _seed_verification(db_session, mfi_a.id, VerificationStatus.VERIFIED)
    _seed_verification(db_session, mfi_b.id, VerificationStatus.PENDING)

    resp = api_client.get(STATS_URL, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_mfis"] >= 2
    assert body["total_verifications"] >= 2
    assert body["total_users"] >= 1
    assert len(body["per_day"]) == 14


def test_admin_lists_mfis_with_rollups(
    api_client: TestClient, db_session: Session
) -> None:
    """The accounts list carries per-MFI counts."""
    headers = _admin_headers(db_session)
    mfi, _ = create_mfi_with_key(db_session, name="Rollup MFI", email="r@x.cm")
    mfi.status = MfiStatus.ACTIVE
    create_agent(db_session, mfi, email="mgr@r.cm", role=AgentRole.MANAGER)
    _seed_verification(db_session, mfi.id, VerificationStatus.VERIFIED)

    resp = api_client.get(MFIS_URL, headers=headers)

    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["name"] == "Rollup MFI")
    assert row["verifications"] == 1
    assert row["users"] == 1
    assert row["api_keys"] == 1
    assert row["status"] == "ACTIVE"


def test_admin_mfi_detail(
    api_client: TestClient, db_session: Session
) -> None:
    """Detail returns plan, performance, and staff for one MFI."""
    headers = _admin_headers(db_session)
    mfi, _ = create_mfi_with_key(db_session, name="Detail MFI", email="d@x.cm")
    create_agent(db_session, mfi, email="mgr@d.cm", role=AgentRole.MANAGER)
    _seed_verification(db_session, mfi.id, VerificationStatus.VERIFIED)

    resp = api_client.get(f"{MFIS_URL}/{mfi.id}", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Detail MFI"
    assert body["performance"]["verified"] == 1
    assert len(body["agents"]) == 1
    assert len(body["api_keys"]) == 1


def test_admin_suspends_and_reactivates_an_mfi(
    api_client: TestClient, db_session: Session
) -> None:
    """PATCH status flips the account and persists it."""
    headers = _admin_headers(db_session)
    mfi, _ = create_mfi_with_key(db_session, name="Toggle MFI", email="t@x.cm")

    resp = api_client.patch(
        f"{MFIS_URL}/{mfi.id}/status",
        json={"status": "SUSPENDED"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUSPENDED"
    db_session.refresh(mfi)
    assert mfi.status == MfiStatus.SUSPENDED

    resp = api_client.patch(
        f"{MFIS_URL}/{mfi.id}/status",
        json={"status": "ACTIVE"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ACTIVE"


def test_admin_audit_lists_actions(
    api_client: TestClient, db_session: Session
) -> None:
    """A suspend action shows up in the platform audit trail."""
    headers = _admin_headers(db_session)
    mfi, _ = create_mfi_with_key(db_session, name="Audit MFI", email="au@x.cm")
    api_client.patch(
        f"{MFIS_URL}/{mfi.id}/status",
        json={"status": "SUSPENDED"},
        headers=headers,
    )

    resp = api_client.get("/api/v1/admin/audit", headers=headers)

    assert resp.status_code == 200
    entry = next(e for e in resp.json() if e["action"] == "mfi.suspended")
    assert entry["mfi_name"] == "Audit MFI"
    assert entry["actor_type"] == "ADMIN"


def test_admin_rejects_invalid_status(
    api_client: TestClient, db_session: Session
) -> None:
    """PENDING is not a valid admin toggle target -> 400."""
    headers = _admin_headers(db_session)
    mfi, _ = create_mfi_with_key(db_session, name="Bad MFI", email="bad@x.cm")

    resp = api_client.patch(
        f"{MFIS_URL}/{mfi.id}/status",
        json={"status": "PENDING"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_admin_detail_unknown_mfi_is_404(
    api_client: TestClient, db_session: Session
) -> None:
    """An unknown MFI id returns 404."""
    headers = _admin_headers(db_session)
    unknown = "00000000-0000-0000-0000-000000000000"
    resp = api_client.get(f"{MFIS_URL}/{unknown}", headers=headers)
    assert resp.status_code == 404


def test_admin_routes_forbid_a_manager(
    api_client: TestClient, db_session: Session
) -> None:
    """A mere MFI manager cannot reach the admin surface -> 403."""
    mfi, _ = create_mfi_with_key(db_session, name="Guard MFI", email="g@x.cm")
    manager = create_agent(
        db_session, mfi, email="mgr@g.cm", role=AgentRole.MANAGER
    )
    token = create_access_token(subject=str(manager.id), role="MANAGER")
    resp = api_client.get(
        STATS_URL, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
