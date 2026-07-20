"""Integration tests for verification history and detail."""

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import (
    DuplicateFlag,
    ExtractedData,
    FaceMatchResult,
    LivenessResult,
    Verification,
)
from app.models.enums import (
    AgentRole,
    Sex,
    SubmissionMethod,
    VerificationStatus,
)
from tests.factories import create_agent, create_mfi_with_key

BASE = "/api/v1/kyc/verifications"
STATS_URL = f"{BASE}/stats"


def _auth(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def _bearer(db: Session, mfi, *, role: AgentRole, email: str):
    """Create an agent with ``role`` and return its bearer headers."""
    agent = create_agent(db, mfi, email=email, role=role)
    token = create_access_token(subject=str(agent.id), role=role.value)
    return {"Authorization": f"Bearer {token}"}


def _seed_stat(
    db: Session,
    mfi_id,
    *,
    status: VerificationStatus,
    when: datetime,
    agent_id=None,
    proc_seconds: int | None = None,
) -> Verification:
    """Seed one verification at a fixed time, agent, and processing span."""
    verification = Verification(
        client_id="C",
        mfi_account_id=mfi_id,
        agent_id=agent_id,
        submission_method=SubmissionMethod.API,
        status=status,
        confidence_score=0.8,
        created_at=when,
        processed_at=(
            when + timedelta(seconds=proc_seconds)
            if proc_seconds is not None
            else None
        ),
    )
    db.add(verification)
    db.flush()
    return verification


def _seed(
    db: Session,
    mfi_id,
    client_id: str = "C-1",
    status: VerificationStatus = VerificationStatus.PENDING,
) -> Verification:
    verification = Verification(
        client_id=client_id,
        mfi_account_id=mfi_id,
        submission_method=SubmissionMethod.API,
        status=status,
        confidence_score=0.8,
        processed_at=datetime.now(UTC),
    )
    db.add(verification)
    db.flush()
    db.add_all(
        [
            ExtractedData(
                verification_id=verification.id,
                full_name="JANE DOE",
                id_number="ID9",
                date_of_birth=date(1990, 1, 1),
                sex=Sex.F,
                occupation="ENGINEER",
            ),
            LivenessResult(
                verification_id=verification.id,
                passed=True,
                method="lbp-svm",
                anti_spoof_score=0.9,
                landmarks_detected=True,
            ),
            FaceMatchResult(
                verification_id=verification.id,
                match_score=0.8,
                verified=True,
                threshold=0.4,
            ),
            DuplicateFlag(
                verification_id=verification.id,
                matched_client_id="C-9",
                similarity_score=0.9,
            ),
        ]
    )
    db.flush()
    return verification


def test_detail_returns_all_stage_records(
    api_client: TestClient, db_session: Session
) -> None:
    """The detail view nests the per-stage records for a reviewer."""
    account, key = create_mfi_with_key(db_session, usage=0)
    verification = _seed(db_session, account.id)

    resp = api_client.get(f"{BASE}/{verification.id}", headers=_auth(key))

    assert resp.status_code == 200
    body = resp.json()
    assert body["client_id"] == "C-1"
    assert body["extracted_data"]["full_name"] == "JANE DOE"
    assert body["extracted_data"]["sex"] == "F"
    assert body["extracted_data"]["occupation"] == "ENGINEER"
    assert body["liveness_result"]["anti_spoof_score"] == 0.9
    assert body["face_match_result"]["verified"] is True
    assert len(body["duplicate_flags"]) == 1
    assert body["duplicate_flags"][0]["matched_client_id"] == "C-9"


def test_list_and_status_filter(
    api_client: TestClient, db_session: Session
) -> None:
    """Listing returns the MFI's verifications, filterable by status."""
    account, key = create_mfi_with_key(db_session, usage=0)
    _seed(db_session, account.id, "C-P", VerificationStatus.PENDING)
    _seed(db_session, account.id, "C-V", VerificationStatus.VERIFIED)

    all_resp = api_client.get(BASE, headers=_auth(key))
    assert all_resp.status_code == 200
    assert len(all_resp.json()) == 2

    pending = api_client.get(
        BASE, params={"status": "PENDING"}, headers=_auth(key)
    )
    assert [item["client_id"] for item in pending.json()] == ["C-P"]


def test_detail_unknown_is_404(
    api_client: TestClient, db_session: Session
) -> None:
    """A missing verification is a 404."""
    _, key = create_mfi_with_key(db_session, usage=0)
    resp = api_client.get(f"{BASE}/{uuid.uuid4()}", headers=_auth(key))
    assert resp.status_code == 404


def test_detail_of_another_mfi_is_404(
    api_client: TestClient, db_session: Session
) -> None:
    """Another MFI's verification is not visible."""
    _, key = create_mfi_with_key(db_session, usage=0)
    other, _ = create_mfi_with_key(db_session, usage=0, email="o@x.com")
    foreign = _seed(db_session, other.id, "C-OTHER")

    resp = api_client.get(f"{BASE}/{foreign.id}", headers=_auth(key))
    assert resp.status_code == 404


def test_requires_authentication(api_client: TestClient) -> None:
    """The history is not accessible without an API key."""
    assert api_client.get(BASE).status_code == 401


# --- Statistics endpoint -------------------------------------------------

_DAY = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
_PERIOD = {"start": "2026-06-01", "end": "2026-06-30"}


def _seed_stats_fixture(db: Session, account) -> None:
    """Seed a known mix across two branches, one row outside the period."""
    ada = create_agent(db, account, email="ada@mfi.cm", branch="Mvog-Ada")
    biy = create_agent(db, account, email="biy@mfi.cm", branch="Biyem-Assi")
    # In period: 2 VERIFIED + 1 REJECTED on Mvog-Ada; 1 PENDING + 1 APPROVED
    # on Biyem-Assi. Only the two VERIFIED carry a processing span (4s, 6s).
    _seed_stat(
        db,
        account.id,
        status=VerificationStatus.VERIFIED,
        when=_DAY,
        agent_id=ada.id,
        proc_seconds=4,
    )
    _seed_stat(
        db,
        account.id,
        status=VerificationStatus.VERIFIED,
        when=_DAY,
        agent_id=ada.id,
        proc_seconds=6,
    )
    _seed_stat(
        db,
        account.id,
        status=VerificationStatus.REJECTED,
        when=_DAY,
        agent_id=ada.id,
    )
    _seed_stat(
        db,
        account.id,
        status=VerificationStatus.PENDING,
        when=_DAY,
        agent_id=biy.id,
    )
    _seed_stat(
        db,
        account.id,
        status=VerificationStatus.APPROVED,
        when=_DAY,
        agent_id=biy.id,
    )
    # Outside the period -> must be excluded entirely.
    _seed_stat(
        db,
        account.id,
        status=VerificationStatus.VERIFIED,
        when=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
        agent_id=ada.id,
    )


def test_stats_aggregate_period_status_branch_and_time(
    api_client: TestClient, db_session: Session
) -> None:
    """Stats total, band, per-day, by-branch, and avg time by the period."""
    account, _ = create_mfi_with_key(db_session, usage=0)
    headers = _bearer(
        db_session, account, role=AgentRole.MANAGER, email="mgr@mfi.cm"
    )
    _seed_stats_fixture(db_session, account)

    resp = api_client.get(STATS_URL, params=_PERIOD, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["verified"] == 3  # VERIFIED + APPROVED
    assert body["pending"] == 1
    assert body["rejected"] == 1
    assert body["by_status"] == {
        "VERIFIED": 2,
        "APPROVED": 1,
        "PENDING": 1,
        "REJECTED": 1,
    }
    # One bucket per day of the requested range (June 1-30), empty days
    # included, so the dashboard chart keeps a stable x-axis.
    per_day = body["per_day"]
    assert len(per_day) == 30
    assert per_day[0]["date"] == "2026-06-01"
    assert per_day[-1]["date"] == "2026-06-30"
    assert {
        "date": "2026-06-15",
        "verified": 3,
        "pending": 1,
        "rejected": 1,
    } in per_day
    assert (
        sum(d["verified"] + d["pending"] + d["rejected"] for d in per_day) == 5
    )
    assert body["by_branch"] == [
        {"branch": "Mvog-Ada", "count": 3},
        {"branch": "Biyem-Assi", "count": 2},
    ]
    assert body["avg_processing_seconds"] == 5.0


def test_stats_branch_filter(
    api_client: TestClient, db_session: Session
) -> None:
    """A branch filter restricts every aggregate to that branch."""
    account, _ = create_mfi_with_key(db_session, usage=0)
    headers = _bearer(
        db_session, account, role=AgentRole.MANAGER, email="mgr@mfi.cm"
    )
    _seed_stats_fixture(db_session, account)

    resp = api_client.get(
        STATS_URL,
        params={**_PERIOD, "branch": "Mvog-Ada"},
        headers=headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["verified"] == 2
    assert body["rejected"] == 1
    assert body["pending"] == 0
    assert body["by_branch"] == [{"branch": "Mvog-Ada", "count": 3}]


def test_stats_requires_manager(
    api_client: TestClient, db_session: Session
) -> None:
    """A plain agent cannot read org-wide statistics (403)."""
    account, _ = create_mfi_with_key(db_session, usage=0)
    headers = _bearer(
        db_session, account, role=AgentRole.AGENT, email="agent@mfi.cm"
    )
    resp = api_client.get(STATS_URL, params=_PERIOD, headers=headers)
    assert resp.status_code == 403


def test_stats_rejects_inverted_range(
    api_client: TestClient, db_session: Session
) -> None:
    """A start date after the end date is a 400."""
    account, _ = create_mfi_with_key(db_session, usage=0)
    headers = _bearer(
        db_session, account, role=AgentRole.MANAGER, email="mgr@mfi.cm"
    )
    resp = api_client.get(
        STATS_URL,
        params={"start": "2026-06-30", "end": "2026-06-01"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_agent_sees_only_own_submissions(
    api_client: TestClient, db_session: Session
) -> None:
    """A plain agent's history is scoped to their own verifications."""
    account, _ = create_mfi_with_key(db_session)
    mine = create_agent(db_session, account, phone="699111111")
    other = create_agent(db_session, account, phone="699222222")
    v_mine = _seed(db_session, account.id, "C-MINE")
    v_mine.agent_id = mine.id
    v_other = _seed(db_session, account.id, "C-OTHER")
    v_other.agent_id = other.id
    db_session.flush()

    token = create_access_token(subject=str(mine.id), role="AGENT")
    rows = api_client.get(
        BASE, headers={"Authorization": f"Bearer {token}"}
    ).json()
    ids = {r["client_id"] for r in rows}
    assert "C-MINE" in ids
    assert "C-OTHER" not in ids
