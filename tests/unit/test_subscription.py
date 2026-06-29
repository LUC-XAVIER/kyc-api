"""Unit tests for quota accounting (no DB; transient ORM objects)."""

import pytest

from app.core.exceptions import QuotaExceededError
from app.models import MfiAccount, SubscriptionPlan
from app.models.enums import PlanName
from app.services import subscription


def _account(used: int, limit: int = 200) -> MfiAccount:
    """Build a transient account on a plan with the given quota."""
    plan = SubscriptionPlan(name=PlanName.STARTER, verification_quota=limit)
    return MfiAccount(current_period_usage=used, plan=plan)


def test_below_warning_threshold() -> None:
    """Under 80% usage: no warning, not exhausted."""
    status = subscription.get_quota_status(_account(used=100))
    assert status.remaining == 100
    assert status.warning is False
    assert status.exhausted is False


def test_warning_threshold_reached() -> None:
    """At 80% usage the warning flag flips on but it is not blocked."""
    status = subscription.get_quota_status(_account(used=160))
    assert status.warning is True
    assert status.exhausted is False


def test_quota_exhausted_at_limit() -> None:
    """At 100% usage the account is exhausted with zero remaining."""
    status = subscription.get_quota_status(_account(used=200))
    assert status.remaining == 0
    assert status.exhausted is True


def test_enforce_passes_below_limit() -> None:
    """enforce_quota returns the status when under the limit."""
    status = subscription.enforce_quota(_account(used=199))
    assert status.exhausted is False


def test_enforce_raises_at_limit() -> None:
    """enforce_quota raises QuotaExceededError once exhausted."""
    with pytest.raises(QuotaExceededError):
        subscription.enforce_quota(_account(used=200))
