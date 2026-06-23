"""Unit tests for the subscription-plan seed definitions (no DB)."""

from app.models.enums import PlanName
from scripts.seed_plans import plan_definitions


def test_four_tiers_defined() -> None:
    """All four subscription tiers are present exactly once."""
    names = [d["name"] for d in plan_definitions()]
    assert names == [
        PlanName.STARTER,
        PlanName.GROWTH,
        PlanName.PRO,
        PlanName.ENTERPRISE,
    ]


def test_starter_tier_values() -> None:
    """Starter matches Design doc §6.2 (200 quota, 25k FCFA, no API)."""
    starter = next(
        d for d in plan_definitions() if d["name"] == PlanName.STARTER
    )
    assert starter["verification_quota"] == 200
    assert starter["monthly_price"] == 25_000
    assert starter["max_agents"] == 3
    assert starter["api_access"] is False


def test_unlimited_and_custom_encoded_as_none() -> None:
    """Unlimited limits and custom price are encoded as None."""
    plans = {d["name"]: d for d in plan_definitions()}
    assert plans[PlanName.PRO]["max_branches"] is None
    assert plans[PlanName.PRO]["api_access"] is True
    assert plans[PlanName.ENTERPRISE]["monthly_price"] is None
    assert plans[PlanName.ENTERPRISE]["verification_quota"] == 10_000
