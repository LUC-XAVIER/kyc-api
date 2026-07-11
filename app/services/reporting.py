"""Compliance report generation over a verification period.

Aggregates an MFI's verifications in a date range into an immutable
:class:`ComplianceReport` snapshot (total + per-status breakdown), so a
later export or audit reflects the numbers as they were at generation time.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Agent, ComplianceReport, Verification

_MISSING = "—"


def _period_bounds(period_start: date, period_end: date):
    """Return the ``[start, end)`` datetime bounds for inclusive dates."""
    start = datetime.combine(period_start, time.min, tzinfo=UTC)
    end = datetime.combine(
        period_end + timedelta(days=1), time.min, tzinfo=UTC
    )
    return start, end


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
    start, end = _period_bounds(period_start, period_end)

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


@dataclass(frozen=True)
class ReportRow:
    """One verification line for a compliance report's detail table."""

    client_id: str
    date: date
    branch: str
    agent: str
    status: str


def report_rows(db: Session, report: ComplianceReport) -> list[ReportRow]:
    """Return the verifications covered by ``report``, newest first.

    Joins each verification to its submitting agent (outer, since a
    machine/API submission has none) for the branch and agent columns.

    Args:
        db: Request-scoped session.
        report: The persisted report whose period defines the rows.

    Returns:
        The per-verification rows for the report's PDF/detail table.
    """
    start, end = _period_bounds(report.period_start, report.period_end)
    rows = (
        db.query(Verification, Agent)
        .outerjoin(Agent, Verification.agent_id == Agent.id)
        .filter(
            Verification.mfi_account_id == report.mfi_account_id,
            Verification.created_at >= start,
            Verification.created_at < end,
        )
        .order_by(Verification.created_at.desc())
        .all()
    )
    return [
        ReportRow(
            client_id=verification.client_id,
            date=verification.created_at.date(),
            branch=agent.branch if agent and agent.branch else _MISSING,
            agent=agent.full_name if agent else _MISSING,
            status=verification.status.value,
        )
        for verification, agent in rows
    ]
