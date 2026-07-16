"""Manager review queue for PENDING verifications.

Verifications land in PENDING when the pipeline is unsure — a duplicate face
hit or a liveness score in the review band. A manager lists them and either
approves (→ APPROVED) or rejects (→ REJECTED) each one; any duplicate flags
on the verification are resolved to match the decision.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.v1.deps import Principal, require_manager_principal
from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import get_db
from app.models import Verification
from app.models.enums import (
    DuplicateResolution,
    VerificationStatus,
)
from app.pipeline.contracts import RejectReason
from app.schemas.review import (
    ReviewAction,
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    ReviewItem,
)
from app.services import audit

router = APIRouter(prefix="/kyc/reviews", tags=["reviews"])


@router.get("", response_model=list[ReviewItem])
def list_pending_reviews(
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> list[Verification]:
    """List the MFI's PENDING verifications, oldest first."""
    return (
        db.query(Verification)
        .options(
            joinedload(Verification.agent),
            joinedload(Verification.extracted_data),
            selectinload(Verification.duplicate_flags),
        )
        .filter_by(
            mfi_account_id=principal.mfi_account.id,
            status=VerificationStatus.PENDING,
        )
        .order_by(Verification.created_at)
        .all()
    )


@router.post(
    "/{verification_id}/decision", response_model=ReviewDecisionResponse
)
def decide_review(
    verification_id: uuid.UUID,
    payload: ReviewDecisionRequest,
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> ReviewDecisionResponse:
    """Approve or reject a PENDING verification owned by the caller's MFI."""
    verification = (
        db.query(Verification)
        .filter_by(
            id=verification_id, mfi_account_id=principal.mfi_account.id
        )
        .one_or_none()
    )
    if verification is None:
        raise NotFoundError("Verification not found.")
    if verification.status is not VerificationStatus.PENDING:
        raise ValidationError("Only PENDING verifications can be reviewed.")

    if payload.action is ReviewAction.APPROVE:
        verification.status = VerificationStatus.APPROVED
        resolution = DuplicateResolution.DISMISSED
    else:
        verification.status = VerificationStatus.REJECTED
        verification.reject_reason = (
            payload.reason or RejectReason.MANUAL_REJECT
        )
        resolution = DuplicateResolution.CONFIRMED

    for flag in verification.duplicate_flags:
        flag.resolution = resolution

    approved = payload.action is ReviewAction.APPROVE
    audit.record(
        db,
        mfi_account_id=principal.mfi_account.id,
        action=audit.REVIEW_APPROVED if approved else audit.REVIEW_REJECTED,
        actor_type=principal.actor_type,
        actor_id=principal.actor_id,
        verification_id=verification.id,
        details=None if approved else {"reason": verification.reject_reason},
    )
    db.flush()
    return ReviewDecisionResponse(
        verification_id=verification.id, status=verification.status
    )
