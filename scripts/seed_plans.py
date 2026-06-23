"""Seed the four subscription plans (Design doc §6.2).

Idempotent: running it repeatedly updates existing plans in place rather
than creating duplicates. ``None`` for branch/agent limits means
unlimited; ``None`` price means custom (Enterprise).

Usage:
    uv run python -m scripts.seed_plans
"""

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import SubscriptionPlan
from app.models.enums import PlanName


def plan_definitions() -> list[dict]:
    """Return the canonical definition of every subscription tier."""
    return [
        {
            "name": PlanName.STARTER,
            "monthly_price": 25_000,
            "verification_quota": 200,
            "max_branches": 1,
            "max_agents": 3,
            "api_access": False,
            "report_access": "monthly",
            "support_level": "Email",
        },
        {
            "name": PlanName.GROWTH,
            "monthly_price": 65_000,
            "verification_quota": 1_000,
            "max_branches": 5,
            "max_agents": 15,
            "api_access": True,
            "report_access": "on_demand",
            "support_level": "Priority email",
        },
        {
            "name": PlanName.PRO,
            "monthly_price": 150_000,
            "verification_quota": 5_000,
            "max_branches": None,  # unlimited
            "max_agents": None,  # unlimited
            "api_access": True,
            "report_access": "on_demand",
            "support_level": "Phone + email, 24h",
        },
        {
            "name": PlanName.ENTERPRISE,
            "monthly_price": None,  # custom
            "verification_quota": 10_000,
            "max_branches": None,
            "max_agents": None,
            "api_access": True,
            "report_access": "on_demand",
            "support_level": "Dedicated account manager",
        },
    ]


def seed(session: Session) -> int:
    """Upsert all plan definitions into the database.

    Args:
        session: An open database session.

    Returns:
        The number of plans seeded.
    """
    definitions = plan_definitions()
    for data in definitions:
        existing = (
            session.query(SubscriptionPlan)
            .filter_by(name=data["name"])
            .one_or_none()
        )
        if existing is None:
            session.add(SubscriptionPlan(**data))
        else:
            for key, value in data.items():
                setattr(existing, key, value)
    session.commit()
    return len(definitions)


def main() -> None:
    """Entry point for ``python -m scripts.seed_plans``."""
    session = SessionLocal()
    try:
        count = seed(session)
        print(f"Seeded {count} subscription plans.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
