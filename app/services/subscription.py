"""Subscription quota accounting and enforcement (Design doc §6.2).

An MFI's monthly verification allowance comes from its plan
(``verification_quota``); usage is tracked on the account
(``current_period_usage``) and resets at the start of each calendar month.
The manager warns at 80% and blocks at 100% of the quota.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import QuotaExceededError
from app.models import MfiAccount


@dataclass(frozen=True)
class QuotaStatus:
    """A point-in-time view of an account's quota consumption.

    Attributes:
        used: Verifications consumed in the current period.
        limit: The plan's monthly verification quota.
        remaining: Verifications left before the block (never negative).
        ratio: ``used / limit`` (0.0 when the limit is zero).
        warning: ``True`` once usage reaches the warning ratio (80%).
        exhausted: ``True`` once usage reaches the limit (block at 100%).
    """

    used: int
    limit: int
    remaining: int
    ratio: float
    warning: bool
    exhausted: bool


def get_quota_status(account: MfiAccount) -> QuotaStatus:
    """Compute the quota status for ``account`` from its plan and usage.

    Args:
        account: The MFI account, with its ``plan`` relationship loaded.

    Returns:
        The derived :class:`QuotaStatus`.
    """
    limit = account.plan.verification_quota
    used = account.current_period_usage
    ratio = used / limit if limit else 0.0
    return QuotaStatus(
        used=used,
        limit=limit,
        remaining=max(limit - used, 0),
        ratio=ratio,
        warning=ratio >= settings.quota_warning_ratio,
        exhausted=used >= limit,
    )


def enforce_quota(account: MfiAccount) -> QuotaStatus:
    """Return the quota status, raising if the account is exhausted.

    Args:
        account: The MFI account to check.

    Returns:
        The current :class:`QuotaStatus` (when not exhausted).

    Raises:
        QuotaExceededError: If usage has reached the plan limit.
    """
    status = get_quota_status(account)
    if status.exhausted:
        raise QuotaExceededError(
            f"Monthly verification quota of {status.limit} reached."
        )
    return status


def roll_period_if_needed(session: Session, account: MfiAccount) -> None:
    """Reset usage when the billing month has rolled over.

    If the account has no billing cycle yet, or its cycle started in a
    previous calendar month, usage is zeroed and the cycle is restarted on
    the first of the current month.

    Args:
        session: An open database session (committed on reset).
        account: The MFI account to roll forward.
    """
    today = date.today()
    start = account.billing_cycle_start
    if start is None or (start.year, start.month) != (today.year, today.month):
        account.current_period_usage = 0
        account.billing_cycle_start = today.replace(day=1)
        session.commit()


def record_usage(session: Session, account: MfiAccount) -> None:
    """Increment the account's period usage by one and persist.

    Args:
        session: An open database session.
        account: The MFI account whose usage to increment.
    """
    account.current_period_usage += 1
    session.commit()
