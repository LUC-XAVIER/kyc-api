"""MFI-side entities: subscription plan, account, agent, and API key."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String
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
    agents: Mapped[list["Agent"]] = relationship(
        back_populates="mfi_account"
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="mfi_account"
    )


class Agent(UUIDMixin, TimestampMixin, Base):
    """An MFI field agent who submits verification requests."""

    __tablename__ = "agents"

    mfi_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mfi_accounts.id")
    )
    full_name: Mapped[str] = mapped_column(String(255))
    branch: Mapped[str | None] = mapped_column(String(255))
    # Login credentials for the management dashboard. Nullable so agents
    # provisioned before dashboard access exist without a password; both
    # are required to authenticate (enforced at the login endpoint).
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[AgentRole] = mapped_column(
        Enum(AgentRole, name="agent_role"), default=AgentRole.AGENT
    )
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, name="agent_status"), default=AgentStatus.ACTIVE
    )

    mfi_account: Mapped["MfiAccount"] = relationship(
        back_populates="agents"
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
