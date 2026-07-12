"""Seed a manager account for local dashboard login (dev convenience).

Creates (or refreshes) an MFI on the Growth plan and a MANAGER you can sign
in with at the Angular dashboard. Idempotent — re-running just resets the PIN.

Run (after `docker compose up -d db` and `python -m scripts.seed_plans`):

    uv run python -m scripts.seed_manager
    uv run python -m scripts.seed_manager --email you@mfi.cm --pin 246810
"""

import argparse
from datetime import date

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Agent, MfiAccount, SubscriptionPlan
from app.models.enums import AgentRole, AgentStatus, MfiStatus, PlanName


def main() -> None:
    """Create/refresh the manager and print the login credentials."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default="manager@camfinance.cm")
    parser.add_argument("--pin", default="123456")
    parser.add_argument("--name", default="Eric Ngono")
    parser.add_argument("--mfi", default="CamFinance Microfinance")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        plan = (
            db.query(SubscriptionPlan)
            .filter_by(name=PlanName.GROWTH)
            .one_or_none()
        )

        mfi = db.query(MfiAccount).filter_by(email=args.email).one_or_none()
        if mfi is None:
            mfi = MfiAccount(
                name=args.mfi,
                email=args.email,
                plan_id=plan.id if plan else None,
                status=MfiStatus.ACTIVE,
                billing_cycle_start=date.today().replace(day=1),
            )
            db.add(mfi)
            db.flush()

        agent = db.query(Agent).filter_by(email=args.email).one_or_none()
        if agent is None:
            agent = Agent(mfi_account_id=mfi.id, full_name=args.name)
            db.add(agent)
        agent.email = args.email
        agent.full_name = args.name
        agent.hashed_password = hash_password(args.pin)
        agent.role = AgentRole.MANAGER
        agent.status = AgentStatus.ACTIVE

        db.commit()
        print(
            f"Manager ready — sign in with email={args.email} "
            f"pin={args.pin}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
