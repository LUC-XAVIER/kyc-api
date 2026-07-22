"""Verification history and detail for the authenticated MFI.

The list gives a history view; the detail returns a verification together
with its per-stage records (OCR, liveness, face match, duplicate flags) so a
manager can see *why* a case landed where it did before acting on it.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session, joinedload

from app.api.v1.deps import (
    Principal,
    get_principal,
    require_manager_principal,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import get_db
from app.models import Verification, VerificationImage
from app.models.enums import ImageKind, VerificationStatus
from app.schemas.stats import VerificationStats
from app.schemas.verification import VerificationDetail, VerificationSummary
from app.services import stats

router = APIRouter(prefix="/kyc/verifications", tags=["verifications"])


@router.get("", response_model=list[VerificationSummary])
def list_verifications(
    status: VerificationStatus | None = Query(default=None),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[Verification]:
    """List verifications for the caller, newest first, optional status.

    A plain agent sees only their own submissions; managers and machine
    (API-key) callers see the whole MFI.
    """
    query = db.query(Verification).options(
        joinedload(Verification.agent),
        joinedload(Verification.extracted_data),
    ).filter_by(mfi_account_id=principal.mfi_account.id)
    if not principal.is_manager and principal.agent is not None:
        query = query.filter_by(agent_id=principal.agent.id)
    if status is not None:
        query = query.filter_by(status=status)
    return query.order_by(Verification.created_at.desc()).all()


@router.get("/stats", response_model=VerificationStats)
def verification_stats(
    start: date = Query(...),
    end: date = Query(...),
    branch: str | None = Query(default=None),
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> VerificationStats:
    """Return aggregated verification statistics for the dashboard.

    Managers only. Counts are scoped to the caller's MFI and the inclusive
    ``[start, end]`` date range, optionally narrowed to one branch.
    """
    if start > end:
        raise ValidationError("start must be on or before end.")
    return stats.compute_verification_stats(
        db,
        mfi_account_id=principal.mfi_account.id,
        period_start=start,
        period_end=end,
        branch=branch,
    )


def _scoped_verification(
    db: Session, verification_id: uuid.UUID, principal: Principal
) -> Verification:
    """Fetch a verification the caller is allowed to see, or 404.

    Scoped to the caller's MFI; an agent additionally only sees the cases
    they submitted, while a manager sees them all. Shared by the detail and
    image endpoints so the access rule lives in one place.
    """
    verification = (
        db.query(Verification)
        .filter_by(
            id=verification_id, mfi_account_id=principal.mfi_account.id
        )
        .one_or_none()
    )
    hidden_from_agent = (
        verification is not None
        and not principal.is_manager
        and principal.agent is not None
        and verification.agent_id != principal.agent.id
    )
    if verification is None or hidden_from_agent:
        raise NotFoundError("Verification not found.")
    return verification


@router.get("/{verification_id}", response_model=VerificationDetail)
def get_verification(
    verification_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Verification:
    """Return one verification with its per-stage records (scoped)."""
    return _scoped_verification(db, verification_id, principal)


@router.get("/{verification_id}/images/{kind}")
def get_verification_image(
    verification_id: uuid.UUID,
    kind: ImageKind,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Response:
    """Stream one captured image (ID front/back or selfie), decrypted.

    Same access scope as the detail endpoint. The bytes are biometric, so
    they are marked ``no-store`` to keep them out of any shared/disk cache.
    """
    _scoped_verification(db, verification_id, principal)
    image = (
        db.query(VerificationImage)
        .filter_by(verification_id=verification_id, kind=kind)
        .one_or_none()
    )
    if image is None:
        raise NotFoundError("Image not found.")
    return Response(
        content=image.image,
        media_type=image.content_type,
        headers={"Cache-Control": "private, no-store"},
    )
