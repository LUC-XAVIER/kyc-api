"""Integration tests for the manager review queue."""

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import DuplicateFlag, Verification
from app.models.enums import (
    DuplicateResolution,
    SubmissionMethod,
    VerificationStatus,
)
from tests.factories import create_mfi_with_key

REVIEWS_URL = "/api/v1/kyc/reviews"


def _auth(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def _verification(
    db: Session,
    mfi_id,
    client_id: str,
    status: VerificationStatus = VerificationStatus.PENDING,
) -> Verification:
    verification = Verification(
        client_id=client_id,
        mfi_account_id=mfi_id,
        submission_method=SubmissionMethod.API,
        status=status,
        confidence_score=0.8,
        reject_reason="LIVENESS_REVIEW" if status.value == "PENDING" else None,
        processed_at=datetime.now(UTC),
    )
    db.add(verification)
    db.flush()
    return verification


def test_lists_only_this_mfis_pending(
    api_client: TestClient, db_session: Session
) -> None:
    """The queue shows the MFI's PENDING items only."""
    account, key = create_mfi_with_key(db_session, usage=0)
    _verification(db_session, account.id, "C-1")
    _verification(db_session, account.id, "C-2", VerificationStatus.VERIFIED)
    other, _ = create_mfi_with_key(db_session, usage=0, email="o@x.com")
    _verification(db_session, other.id, "C-OTHER")

    resp = api_client.get(REVIEWS_URL, headers=_auth(key))

    assert resp.status_code == 200
    body = resp.json()
    assert [item["client_id"] for item in body] == ["C-1"]
    assert body[0]["status"] == VerificationStatus.PENDING.value


def test_approve_moves_to_approved(
    api_client: TestClient, db_session: Session
) -> None:
    """Approving a PENDING verification sets APPROVED."""
    account, key = create_mfi_with_key(db_session, usage=0)
    verification = _verification(db_session, account.id, "C-1")

    resp = api_client.post(
        f"{REVIEWS_URL}/{verification.id}/decision",
        json={"action": "approve"},
        headers=_auth(key),
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == VerificationStatus.APPROVED.value
    db_session.refresh(verification)
    assert verification.status is VerificationStatus.APPROVED


def test_reject_sets_status_and_reason(
    api_client: TestClient, db_session: Session
) -> None:
    """Rejecting sets REJECTED and records the reason."""
    account, key = create_mfi_with_key(db_session, usage=0)
    verification = _verification(db_session, account.id, "C-1")

    resp = api_client.post(
        f"{REVIEWS_URL}/{verification.id}/decision",
        json={"action": "reject", "reason": "BAD_DOCS"},
        headers=_auth(key),
    )

    assert resp.status_code == 200
    db_session.refresh(verification)
    assert verification.status is VerificationStatus.REJECTED
    assert verification.reject_reason == "BAD_DOCS"


def test_approve_resolves_duplicate_flags(
    api_client: TestClient, db_session: Session
) -> None:
    """Approving dismisses the verification's duplicate flags."""
    account, key = create_mfi_with_key(db_session, usage=0)
    verification = _verification(db_session, account.id, "C-1")
    flag = DuplicateFlag(
        verification_id=verification.id,
        matched_client_id="C-9",
        similarity_score=0.9,
    )
    db_session.add(flag)
    db_session.flush()

    resp = api_client.post(
        f"{REVIEWS_URL}/{verification.id}/decision",
        json={"action": "approve"},
        headers=_auth(key),
    )

    assert resp.status_code == 200
    db_session.refresh(flag)
    assert flag.resolution is DuplicateResolution.DISMISSED


def test_unknown_verification_is_404(
    api_client: TestClient, db_session: Session
) -> None:
    """Deciding a non-existent verification is a 404."""
    _, key = create_mfi_with_key(db_session, usage=0)

    resp = api_client.post(
        f"{REVIEWS_URL}/{uuid.uuid4()}/decision",
        json={"action": "approve"},
        headers=_auth(key),
    )

    assert resp.status_code == 404


def test_cannot_review_another_mfis_verification(
    api_client: TestClient, db_session: Session
) -> None:
    """Another MFI's verification is invisible (404), not actionable."""
    _, key = create_mfi_with_key(db_session, usage=0)
    other, _ = create_mfi_with_key(db_session, usage=0, email="o@x.com")
    foreign = _verification(db_session, other.id, "C-OTHER")

    resp = api_client.post(
        f"{REVIEWS_URL}/{foreign.id}/decision",
        json={"action": "approve"},
        headers=_auth(key),
    )

    assert resp.status_code == 404


def test_non_pending_cannot_be_reviewed(
    api_client: TestClient, db_session: Session
) -> None:
    """Only PENDING verifications can be decided."""
    account, key = create_mfi_with_key(db_session, usage=0)
    verified = _verification(
        db_session, account.id, "C-1", VerificationStatus.VERIFIED
    )

    resp = api_client.post(
        f"{REVIEWS_URL}/{verified.id}/decision",
        json={"action": "approve"},
        headers=_auth(key),
    )

    assert resp.status_code == 400


def test_reviews_require_authentication(api_client: TestClient) -> None:
    """The queue is not accessible without an API key."""
    assert api_client.get(REVIEWS_URL).status_code == 401
