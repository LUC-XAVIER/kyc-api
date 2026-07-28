"""Subscription payments made via mobile money (Campay: MTN MoMo / Orange).

A payment collects the price of a plan from an MFI's mobile-money account.
On success the account is activated/renewed and its billing cycle rolls.
Payments are an immutable-ish ledger: a row's ``status`` moves PENDING →
SUCCESSFUL/FAILED exactly once and is never reused.
"""

import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import PaymentProvider, PaymentStatus, PlanName


class Payment(UUIDMixin, TimestampMixin, Base):
    """One mobile-money collection for an MFI's plan subscription."""

    __tablename__ = "payments"

    mfi_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mfi_accounts.id"), index=True
    )
    # The plan this payment buys. Kept as the enum name (not a plan FK) so the
    # record survives any later re-pricing of that tier.
    plan_name: Mapped[PlanName] = mapped_column(
        Enum(PlanName, name="plan_name")
    )
    # Charged amount, in the smallest whole unit of the currency (XAF has no
    # minor unit, so this is whole francs).
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="XAF")
    # Payer's mobile-money number, normalised to full international form.
    phone: Mapped[str] = mapped_column(String(32))
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"),
        default=PaymentStatus.PENDING,
    )
    provider: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider, name="payment_provider")
    )
    # Our idempotency key, sent to the provider as external_reference and
    # echoed back on the webhook so a callback maps to exactly one payment.
    external_reference: Mapped[str] = mapped_column(String(64), unique=True)
    # The provider's own transaction id, for status polling and support.
    provider_reference: Mapped[str | None] = mapped_column(String(128))
    # USSD code the payer can dial to approve, when the provider returns one.
    ussd_code: Mapped[str | None] = mapped_column(String(32))
    # Free-text reason when a payment fails (declined, timeout, …).
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    # When the collection reached a terminal state (success or failure).
    completed_at: Mapped[datetime | None] = mapped_column()

    mfi_account = relationship("MfiAccount")
