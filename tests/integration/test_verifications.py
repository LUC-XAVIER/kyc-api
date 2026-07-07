"""Integration tests for verification history and detail."""

import uuid
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    DuplicateFlag,
    ExtractedData,
    FaceMatchResult,
    LivenessResult,
    Verification,
)
from app.models.enums import Sex, SubmissionMethod, VerificationStatus
from tests.factories import create_mfi_with_key

BASE = "/api/v1/kyc/verifications"


def _auth(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


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
    db.add_all([
        ExtractedData(
            verification_id=verification.id, full_name="JANE DOE",
            id_number="ID9", date_of_birth=date(1990, 1, 1), sex=Sex.F,
            occupation="ENGINEER",
        ),
        LivenessResult(
            verification_id=verification.id, passed=True, method="lbp-svm",
            anti_spoof_score=0.9, landmarks_detected=True,
        ),
        FaceMatchResult(
            verification_id=verification.id, match_score=0.8,
            verified=True, threshold=0.4,
        ),
        DuplicateFlag(
            verification_id=verification.id, matched_client_id="C-9",
            similarity_score=0.9,
        ),
    ])
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
