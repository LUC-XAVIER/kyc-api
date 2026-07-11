"""Aggregate verification statistics for the manager dashboard.

Computes, for an MFI over an inclusive date range (optionally one branch):
totals and per-status counts, a per-day breakdown, a by-branch breakdown
(via the verification -> agent join, since branch lives on the agent), and
the average end-to-end processing time.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Agent, Verification
from app.models.enums import VerificationStatus
from app.schemas.stats import BranchBucket, DayBucket, VerificationStats

# Statuses that count as a clean/approved pass in the dashboard's bands.
_VERIFIED = {VerificationStatus.VERIFIED, VerificationStatus.APPROVED}
_UNASSIGNED = "Unassigned"


def compute_verification_stats(
    db: Session,
    *,
    mfi_account_id: uuid.UUID,
    period_start: date,
    period_end: date,
    branch: str | None = None,
) -> VerificationStats:
    """Return aggregated stats for ``[period_start, period_end]`` inclusive.

    Args:
        db: Request-scoped session.
        mfi_account_id: The tenant to scope every count to.
        period_start: First day counted (inclusive).
        period_end: Last day counted (inclusive).
        branch: If given, restrict to verifications submitted by an agent
            of that branch.

    Returns:
        A populated :class:`~app.schemas.stats.VerificationStats`.
    """
    start = datetime.combine(period_start, time.min, tzinfo=UTC)
    end = datetime.combine(
        period_end + timedelta(days=1), time.min, tzinfo=UTC
    )
    base = [
        Verification.mfi_account_id == mfi_account_id,
        Verification.created_at >= start,
        Verification.created_at < end,
    ]
    day_col = func.date(Verification.created_at)

    # Per-day, per-status counts (also the source of totals/by-status).
    day_q = db.query(day_col, Verification.status, func.count()).filter(
        *base
    )
    if branch is not None:
        day_q = day_q.join(
            Agent, Verification.agent_id == Agent.id
        ).filter(Agent.branch == branch)
    day_rows = day_q.group_by(day_col, Verification.status).all()

    by_status: dict[str, int] = {}
    days: dict[date, dict[str, int]] = {}
    for day, status, count in day_rows:
        by_status[status.value] = by_status.get(status.value, 0) + count
        bucket = days.setdefault(
            day, {"verified": 0, "pending": 0, "rejected": 0}
        )
        if status in _VERIFIED:
            bucket["verified"] += count
        elif status is VerificationStatus.PENDING:
            bucket["pending"] += count
        elif status is VerificationStatus.REJECTED:
            bucket["rejected"] += count

    per_day = [
        DayBucket(date=day, **days[day]) for day in sorted(days)
    ]

    # By-branch counts (outer join so unattributed rows still total).
    branch_q = (
        db.query(Agent.branch, func.count())
        .select_from(Verification)
        .outerjoin(Agent, Verification.agent_id == Agent.id)
        .filter(*base)
    )
    if branch is not None:
        branch_q = branch_q.filter(Agent.branch == branch)
    by_branch = [
        BranchBucket(branch=name or _UNASSIGNED, count=count)
        for name, count in sorted(
            branch_q.group_by(Agent.branch).all(),
            key=lambda row: row[1],
            reverse=True,
        )
    ]

    # Average end-to-end processing time (seconds) over processed rows.
    seconds = func.extract(
        "epoch", Verification.processed_at - Verification.created_at
    )
    avg_q = (
        db.query(func.avg(seconds))
        .select_from(Verification)
        .filter(*base, Verification.processed_at.isnot(None))
    )
    if branch is not None:
        avg_q = avg_q.join(
            Agent, Verification.agent_id == Agent.id
        ).filter(Agent.branch == branch)
    avg_seconds = avg_q.scalar()

    return VerificationStats(
        period_start=period_start,
        period_end=period_end,
        total=sum(by_status.values()),
        verified=by_status.get(VerificationStatus.VERIFIED.value, 0)
        + by_status.get(VerificationStatus.APPROVED.value, 0),
        pending=by_status.get(VerificationStatus.PENDING.value, 0),
        rejected=by_status.get(VerificationStatus.REJECTED.value, 0),
        by_status=by_status,
        per_day=per_day,
        by_branch=by_branch,
        avg_processing_seconds=(
            round(float(avg_seconds), 2) if avg_seconds is not None else None
        ),
    )
