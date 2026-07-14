"""MFI-side entities: subscription plan, account, user, and API key."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import AgentRole, AgentStatus, MfiStatus, PlanName


class SubscriptionPlan(UUIDMixin, Base):
    """A subscription tier governing an MFI's quota, limits, and features.

    ``None`` for ``max_branches`` / ``max_agents`` means *unlimited*, and a
    ``None`` ``monthly_price`` denotes custom (Enterprise) pricing.
    """

    __tablename__ = "subscription_plans"

    name: Mapped[PlanName] = mapped_column(
        Enum(PlanName, name="plan_name"), unique=True
    )
    monthly_price: Mapped[int | None] = mapped_column(Integer)  # FCFA
    verification_quota: Mapped[int] = mapped_column(Integer)
    max_branches: Mapped[int | None] = mapped_column(Integer)
    max_agents: Mapped[int | None] = mapped_column(Integer)
    api_access: Mapped[bool] = mapped_column(Boolean, default=False)
    report_access: Mapped[str] = mapped_column(String(32))  # monthly/on_demand
    support_level: Mapped[str] = mapped_column(String(64))

    accounts: Mapped[list["MfiAccount"]] = relationship(
        back_populates="plan"
    )


class MfiAccount(UUIDMixin, TimestampMixin, Base):
    """A Microfinance Institution subscribed to the platform."""

    __tablename__ = "mfi_accounts"

    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[MfiStatus] = mapped_column(
        Enum(MfiStatus, name="mfi_status"), default=MfiStatus.PENDING
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subscription_plans.id")
    )

    # Subscription usage tracking (Design doc §6.2).
    current_period_usage: Mapped[int] = mapped_column(Integer, default=0)
    billing_cycle_start: Mapped[date | None] = mapped_column()

    plan: Mapped["SubscriptionPlan | None"] = relationship(
        back_populates="accounts"
    )
    users: Mapped[list["User"]] = relationship(
        back_populates="mfi_account"
    )
    branches: Mapped[list["Branch"]] = relationship(
        back_populates="mfi_account"
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="mfi_account"
    )


class User(UUIDMixin, TimestampMixin, Base):
    """A person who signs in for an MFI — a manager or a field agent.

    The ``role`` distinguishes them; both share one login (identifier +
    PIN). This is the ``users`` table (formerly ``agents``).
    """

    __tablename__ = "users"

    mfi_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mfi_accounts.id")
    )
    full_name: Mapped[str] = mapped_column(String(255))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("branches.id")
    )
    # Login identity. Managers sign in with their email, agents with their
    # phone number; both are unique and nullable so an account carries only
    # the identifier its role uses. ``hashed_pin`` stores the bcrypt hash of
    # the 6-8 char PIN (the shared credential for both roles).
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True)
    hashed_pin: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[AgentRole] = mapped_column(
        Enum(AgentRole, name="agent_role"), default=AgentRole.AGENT
    )
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, name="agent_status"), default=AgentStatus.ACTIVE
    )

    mfi_account: Mapped["MfiAccount"] = relationship(
        back_populates="users"
    )
    branch: Mapped["Branch | None"] = relationship()

    @property
    def branch_name(self) -> str | None:
        """The user's branch name, or ``None`` (e.g. org-wide managers)."""
        return self.branch.name if self.branch else None


class Branch(UUIDMixin, TimestampMixin, Base):
    """A physical office of an MFI; the plan caps how many exist."""

    __tablename__ = "branches"

    mfi_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mfi_accounts.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))

    mfi_account: Mapped["MfiAccount"] = relationship(
        back_populates="branches"
    )

    __table_args__ = (
        UniqueConstraint(
            "mfi_account_id", "name", name="uq_branches_mfi_name"
        ),
    )


class ApiKey(UUIDMixin, TimestampMixin, Base):
    """A hashed API key used by an MFI's own software to call the API.

    The plaintext key is never stored; only ``hashed_key`` (NFR03).
    """

    __tablename__ = "api_keys"

    mfi_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mfi_accounts.id")
    )
    hashed_key: Mapped[str] = mapped_column(String(255), unique=True)
    prefix: Mapped[str] = mapped_column(String(16))  # shown in dashboard
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    rate_limit: Mapped[int | None] = mapped_column(Integer)
    last_used_at: Mapped[datetime | None] = mapped_column()

    mfi_account: Mapped["MfiAccount"] = relationship(
        back_populates="api_keys"
    )
