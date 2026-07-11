"""Helpers to seed test data into a (rolled-back) database session."""

from datetime import date

from sqlalchemy.orm import Session

from app.core.security import generate_api_key, hash_password
from app.models import Agent, ApiKey, MfiAccount, SubscriptionPlan
from app.models.enums import AgentRole, PlanName


def create_mfi_with_key(
    db: Session,
    *,
    plan_name: PlanName = PlanName.STARTER,
    usage: int = 0,
    email: str = "factory@example.com",
    name: str = "Factory MFI",
) -> tuple[MfiAccount, str]:
    """Create an MFI account with one active API key.

    Args:
        db: An open session (caller is responsible for rollback/cleanup).
        plan_name: Subscription tier to attach (must already be seeded).
        usage: Initial ``current_period_usage`` for quota scenarios.
        email: Unique account email.
        name: Account display name.

    Returns:
        The created account and the plaintext API key.
    """
    plan = db.query(SubscriptionPlan).filter_by(name=plan_name).one()
    account = MfiAccount(
        name=name,
        email=email,
        plan_id=plan.id,
        current_period_usage=usage,
        # An account already consuming quota is within an active billing
        # cycle; without this, roll_period_if_needed would reset usage.
        billing_cycle_start=date.today().replace(day=1),
    )
    db.add(account)
    db.flush()

    key = generate_api_key()
    db.add(
        ApiKey(
            mfi_account_id=account.id,
            hashed_key=key.hashed_key,
            prefix=key.prefix,
        )
    )
    db.flush()
    return account, key.full_key


def create_agent(
    db: Session,
    mfi: MfiAccount,
    *,
    email: str = "agent@example.com",
    password: str = "password123",
    role: AgentRole = AgentRole.AGENT,
    full_name: str = "Test Agent",
    branch: str = "Central",
) -> Agent:
    """Create a login-capable agent under ``mfi``.

    Args:
        db: An open session (caller owns rollback/cleanup).
        mfi: The owning account the agent belongs to.
        email: Login email (unique).
        password: Plaintext password; stored hashed.
        role: The agent's dashboard role.
        full_name: Display name.
        branch: Branch label.

    Returns:
        The flushed :class:`~app.models.mfi.Agent`.
    """
    agent = Agent(
        mfi_account_id=mfi.id,
        full_name=full_name,
        branch=branch,
        email=email,
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(agent)
    db.flush()
    return agent
