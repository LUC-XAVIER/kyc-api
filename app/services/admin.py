"""Cross-tenant aggregations for the Openxtech platform-admin dashboard.

Unlike :mod:`app.services.stats` (which scopes to one MFI), these roll up
*every* MFI on the platform. Consumed only by the ``/admin/*`` routes.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models import (
    ApiKey,
    Branch,
    DuplicateFlag,
    MfiAccount,
    SubscriptionPlan,
    User,
    Verification,
)
from app.models.enums import MfiStatus, VerificationStatus
from app.schemas.admin import (
    AdminAgentSummary,
    AdminApiKeySummary,
    AdminMfiDetail,
    AdminMfiSummary,
    DayCount,
    MfiPerformance,
    PlanBucket,
    PlatformStats,
    QuotaRow,
)

# An MFI at or above this fraction of its quota is flagged as a warning.
WARNING_FRACTION = 0.8
# How many days of history the Overview verification bars cover.
OVERVIEW_DAYS = 14
# Cap on the quota panel so it stays a short "worst offenders" list.
QUOTA_ROW_LIMIT = 6


def _pct(usage: int, quota: int | None) -> int:
    """Usage as a whole-percent of quota; 0 when the plan is unlimited."""
    if not quota:
        return 0
    return round(usage / quota * 100)


def _count_map(rows: list[tuple]) -> dict:
    """Turn ``(key, count)`` rows into a ``{key: count}`` dict."""
    return {key: count for key, count in rows if key is not None}


def platform_stats(db: Session) -> PlatformStats:
    """Compute the platform-wide totals shown on the admin Overview."""
    status_counts = _count_map(
        db.query(MfiAccount.status, func.count()).group_by(
            MfiAccount.status
        ).all()
    )
    total_verifications = (
        db.query(func.count(Verification.id)).scalar() or 0
    )
    # Staff accounts only; a platform admin has no MFI and is not counted.
    total_users = (
        db.query(func.count(User.id))
        .filter(User.mfi_account_id.isnot(None))
        .scalar()
        or 0
    )

    by_plan = [
        PlanBucket(plan=name.value, count=count)
        for name, count in db.query(
            SubscriptionPlan.name, func.count(MfiAccount.id)
        )
        .join(MfiAccount, MfiAccount.plan_id == SubscriptionPlan.id)
        .group_by(SubscriptionPlan.name)
        .all()
    ]

    # Quota consumption per MFI (only those on a metered plan).
    quota_rows: list[QuotaRow] = []
    warning_count = 0
    metered = (
        db.query(MfiAccount)
        .options(joinedload(MfiAccount.plan))
        .filter(MfiAccount.plan_id.isnot(None))
        .all()
    )
    for mfi in metered:
        quota = mfi.plan.verification_quota if mfi.plan else None
        pct = _pct(mfi.current_period_usage, quota)
        if quota and pct >= WARNING_FRACTION * 100:
            warning_count += 1
        quota_rows.append(
            QuotaRow(
                id=mfi.id,
                name=mfi.name,
                plan=mfi.plan.name.value if mfi.plan else None,
                usage=mfi.current_period_usage,
                quota=quota,
                pct=pct,
            )
        )
    quota_rows.sort(key=lambda r: r.pct, reverse=True)

    return PlatformStats(
        total_mfis=sum(status_counts.values()),
        active_mfis=status_counts.get(MfiStatus.ACTIVE, 0),
        suspended_mfis=status_counts.get(MfiStatus.SUSPENDED, 0),
        pending_mfis=status_counts.get(MfiStatus.PENDING, 0),
        total_verifications=total_verifications,
        total_users=total_users,
        warning_count=warning_count,
        by_plan=by_plan,
        per_day=_daily_verifications(db),
        quota_rows=quota_rows[:QUOTA_ROW_LIMIT],
    )


def _daily_verifications(db: Session) -> list[DayCount]:
    """Total verifications per day over the last ``OVERVIEW_DAYS`` days.

    Days with no activity are filled with zero so the client renders a
    continuous bar series.
    """
    start = date.today() - timedelta(days=OVERVIEW_DAYS - 1)
    day = func.date(Verification.created_at)
    counts = {
        d: c
        for d, c in db.query(day, func.count())
        .filter(day >= start)
        .group_by(day)
        .all()
    }
    return [
        DayCount(
            date=(d := start + timedelta(days=i)),
            count=counts.get(d, 0),
        )
        for i in range(OVERVIEW_DAYS)
    ]


def list_mfis(db: Session) -> list[AdminMfiSummary]:
    """List every MFI with its rollup counts, newest first."""
    verif = _count_map(
        db.query(Verification.mfi_account_id, func.count())
        .group_by(Verification.mfi_account_id)
        .all()
    )
    users = _count_map(
        db.query(User.mfi_account_id, func.count())
        .filter(User.mfi_account_id.isnot(None))
        .group_by(User.mfi_account_id)
        .all()
    )
    keys = _count_map(
        db.query(ApiKey.mfi_account_id, func.count())
        .filter(ApiKey.is_active.is_(True))
        .group_by(ApiKey.mfi_account_id)
        .all()
    )
    branches = _count_map(
        db.query(Branch.mfi_account_id, func.count())
        .group_by(Branch.mfi_account_id)
        .all()
    )

    mfis = (
        db.query(MfiAccount)
        .options(joinedload(MfiAccount.plan))
        .order_by(MfiAccount.created_at.desc())
        .all()
    )
    return [
        AdminMfiSummary(
            id=mfi.id,
            name=mfi.name,
            email=mfi.email,
            plan=mfi.plan.name.value if mfi.plan else None,
            status=mfi.status,
            usage=mfi.current_period_usage,
            quota=mfi.plan.verification_quota if mfi.plan else None,
            verifications=verif.get(mfi.id, 0),
            users=users.get(mfi.id, 0),
            api_keys=keys.get(mfi.id, 0),
            branches=branches.get(mfi.id, 0),
            created_at=mfi.created_at,
        )
        for mfi in mfis
    ]


def _month_bounds(today: date) -> tuple[date, date]:
    """First day of this month and of last month, for period counts."""
    this_start = today.replace(day=1)
    last_start = (this_start - timedelta(days=1)).replace(day=1)
    return this_start, last_start


def mfi_detail(db: Session, mfi: MfiAccount) -> AdminMfiDetail:
    """Build the full admin drill-down for one MFI."""
    plan = mfi.plan
    today = datetime.now(UTC).date()
    this_start, last_start = _month_bounds(today)
    day = func.date(Verification.created_at)
    base = Verification.mfi_account_id == mfi.id

    this_month = (
        db.query(func.count(Verification.id))
        .filter(base, day >= this_start)
        .scalar()
        or 0
    )
    last_month = (
        db.query(func.count(Verification.id))
        .filter(base, day >= last_start, day < this_start)
        .scalar()
        or 0
    )
    avg_per_day = round(this_month / today.day, 1)

    # Verification outcomes, all-time.
    status_counts = _count_map(
        db.query(Verification.status, func.count())
        .filter(base)
        .group_by(Verification.status)
        .all()
    )
    duplicates = (
        db.query(func.count(func.distinct(DuplicateFlag.verification_id)))
        .join(Verification, DuplicateFlag.verification_id == Verification.id)
        .filter(base)
        .scalar()
        or 0
    )
    seconds = func.extract(
        "epoch", Verification.processed_at - Verification.created_at
    )
    avg_seconds = (
        db.query(func.avg(seconds))
        .filter(base, Verification.processed_at.isnot(None))
        .scalar()
    )

    # Per-agent verification counts for this MFI.
    agent_counts = _count_map(
        db.query(Verification.agent_id, func.count())
        .filter(base)
        .group_by(Verification.agent_id)
        .all()
    )
    agents = [
        AdminAgentSummary(
            id=user.id,
            full_name=user.full_name,
            branch=user.branch_name,
            role=user.role,
            status=user.status,
            verifications=agent_counts.get(user.id, 0),
        )
        for user in (
            db.query(User)
            .options(joinedload(User.branch))
            .filter(User.mfi_account_id == mfi.id)
            .order_by(User.full_name)
            .all()
        )
    ]

    api_keys = [
        AdminApiKeySummary(
            prefix=key.prefix,
            is_active=key.is_active,
            last_used_at=key.last_used_at,
        )
        for key in sorted(
            mfi.api_keys, key=lambda k: k.is_active, reverse=True
        )
    ]

    verified = status_counts.get(
        VerificationStatus.VERIFIED, 0
    ) + status_counts.get(VerificationStatus.APPROVED, 0)
    return AdminMfiDetail(
        id=mfi.id,
        name=mfi.name,
        email=mfi.email,
        status=mfi.status,
        plan=plan.name.value if plan else None,
        quota=plan.verification_quota if plan else None,
        usage=mfi.current_period_usage,
        max_branches=plan.max_branches if plan else None,
        max_agents=plan.max_agents if plan else None,
        api_access=plan.api_access if plan else False,
        this_month=this_month,
        last_month=last_month,
        avg_per_day=avg_per_day,
        billing_cycle_start=mfi.billing_cycle_start,
        created_at=mfi.created_at,
        api_keys=api_keys,
        agents=agents,
        performance=MfiPerformance(
            verified=verified,
            pending=status_counts.get(VerificationStatus.PENDING, 0),
            rejected=status_counts.get(VerificationStatus.REJECTED, 0),
            duplicates=duplicates,
            avg_processing_seconds=(
                round(float(avg_seconds), 2)
                if avg_seconds is not None
                else None
            ),
        ),
    )
