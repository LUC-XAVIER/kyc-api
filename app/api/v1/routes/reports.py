"""Compliance report generation and retrieval for an MFI.

A manager generates a report for a period; the pipeline snapshots the
verification counts (total + per-status) into an immutable record and logs
the action. Reports can then be listed and fetched.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_mfi
from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import get_db
from app.models import ComplianceReport, MfiAccount
from app.models.enums import ActorType
from app.schemas.report import ReportRequest, ReportSummary
from app.services import audit, reporting

router = APIRouter(prefix="/kyc/reports", tags=["reports"])


@router.post(
    "", response_model=ReportSummary, status_code=status.HTTP_201_CREATED
)
def generate_report(
    payload: ReportRequest,
    mfi: MfiAccount = Depends(get_current_mfi),
    db: Session = Depends(get_db),
) -> ComplianceReport:
    """Generate a compliance report for the given period."""
    if payload.period_start > payload.period_end:
        raise ValidationError(
            "period_start must be on or before period_end."
        )
    report = reporting.generate_report(
        db,
        mfi_account_id=mfi.id,
        period_start=payload.period_start,
        period_end=payload.period_end,
    )
    audit.record(
        db,
        mfi_account_id=mfi.id,
        action=audit.REPORT_GENERATED,
        actor_type=ActorType.MANAGER,
        details={
            "period_start": str(report.period_start),
            "period_end": str(report.period_end),
            "total_verifications": report.total_verifications,
        },
    )
    return report


@router.get("", response_model=list[ReportSummary])
def list_reports(
    mfi: MfiAccount = Depends(get_current_mfi),
    db: Session = Depends(get_db),
) -> list[ComplianceReport]:
    """List the MFI's generated reports, newest first."""
    return (
        db.query(ComplianceReport)
        .filter_by(mfi_account_id=mfi.id)
        .order_by(ComplianceReport.generated_at.desc())
        .all()
    )


@router.get("/{report_id}", response_model=ReportSummary)
def get_report(
    report_id: uuid.UUID,
    mfi: MfiAccount = Depends(get_current_mfi),
    db: Session = Depends(get_db),
) -> ComplianceReport:
    """Fetch one of the MFI's compliance reports."""
    report = (
        db.query(ComplianceReport)
        .filter_by(id=report_id, mfi_account_id=mfi.id)
        .one_or_none()
    )
    if report is None:
        raise NotFoundError("Report not found.")
    return report
