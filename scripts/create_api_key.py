r"""Provision an MFI account and issue an API key (dev/onboarding helper).

The plaintext key is printed exactly once — copy it immediately, since only
its HMAC digest is stored and it cannot be recovered later. Re-running with
the same email reuses the account but always mints a fresh key.

Usage:
    uv run python -m scripts.create_api_key
    uv run python -m scripts.create_api_key --name "Acme MFI" \\
        --email acme@example.com --plan GROWTH
"""

import argparse

from sqlalchemy.orm import Session

from app.core.security import generate_api_key
from app.db.session import SessionLocal
from app.models import ApiKey, MfiAccount, SubscriptionPlan
from app.models.enums import PlanName


def provision(
    session: Session, *, name: str, email: str, plan_name: PlanName
) -> str:
    """Create/reuse the MFI account, mint a key, and return the plaintext.

    Args:
        session: An open database session.
        name: Display name of the MFI.
        email: Unique account email; reused if it already exists.
        plan_name: Subscription tier to attach.

    Returns:
        The plaintext API key (shown once; never stored).
    """
    plan = (
        session.query(SubscriptionPlan)
        .filter_by(name=plan_name)
        .one_or_none()
    )
    if plan is None:
        raise SystemExit(
            f"Plan {plan_name} not found — run scripts.seed_plans first."
        )

    account = (
        session.query(MfiAccount).filter_by(email=email).one_or_none()
    )
    if account is None:
        account = MfiAccount(name=name, email=email, plan_id=plan.id)
        session.add(account)
        session.flush()

    key = generate_api_key()
    session.add(
        ApiKey(
            mfi_account_id=account.id,
            hashed_key=key.hashed_key,
            prefix=key.prefix,
        )
    )
    session.commit()
    return key.full_key


def main() -> None:
    """Parse args and print the freshly issued key."""
    parser = argparse.ArgumentParser(description="Issue an MFI API key.")
    parser.add_argument("--name", default="Dev MFI")
    parser.add_argument("--email", default="dev@example.com")
    parser.add_argument(
        "--plan",
        default=PlanName.STARTER.value,
        choices=[p.value for p in PlanName],
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        full_key = provision(
            session,
            name=args.name,
            email=args.email,
            plan_name=PlanName(args.plan),
        )
    finally:
        session.close()

    print("API key (store it now — it will not be shown again):")
    print(f"  {full_key}")


if __name__ == "__main__":
    main()
