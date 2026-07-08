"""Compliance report generation over a verification period.

Aggregates an MFI's verifications in a date range into an immutable
:class:`ComplianceReport` snapshot (total + per-status breakdown), so a
later export or audit reflects the numbers as they were at generation time.
"""

import uuid
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import ComplianceReport, Verification


def generate_report(
    db: Session,
    *,
    mfi_account_id: uuid.UUID,
    period_start,
    period_end,
) -> ComplianceReport:
    """Snapshot the MFI's verifications for ``[period_start, period_end]``.

    The range is inclusive of both dates. Returns the persisted (flushed)
    report; the caller owns the transaction.
    """
    start = datetime.combine(period_start, time.min, tzinfo=UTC)
    end = datetime.combine(
        period_end + timedelta(days=1), time.min, tzinfo=UTC
    )

    rows = (
        db.query(Verification.status, func.count())
        .filter(
            Verification.mfi_account_id == mfi_account_id,
            Verification.created_at >= start,
            Verification.created_at < end,
        )
        .group_by(Verification.status)
        .all()
    )
    breakdown = {status.value: count for status, count in rows}

    report = ComplianceReport(
        mfi_account_id=mfi_account_id,
        period_start=period_start,
        period_end=period_end,
        total_verifications=sum(breakdown.values()),
        status_breakdown=breakdown,
    )
    db.add(report)
    db.flush()
    return report
