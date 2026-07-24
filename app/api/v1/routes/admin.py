"""Platform-admin routes (cross-tenant).

Every endpoint here is gated by :func:`require_platform_admin` and reports
across *all* MFIs, so none of them apply the per-tenant scoping the rest of
the API uses. The admin can review each MFI and enable/disable it.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.api.v1.deps import require_platform_admin
from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import get_db
from app.models import MfiAccount, User
from app.models.enums import ActorType, MfiStatus
from app.schemas.admin import (
    AdminAuditEntry,
    AdminMfiDetail,
    AdminMfiSummary,
    MfiStatusUpdate,
    PlatformStats,
)
from app.services import admin as admin_service
from app.services import audit

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_platform_admin)],
)


def _get_mfi(db: Session, mfi_id: uuid.UUID) -> MfiAccount:
    """Fetch an MFI by id (with its plan) or raise 404."""
    mfi = (
        db.query(MfiAccount)
        .options(joinedload(MfiAccount.plan))
        .filter(MfiAccount.id == mfi_id)
        .one_or_none()
    )
    if mfi is None:
        raise NotFoundError("MFI account not found.")
    return mfi


@router.get("/stats", response_model=PlatformStats)
def platform_stats(db: Session = Depends(get_db)) -> PlatformStats:
    """Platform-wide totals for the admin Overview."""
    return admin_service.platform_stats(db)


@router.get("/mfis", response_model=list[AdminMfiSummary])
def list_mfis(db: Session = Depends(get_db)) -> list[AdminMfiSummary]:
    """Every MFI with its rollup counts, newest first."""
    return admin_service.list_mfis(db)


@router.get("/audit", response_model=list[AdminAuditEntry])
def audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[AdminAuditEntry]:
    """Platform-wide audit trail, newest first (paginated)."""
    return admin_service.list_audit(db, limit=limit, offset=offset)


@router.get("/mfis/{mfi_id}", response_model=AdminMfiDetail)
def mfi_detail(
    mfi_id: uuid.UUID, db: Session = Depends(get_db)
) -> AdminMfiDetail:
    """Full drill-down on one MFI."""
    return admin_service.mfi_detail(db, _get_mfi(db, mfi_id))


@router.patch("/mfis/{mfi_id}/status", response_model=AdminMfiDetail)
def update_mfi_status(
    mfi_id: uuid.UUID,
    payload: MfiStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> AdminMfiDetail:
    """Enable or disable an MFI account (ACTIVE ↔ SUSPENDED).

    Suspending immediately locks the MFI out of both the dashboard and its
    API keys (enforced at authentication). The change is audited.
    """
    if payload.status not in (MfiStatus.ACTIVE, MfiStatus.SUSPENDED):
        raise ValidationError("Status must be ACTIVE or SUSPENDED.")
    mfi = _get_mfi(db, mfi_id)
    mfi.status = payload.status
    audit.record(
        db,
        mfi_account_id=mfi.id,
        action=(
            audit.MFI_SUSPENDED
            if payload.status == MfiStatus.SUSPENDED
            else audit.MFI_REACTIVATED
        ),
        actor_type=ActorType.ADMIN,
        actor_id=str(admin.id),
    )
    db.commit()
    db.refresh(mfi)
    return admin_service.mfi_detail(db, mfi)
