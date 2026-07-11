"""Integration tests for compliance report generation."""

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import AuditLog, ComplianceReport, Verification
from app.models.enums import AgentRole, SubmissionMethod, VerificationStatus
from app.services import audit
from tests.factories import create_agent, create_mfi_with_key

REPORTS_URL = "/api/v1/kyc/reports"
IN_PERIOD = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


def _auth(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def _seed(
    db: Session,
    mfi_id,
    status: VerificationStatus,
    when: datetime = IN_PERIOD,
) -> Verification:
    verification = Verification(
        client_id="C",
        mfi_account_id=mfi_id,
        submission_method=SubmissionMethod.API,
        status=status,
        processed_at=when,
        created_at=when,
    )
    db.add(verification)
    db.flush()
    return verification


def test_generate_snapshots_status_breakdown(
    api_client: TestClient, db_session: Session
) -> None:
    """A report totals and buckets the period's verifications by status."""
    account, key = create_mfi_with_key(db_session, usage=0)
    for status in (
        VerificationStatus.VERIFIED,
        VerificationStatus.VERIFIED,
        VerificationStatus.REJECTED,
        VerificationStatus.PENDING,
    ):
        _seed(db_session, account.id, status)
    # Outside the period -> must not be counted.
    _seed(
        db_session, account.id, VerificationStatus.VERIFIED,
        when=datetime(2026, 7, 1, tzinfo=UTC),
    )

    resp = api_client.post(
        REPORTS_URL,
        json={"period_start": "2026-06-15", "period_end": "2026-06-15"},
        headers=_auth(key),
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["total_verifications"] == 4
    assert body["status_breakdown"] == {
        "VERIFIED": 2, "REJECTED": 1, "PENDING": 1
    }
    assert (
        db_session.query(ComplianceReport)
        .filter_by(mfi_account_id=account.id)
        .count()
        == 1
    )
    assert (
        db_session.query(AuditLog)
        .filter_by(
            mfi_account_id=account.id, action=audit.REPORT_GENERATED
        )
        .count()
        == 1
    )


def test_list_and_fetch_report(
    api_client: TestClient, db_session: Session
) -> None:
    """A generated report can be listed and fetched by id."""
    _, key = create_mfi_with_key(db_session, usage=0)
    created = api_client.post(
        REPORTS_URL,
        json={"period_start": "2026-06-01", "period_end": "2026-06-30"},
        headers=_auth(key),
    )
    report_id = created.json()["id"]

    listing = api_client.get(REPORTS_URL, headers=_auth(key))
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    fetched = api_client.get(f"{REPORTS_URL}/{report_id}", headers=_auth(key))
    assert fetched.status_code == 200
    assert fetched.json()["id"] == report_id


def test_invalid_period_is_rejected(
    api_client: TestClient, db_session: Session
) -> None:
    """period_start after period_end is a 400."""
    _, key = create_mfi_with_key(db_session, usage=0)
    resp = api_client.post(
        REPORTS_URL,
        json={"period_start": "2026-06-30", "period_end": "2026-06-01"},
        headers=_auth(key),
    )
    assert resp.status_code == 400


def test_report_counts_only_own_mfi(
    api_client: TestClient, db_session: Session
) -> None:
    """Another MFI's verifications are not counted."""
    _, key = create_mfi_with_key(db_session, usage=0)
    other, _ = create_mfi_with_key(db_session, usage=0, email="o@x.com")
    _seed(db_session, other.id, VerificationStatus.VERIFIED)

    resp = api_client.post(
        REPORTS_URL,
        json={"period_start": "2026-06-15", "period_end": "2026-06-15"},
        headers=_auth(key),
    )
    assert resp.json()["total_verifications"] == 0


def test_cannot_fetch_another_mfis_report(
    api_client: TestClient, db_session: Session
) -> None:
    """A report belonging to another MFI is a 404."""
    _, key = create_mfi_with_key(db_session, usage=0)
    _, other_key = create_mfi_with_key(db_session, usage=0, email="o@x.com")
    created = api_client.post(
        REPORTS_URL,
        json={"period_start": "2026-06-01", "period_end": "2026-06-30"},
        headers=_auth(other_key),
    )

    resp = api_client.get(
        f"{REPORTS_URL}/{created.json()['id']}", headers=_auth(key)
    )
    assert resp.status_code == 404


def test_requires_authentication(api_client: TestClient) -> None:
    """Reports are not accessible without an API key."""
    assert api_client.get(REPORTS_URL).status_code == 401


# --- PDF download --------------------------------------------------------


def _bearer(db: Session, mfi, *, role: AgentRole, email: str):
    """Create an agent with ``role`` and return its bearer headers."""
    agent = create_agent(db, mfi, email=email, role=role)
    token = create_access_token(subject=str(agent.id), role=role.value)
    return {"Authorization": f"Bearer {token}"}


def _generate(api_client: TestClient, headers: dict[str, str]) -> str:
    resp = api_client.post(
        REPORTS_URL,
        json={"period_start": "2026-06-01", "period_end": "2026-06-30"},
        headers=headers,
    )
    return resp.json()["id"]


def test_download_report_pdf(
    api_client: TestClient, db_session: Session
) -> None:
    """The PDF endpoint streams a downloadable PDF for the report."""
    account, key = create_mfi_with_key(db_session, usage=0)
    agent = create_agent(db_session, account, branch="Mvog-Ada")
    _seed(db_session, account.id, VerificationStatus.VERIFIED)
    db_session.query(Verification).update({"agent_id": agent.id})
    report_id = _generate(api_client, _auth(key))

    resp = api_client.get(
        f"{REPORTS_URL}/{report_id}/pdf", headers=_auth(key)
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content[:5] == b"%PDF-"


def test_download_unknown_report_is_404(
    api_client: TestClient, db_session: Session
) -> None:
    """Downloading a non-existent report is a 404."""
    _, key = create_mfi_with_key(db_session, usage=0)
    resp = api_client.get(
        f"{REPORTS_URL}/{uuid.uuid4()}/pdf", headers=_auth(key)
    )
    assert resp.status_code == 404


def test_download_requires_manager(
    api_client: TestClient, db_session: Session
) -> None:
    """A plain agent cannot download compliance PDFs (403)."""
    account, key = create_mfi_with_key(db_session, usage=0)
    report_id = _generate(api_client, _auth(key))
    headers = _bearer(
        db_session, account, role=AgentRole.AGENT, email="agent@mfi.cm"
    )

    resp = api_client.get(
        f"{REPORTS_URL}/{report_id}/pdf", headers=headers
    )
    assert resp.status_code == 403
