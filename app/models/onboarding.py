"""Self-service onboarding — pending manager signup invites."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class SignupInvite(UUIDMixin, TimestampMixin, Base):
    """A pending manager signup created when a customer chooses a plan.

    The customer receives an emailed link carrying the raw token; only its
    digest is stored (``token_hash``). Completing the signup creates the MFI
    account and its first manager, and stamps ``completed_at``.
    """

    __tablename__ = "signup_invites"

    email: Mapped[str] = mapped_column(String(255), index=True)
    plan: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
