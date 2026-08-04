"""Manager notification preferences and email triggers.

The manager Settings screen exposes four toggles. One — "New PENDING case" —
is handled in-app (a toast). The other three are email alerts orchestrated
here:

* ``quota``       — one warning when usage first crosses the 80% threshold.
* ``weekly``      — a digest of the last 7 days (sent by a scheduled script).
* ``maintenance`` — a broadcast an admin sends from the admin dashboard.

Preferences are stored on :class:`MfiAccount.notification_prefs` (JSON); a null
value means "use :data:`NOTIF_DEFAULTS`". This module owns *who* and *when*;
:mod:`app.services.email` owns the message bodies and the actual send.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import EmailError
from app.models import DuplicateFlag, MfiAccount, Verification
from app.models.enums import VerificationStatus
from app.services import email as email_service
from app.services import subscription
from app.services.subscription import QuotaStatus

logger = logging.getLogger("app.notifications")

# How many days the weekly digest looks back over.
DIGEST_DAYS = 7

# Mirrors the frontend defaults (manager.component.ts NOTIF_DEFAULTS).
NOTIF_DEFAULTS: dict[str, bool] = {
    "quota": True,
    "pending": True,
    "weekly": False,
    "maintenance": True,
}
NOTIF_KEYS = frozenset(NOTIF_DEFAULTS)


def get_prefs(account: MfiAccount) -> dict[str, bool]:
    """Return the account's notification prefs, defaults filling any gaps."""
    stored = account.notification_prefs or {}
    return {key: bool(stored.get(key, default))
            for key, default in NOTIF_DEFAULTS.items()}


def pref_enabled(account: MfiAccount, key: str) -> bool:
    """Whether ``account`` wants the ``key`` notification (default-aware)."""
    return get_prefs(account)[key]


def sanitize_prefs(raw: dict) -> dict[str, bool]:
    """Coerce a client payload to a clean {known_key: bool} dict."""
    return {key: bool(value)
            for key, value in raw.items()
            if key in NOTIF_KEYS}


def maybe_send_quota_warning(
    session: Session, account: MfiAccount, quota: QuotaStatus
) -> None:
    """Email the 80%-quota warning once per period, if the MFI wants it.

    Called after a verification is recorded. Guarded by
    ``account.quota_warning_sent`` so it fires a single time each billing
    period (the flag is reset in ``subscription.roll_period_if_needed``). A
    failed send is logged, never raised — it must not break verification.
    """
    if account.quota_warning_sent or not quota.warning or quota.exhausted:
        return
    if not pref_enabled(account, "quota"):
        return
    try:
        email_service.send_quota_warning(
            account.email, used=quota.used, limit=quota.limit
        )
    except EmailError:
        logger.exception("quota-warning email to %s failed", account.email)
        return
    account.quota_warning_sent = True
    session.commit()


@dataclass(frozen=True)
class WeeklyDigest:
    """Last-``DIGEST_DAYS`` activity summary for one MFI."""

    days: int
    total: int
    verified: int
    pending: int
    rejected: int
    open_pending: int  # cases currently awaiting a manager's review
    duplicates: int
    quota_used: int
    quota_limit: int


def build_weekly_digest(db: Session, account: MfiAccount) -> WeeklyDigest:
    """Compute the weekly digest figures for ``account``."""
    since = datetime.now(UTC) - timedelta(days=DIGEST_DAYS)
    owned = Verification.mfi_account_id == account.id
    recent = (owned, Verification.created_at >= since)

    counts = dict(
        db.query(Verification.status, func.count())
        .filter(*recent)
        .group_by(Verification.status)
        .all()
    )

    def total_of(*statuses: VerificationStatus) -> int:
        return sum(counts.get(s, 0) for s in statuses)

    open_pending = (
        db.query(func.count(Verification.id))
        .filter(owned, Verification.status == VerificationStatus.PENDING)
        .scalar()
        or 0
    )
    duplicates = (
        db.query(func.count(func.distinct(DuplicateFlag.verification_id)))
        .join(Verification, DuplicateFlag.verification_id == Verification.id)
        .filter(*recent)
        .scalar()
        or 0
    )
    quota = subscription.get_quota_status(account)
    return WeeklyDigest(
        days=DIGEST_DAYS,
        total=sum(counts.values()),
        verified=total_of(
            VerificationStatus.VERIFIED, VerificationStatus.APPROVED
        ),
        pending=total_of(VerificationStatus.PENDING),
        rejected=total_of(VerificationStatus.REJECTED),
        open_pending=open_pending,
        duplicates=duplicates,
        quota_used=quota.used,
        quota_limit=quota.limit,
    )


def send_weekly_digest_for(db: Session, account: MfiAccount) -> bool:
    """Build and email the weekly digest for one MFI.

    Returns True if an email was sent. Skips accounts with no activity in the
    window (nothing worth a message). A failed send is logged, not raised.
    """
    digest = build_weekly_digest(db, account)
    if digest.total == 0:
        return False
    try:
        email_service.send_weekly_digest(account.email, digest)
    except EmailError:
        logger.exception("weekly digest to %s failed", account.email)
        return False
    return True
