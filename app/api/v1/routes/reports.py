"""Compliance report generation and retrieval for an MFI.

A manager generates a report for a period; the pipeline snapshots the
verification counts (total + per-status) into an immutable record and logs
the action. Reports can then be listed and fetched.
"""

import uuid

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, require_manager_principal
from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import get_db
from app.models import ComplianceReport
from app.schemas.report import ReportRequest, ReportSummary
from app.services import audit, report_pdf, reporting

router = APIRouter(prefix="/kyc/reports", tags=["reports"])


@router.post(
    "", response_model=ReportSummary, status_code=status.HTTP_201_CREATED
)
def generate_report(
    payload: ReportRequest,
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> ComplianceReport:
    """Generate a compliance report for the given period."""
    if payload.period_start > payload.period_end:
        raise ValidationError(
            "period_start must be on or before period_end."
        )
    report = reporting.generate_report(
        db,
        mfi_account_id=principal.mfi_account.id,
        period_start=payload.period_start,
        period_end=payload.period_end,
    )
    audit.record(
        db,
        mfi_account_id=principal.mfi_account.id,
        action=audit.REPORT_GENERATED,
        actor_type=principal.actor_type,
        actor_id=principal.actor_id,
        details={
            "period_start": str(report.period_start),
            "period_end": str(report.period_end),
            "total_verifications": report.total_verifications,
        },
    )
    return report


@router.get("", response_model=list[ReportSummary])
def list_reports(
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> list[ComplianceReport]:
    """List the MFI's generated reports, newest first."""
    return (
        db.query(ComplianceReport)
        .filter_by(mfi_account_id=principal.mfi_account.id)
        .order_by(ComplianceReport.generated_at.desc())
        .all()
    )


@router.get("/{report_id}", response_model=ReportSummary)
def get_report(
    report_id: uuid.UUID,
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> ComplianceReport:
    """Fetch one of the MFI's compliance reports."""
    report = (
        db.query(ComplianceReport)
        .filter_by(id=report_id, mfi_account_id=principal.mfi_account.id)
        .one_or_none()
    )
    if report is None:
        raise NotFoundError("Report not found.")
    return report


@router.get("/{report_id}/pdf")
def download_report_pdf(
    report_id: uuid.UUID,
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream a COBAC-ready PDF of one of the MFI's compliance reports."""
    report = (
        db.query(ComplianceReport)
        .filter_by(id=report_id, mfi_account_id=principal.mfi_account.id)
        .one_or_none()
    )
    if report is None:
        raise NotFoundError("Report not found.")

    pdf = report_pdf.render_report_pdf(
        report,
        reporting.report_rows(db, report),
        mfi_name=principal.mfi_account.name,
    )
    filename = (
        f"kyc-compliance-{report.period_start}-{report.period_end}.pdf"
    )
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )
