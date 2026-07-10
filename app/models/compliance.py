"""Compliance entities: immutable audit log and generated reports."""

import uuid
from datetime import date, datetime

from sqlalchemy import JSON as SAJSON
from sqlalchemy import Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin
from app.models.enums import ActorType, ReportFormat


class AuditLog(UUIDMixin, Base):
    """Immutable record of every action, for COBAC compliance (FR08).

    Append-only: rows are never updated or deleted.
    """

    __tablename__ = "audit_logs"

    verification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("verifications.id"), index=True
    )
    mfi_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mfi_accounts.id"), index=True
    )
    action: Mapped[str] = mapped_column(String(64))
    actor_type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, name="actor_type")
    )
    actor_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(SAJSON)
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now())


class ComplianceReport(UUIDMixin, Base):
    """A generated compliance report for an MFI over a period (FR10)."""

    __tablename__ = "compliance_reports"

    mfi_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mfi_accounts.id"), index=True
    )
    generated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    period_start: Mapped[date] = mapped_column()
    period_end: Mapped[date] = mapped_column()
    total_verifications: Mapped[int] = mapped_column(Integer, default=0)
    # Snapshot of the {status: count} breakdown at generation time, so the
    # report stays an immutable record of the period.
    status_breakdown: Mapped[dict | None] = mapped_column(SAJSON)
    format: Mapped[ReportFormat] = mapped_column(
        Enum(ReportFormat, name="report_format"), default=ReportFormat.PDF
    )
