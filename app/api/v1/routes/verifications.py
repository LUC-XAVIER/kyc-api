"""Verification history and detail for the authenticated MFI.

The list gives a history view; the detail returns a verification together
with its per-stage records (OCR, liveness, face match, duplicate flags) so a
manager can see *why* a case landed where it did before acting on it.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_mfi
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models import MfiAccount, Verification
from app.models.enums import VerificationStatus
from app.schemas.verification import VerificationDetail, VerificationSummary

router = APIRouter(prefix="/kyc/verifications", tags=["verifications"])


@router.get("", response_model=list[VerificationSummary])
def list_verifications(
    status: VerificationStatus | None = Query(default=None),
    mfi: MfiAccount = Depends(get_current_mfi),
    db: Session = Depends(get_db),
) -> list[Verification]:
    """List the MFI's verifications, newest first, optionally by status."""
    query = db.query(Verification).filter_by(mfi_account_id=mfi.id)
    if status is not None:
        query = query.filter_by(status=status)
    return query.order_by(Verification.created_at.desc()).all()


@router.get("/{verification_id}", response_model=VerificationDetail)
def get_verification(
    verification_id: uuid.UUID,
    mfi: MfiAccount = Depends(get_current_mfi),
    db: Session = Depends(get_db),
) -> Verification:
    """Return one verification with its per-stage records."""
    verification = (
        db.query(Verification)
        .filter_by(id=verification_id, mfi_account_id=mfi.id)
        .one_or_none()
    )
    if verification is None:
        raise NotFoundError("Verification not found.")
    return verification
